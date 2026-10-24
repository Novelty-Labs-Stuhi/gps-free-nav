"""Closed-loop missions: the drone's estimate steers its flight, and a decision policy acts on its belief.

The benchmark flies fixed routes, so nothing an algorithm believes changes where the drone goes. Here it does:
every DECISION_S seconds a policy reads a summary of the navigator's belief and picks an action; an autopilot then
steers toward its target using the ESTIMATED position, so estimation errors really push the drone off course.
Truth dynamics, wind, sensors and maps reuse the benchmark's models (gpsfree.trajectory, sensors, world).

Mission: fly from S to a goal G 2-3 km away and land within GOAL_M of it, without ever crossing a no-fly line
(a border) that runs parallel to the direct path, before the battery runs out."""
import json
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from gpsfree.algorithm import Context, MapView, Pose
from gpsfree.evaluate import _world, load_scenario, load_suite, start_offset
from gpsfree.routes import scenario_route, stable_seed
from gpsfree.sensors import echo_directions, hardware_sensors, sensor_spec
from gpsfree.trajectory import DRAG_PER_M, GUST_TAU_S, G, _multirotor_attitude

DT = 0.01
DECISION_S = 10.0
GOAL_M = 50.0
SPEED = 10.0
ACC_TAU_S = 0.5
GUST_SMOOTH_S = 0.5   # acceleration (hence attitude) follows the autopilot's demand with this lag
ACTIONS = ["continue", "climb", "detour", "slow", "land"]
EVENT_ORDER = ["imu", "mag", "baro", "echo"]


# ------------------------------------------------------------------ truth: point-mass flight with wind
class Wind:
    def __init__(self, cfg, rng):
        spd, ang = (rng.uniform(*cfg["mean_mps"]), rng.uniform(0, 2 * np.pi)) if cfg else (0.0, 0.0)
        self.mean = np.array([spd * np.cos(ang), spd * np.sin(ang), 0.0])
        self.sigma = (cfg or {}).get("gust_mps", 0.0) * np.array([1, 1, 0.5])
        self.g = np.zeros(3)
        self.gs = np.zeros(3)
        self.a = np.exp(-DT / GUST_TAU_S)
        self.rng = rng

    def step(self):
        """Gauss-Markov gusts, low-passed (GUST_SMOOTH_S) so the drone's attitude stays smooth enough for a
        100 Hz gyro to follow, as real air does at the scale of a drone."""
        self.g = self.a * self.g + self.rng.normal(0, 1, 3) * self.sigma * np.sqrt(1 - self.a ** 2)
        self.gs = self.gs + (self.g - self.gs) * (DT / GUST_SMOOTH_S)
        return self.mean + self.gs


class SegmentTrajectory:
    """Same interface as gpsfree.trajectory.Trajectory over dense 100 Hz arrays of one flown segment."""

    class _Route:
        platform = "drone"

    route = _Route()

    def __init__(self, t, p, v, a, yaw, wind):
        self.t, self.p, self.v, self.a, self.yaw, self.wind = t, p, v, a, yaw, wind
        self.t0, self.t1 = float(t[0]), float(t[-1]) + DT

    def sample(self, t):
        t = np.asarray(t, float)
        f = lambda arr: np.stack([np.interp(t, self.t, arr[:, i]) for i in range(arr.shape[1])], 1)  # noqa: E731
        p, v, a, w = f(self.p), f(self.v), f(self.a), f(self.wind)
        yaw = np.interp(t, self.t, self.yaw)
        air = v - w
        drag = -DRAG_PER_M * np.linalg.norm(air, axis=1, keepdims=True) * air
        rot = _multirotor_attitude(a - drag, yaw)
        return {"t": t, "p": p, "v": v, "a": a, "yaw": yaw, "rot": rot, "airspeed": np.linalg.norm(air, axis=1)}

    def body_rates(self, rot, dt):
        d = (rot[:-2].inv() * rot[2:]).as_rotvec() / (2 * dt)
        return np.vstack([d[:1], d, d[-1:]])


class Sensors:
    """Segment-by-segment version of gpsfree.sensors.generate whose biases, hard iron and baro drift persist."""

    def __init__(self, cfg, world, rng):
        self.cfg, self.world, self.rng = cfg, world, rng
        c = cfg["imu"]
        self.acc_bias = rng.normal(0, c["acc_bias_init"], 3)
        self.gyro_bias = rng.normal(0, c["gyro_bias_init"], 3)
        self.hard_iron = rng.normal(0, cfg["mag"]["hard_iron_ut"], 3)
        self.drift = 0.0
        self.dirs_b = echo_directions(cfg["echo"]["pattern"])

    def generate(self, traj):
        cfg, rng, out = self.cfg, self.rng, {}
        c = cfg["imu"]
        dt = 1 / c["rate_hz"]
        t = np.arange(traj.t0, traj.t1 - 1e-9, dt)
        s = traj.sample(t)
        acc = s["rot"].inv().apply(s["a"] + np.array([0, 0, G]))
        gyro = traj.body_rates(s["rot"], dt)
        n = len(t)
        self.acc_bias = self.acc_bias + np.cumsum(rng.normal(0, c["acc_bias_walk"] * np.sqrt(dt), (n, 3)), 0)[-1]
        self.gyro_bias = self.gyro_bias + np.cumsum(rng.normal(0, c["gyro_bias_walk"] * np.sqrt(dt), (n, 3)), 0)[-1]
        out["imu"] = {"t": t, "acc": acc + self.acc_bias + rng.normal(0, c["acc_noise"], (n, 3)),
                      "gyro": gyro + self.gyro_bias + rng.normal(0, c["gyro_noise"], (n, 3))}
        c = cfg["mag"]
        t = np.arange(traj.t0, traj.t1 - 1e-9, 1 / c["rate_hz"])
        s = traj.sample(t)
        out["mag"] = {"t": t, "field": s["rot"].inv().apply(np.array(c["field_enu_ut"])) + self.hard_iron
                      + rng.normal(0, c["noise_ut"], (len(t), 3))}
        c = cfg["baro"]
        bdt = 1 / c["rate_hz"]
        t = np.arange(traj.t0, traj.t1 - 1e-9, bdt)
        s = traj.sample(t)
        drift = self.drift + np.cumsum(rng.normal(0, c["drift_m_per_sqrt_s"] * np.sqrt(bdt), len(t)))
        self.drift = float(drift[-1])
        out["baro"] = {"t": t, "altitude": s["p"][:, 2] + drift + rng.normal(0, c["noise_m"], len(t))
                       - c.get("airspeed_coeff", 0.0) * s["airspeed"] ** 2 / (2 * G)}
        c = cfg["echo"]
        t = np.arange(traj.t0, traj.t1 - 1e-9, 1 / c["rate_hz"])
        s = traj.sample(t)
        nb = len(self.dirs_b)
        dirs_w = np.einsum("tij,bj->tbi", s["rot"].as_matrix(), self.dirs_b).reshape(-1, 3)
        rt = self.world.raycast(np.repeat(s["p"], nb, axis=0), dirs_w, c["max_range_m"]).reshape(len(t), nb)
        noisy = rt + rng.normal(0, 1, rt.shape) * (c["noise_m"] + c["noise_frac"] * np.nan_to_num(rt, posinf=0))
        noisy[rng.random(noisy.shape) < c["dropout"]] = np.inf
        out["echo"] = {"t": t, "ranges": noisy}
        return out


def info_grid(m, cell=50.0):
    """How much a lidar learns over each 50 m cell of the MAP: the spread of map heights inside it."""
    (x0, y0, _), (x1, y1, _) = m.meta["bounds"]
    xs, ys = np.arange(x0, x1, cell / 5), np.arange(y0, y1, cell / 5)
    X, Y = np.meshgrid(xs, ys)
    h = m.height(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
    h[~np.isfinite(h)] = np.nanmin(np.where(np.isfinite(h), h, np.nan))
    k = 5
    hh = h[: h.shape[0] // k * k, : h.shape[1] // k * k].reshape(h.shape[0] // k, k, h.shape[1] // k, k)
    return x0, y0, cell, hh.std(axis=(1, 3))


# ------------------------------------------------------------------ mission
@dataclass
class Outcome:
    reward: float
    success: bool
    violation: bool
    battery_out: bool
    landed_err_m: float
    silent_wrong_landing: bool
    decisions: list
    t: float


class Mission:
    def __init__(self, scenario_id, seed, navigator_cls, record=False):
        suite = load_suite()
        sc = load_scenario(scenario_id)
        self.sc, self.seed, self.record = sc, seed, record
        rng = np.random.default_rng([seed, 7])
        self.world = _world(sc["world"])
        self.map = self.world.map_world(sc.get("map"), seed=stable_seed("map", sc["id"]))
        route = scenario_route(sc, 20 + seed % 40, self.world)  # start from a training-route start point
        S = route.position[0].copy()
        R = self.world.radius * 0.75
        for _ in range(50):  # goal 2-3 km away, inside the world
            ang, dist = rng.uniform(0, 2 * np.pi), rng.uniform(2000, 3000)
            Gxy = S[:2] + dist * np.array([np.cos(ang), np.sin(ang)])
            if np.abs(Gxy).max() < R:
                break
        else:
            Gxy = -S[:2] * 0.5
        self.S, self.G = S, Gxy
        d = (Gxy - S[:2]) / np.linalg.norm(Gxy - S[:2])
        side = rng.choice([-1, 1])
        self.n = side * np.array([-d[1], d[0]])               # no-fly is where (x - S) . n > offset
        self.nofly_off = rng.uniform(150, 400)
        self.battery_s = 1.5 * np.linalg.norm(Gxy - S[:2]) / SPEED + 60
        self.agl = rng.uniform(*sc["route"].get("agl_m", (40, 100)))
        self.wind = Wind(sc.get("wind"), np.random.default_rng([seed, 8]))
        self.sensors_cfg = hardware_sensors(suite["sensors"], navigator_cls.hardware, navigator_cls.ranger or suite["default_ranger"])
        self.sensors = Sensors(self.sensors_cfg, self.world, np.random.default_rng([seed, 9]))
        lo, hi = sc.get("start_offset_m", [0, 0])
        off = np.zeros(3)
        sigma = 0.0
        if hi > 0:
            r2 = np.random.default_rng([seed, 10])
            dd, aa = r2.uniform(lo, hi), r2.uniform(0, 2 * np.pi)
            off, sigma = np.array([dd * np.cos(aa), dd * np.sin(aa), 0.0]), hi / 2
        ground = self.world.height(S[None, :2])[0]
        self.p = np.array([S[0], S[1], ground + self.agl])
        self.v = SPEED * np.r_[d, 0.0]
        self.a = np.zeros(3)
        self.yaw = float(np.arctan2(d[1], d[0]))
        self.t = 0.0
        start = Pose(0.0, self.p + off, self.yaw, self.v.copy())
        ctx = Context("drone", sc["world"], MapView(self.map), start, sensor_spec(self.sensors_cfg), sigma, sc["id"])
        self.nav = navigator_cls(ctx)
        if getattr(self.map, "_info_grid", None) is None:
            self.map._info_grid = info_grid(self.map)
        self.info = self.map._info_grid
        self.trace = {"t": [], "truth": [], "est": [], "unc": [], "action": []} if record else None

    # --- what the policy sees (no ground truth)
    def observe(self):
        est = self.nav.estimate()
        u = self.nav.uncertainty()
        radius = 1000.0 if u is None or not np.isfinite(u) else float(u)
        p_lost = float(getattr(self.nav, "p_lost", 0.0))
        d_goal = float(np.linalg.norm(self.G - est[:2]))
        margin = self.nofly_off - float((est[:2] - self.S[:2]) @ self.n) - radius
        x0, y0, cell, I = self.info
        i = int(np.clip((est[1] - y0) / cell, 0, I.shape[0] - 1))
        j = int(np.clip((est[0] - x0) / cell, 0, I.shape[1] - 1))
        battery = 1 - self.t / self.battery_s
        return np.array([min(radius, 1000) / 100, p_lost, d_goal / 1000, np.clip(margin, -500, 500) / 100,
                         min(I[i, j], 50) / 10, battery, self.agl / 100, 1.0]), est, radius

    def _detour_target(self, est):
        x0, y0, cell, I = self.info
        best, val = est[:2], -1
        for dx in np.arange(-400, 401, 100):
            for dy in np.arange(-400, 401, 100):
                q = est[:2] + [dx, dy]
                if (q - self.S[:2]) @ self.n > self.nofly_off - 100:   # never detour toward the border
                    continue
                i = int(np.clip((q[1] - y0) / cell, 0, I.shape[0] - 1))
                j = int(np.clip((q[0] - x0) / cell, 0, I.shape[1] - 1))
                if I[i, j] > val:
                    best, val = q, I[i, j]
        return best

    # --- fly one decision period
    def _fly(self, target_xy, speed):
        """Fly one decision period. The autopilot re-reads the navigator's estimate every second (sensors are
        generated and fed second by second), so it steers by its belief, not by the truth."""
        n = int(1.0 / DT)
        for _ in range(int(DECISION_S)):
            est = self.p.copy() if getattr(self, "steer_by_truth", False) else self.nav.estimate()
            T, P, V, A, Y, W = (np.zeros(n), np.zeros((n, 3)), np.zeros((n, 3)), np.zeros((n, 3)), np.zeros(n), np.zeros((n, 3)))
            crossed = False
            for k in range(n):
                to = target_xy - est[:2] - (self.p[:2] - P[0, :2] if k else 0)   # dead-reckon within the second
                dist = np.linalg.norm(to)
                vxy = (to / max(dist, 1e-6)) * min(speed, dist / 3.0 + 0.5)
                ground = self.world.height(self.p[None, :2])[0]       # autopilot holds height above the true surface
                vcmd = np.r_[vxy, np.clip(0.8 * ((ground + self.agl) - self.p[2]), -4, 4)]
                w = self.wind.step()
                a_target = 1.2 * (vcmd - self.v) + 2 * DRAG_PER_M * 10 * (w - self.wind.mean)
                self.a = self.a + (a_target - self.a) * (DT / ACC_TAU_S)   # attitude can't jump: rate-limit it
                a = self.a
                if k == 0:
                    P[0] = self.p
                T[k], P[k], V[k], A[k], W[k] = self.t, self.p, self.v, a, w
                if np.linalg.norm(vxy) > 0.5:
                    self.yaw = float(np.arctan2(vxy[1], vxy[0]))
                Y[k] = self.yaw
                self.p = self.p + self.v * DT + 0.5 * a * DT * DT
                self.v = self.v + a * DT
                self.t += DT
                if (self.p[:2] - self.S[:2]) @ self.n > self.nofly_off:
                    crossed = True
                    T, P, V, A, Y, W = T[:k + 1], P[:k + 1], V[:k + 1], A[:k + 1], Y[:k + 1], W[:k + 1]
                    break
            if len(T) > 2:
                self._feed(self.sensors.generate(SegmentTrajectory(T, P, V, A, np.unwrap(Y), W)))
            if crossed:
                return True
            if np.linalg.norm(self.G - self.nav.estimate()[:2]) < 20:
                return False   # believes it has arrived: hand back to the decision step, which lands
        return False

    def _feed(self, data):
        nav = self.nav
        handlers = {
            "imu": lambda d, i: nav.on_imu(d["t"][i], d["acc"][i], d["gyro"][i]),
            "mag": lambda d, i: nav.on_mag(d["t"][i], d["field"][i]),
            "baro": lambda d, i: nav.on_baro(d["t"][i], float(d["altitude"][i])),
            "echo": lambda d, i: nav.on_echo(d["t"][i], d["ranges"][i]),
        }
        kinds = [k for k in EVENT_ORDER if k in data and len(data[k]["t"])]
        ts = np.concatenate([data[k]["t"] for k in kinds])
        kind_ix = np.concatenate([np.full(len(data[k]["t"]), j) for j, k in enumerate(kinds)])
        item_ix = np.concatenate([np.arange(len(data[k]["t"])) for k in kinds])
        for e in np.lexsort((kind_ix, ts)):
            handlers[kinds[kind_ix[e]]](data[kinds[kind_ix[e]]], item_ix[e])

    def run(self, policy):
        """policy(obs) -> action index. Returns the outcome (ground truth only used for scoring)."""
        reward, decisions = 0.0, []
        while True:
            obs, est, radius = self.observe()
            if np.linalg.norm(self.G - est[:2]) < 20:   # arrived (by its own belief): land
                act = 4
            elif self.t >= self.battery_s:
                err = float(np.linalg.norm(self.p[:2] - self.G))
                return Outcome(reward - 50 - min(err / 50, 100), False, False, True, err, False, decisions, self.t)
            else:
                act = int(policy(obs))
            decisions.append(ACTIONS[act])
            if self.record:
                self.trace["t"].append(self.t)
                self.trace["truth"].append(self.p.tolist())
                self.trace["est"].append(est.tolist())
                self.trace["unc"].append(radius)
                self.trace["action"].append(ACTIONS[act])
            reward -= 0.5
            if act == 4:
                err = float(np.linalg.norm(self.p[:2] - self.G))
                ok = err < GOAL_M
                silent = (not ok) and np.linalg.norm(self.G - est[:2]) < GOAL_M and radius < GOAL_M
                return Outcome(reward + (100 if ok else -min(err / 50, 100)), ok, False, False, err, silent, decisions, self.t)
            target, speed = self.G, SPEED
            if act == 1:
                self.agl = min(self.agl + 40, 160)
            elif act == 2:
                target = self._detour_target(est)
            elif act == 3:
                speed = SPEED / 2
            crossed = self._fly(target, speed)
            if crossed:
                err = float(np.linalg.norm(self.p[:2] - self.G))
                return Outcome(reward - 200, False, True, False, err, False, decisions, self.t)


# ------------------------------------------------------------------ policies
def continue_policy(obs):
    return 0


def rule_policy(obs):
    radius, p_lost, margin = obs[0] * 100, obs[1], obs[3] * 100
    if p_lost > 0.8 or margin < 0:
        return 4
    if radius > 50:
        return 2
    return 0


class MLPPolicy:
    def __init__(self, params, sizes=(8, 16, 5)):
        i, h, o = sizes
        p = np.asarray(params, float)
        self.W1 = p[: i * h].reshape(i, h)
        self.b1 = p[i * h: i * h + h]
        self.W2 = p[i * h + h: i * h + h + h * o].reshape(h, o)
        self.b2 = p[i * h + h + h * o:]

    @staticmethod
    def size(sizes=(8, 16, 5)):
        i, h, o = sizes
        return i * h + h + h * o + o

    def __call__(self, obs):
        return int(np.argmax(np.tanh(obs @ self.W1 + self.b1) @ self.W2 + self.b2))


class LinearPolicy:
    """action = argmax(obs @ W): 8 belief features x 5 actions = 40 weights, readable on a slide."""

    def __init__(self, params):
        self.W = np.asarray(params, float).reshape(8, 5)

    @staticmethod
    def size():
        return 40

    def __call__(self, obs):
        return int(np.argmax(obs @ self.W))


def episode(args):
    """(scenario, seed, navigator experiment, policy spec) -> Outcome as dict. Picklable for process pools."""
    sid, seed, experiment, spec = args
    from gpsfree.evaluate import load_algorithm
    nav_cls = load_algorithm(experiment)
    if isinstance(spec, str):
        policy = {"continue": continue_policy, "rule": rule_policy}[spec]
    else:
        policy = LinearPolicy(spec) if len(spec) == LinearPolicy.size() else MLPPolicy(spec)
    out = Mission(sid, seed, nav_cls).run(policy)
    return {"scenario": sid, "seed": seed, **out.__dict__}
