// Time-series chart of the run's error metrics on a 2D canvas, with a cursor at the playback time.
// Click or drag to seek.

export const SERIES = [
  { key: "err", label: "error", color: "#ff4d6d", width: 1.6 },
  { key: "geo_mean_err", label: "running geo-mean error", color: "#ffffff", width: 2 },
  { key: "dev_xy", label: "est vs truth, horizontal", color: "#58a6ff", width: 1 },
  { key: "dev_z", label: "est vs truth, vertical", color: "#c792ea", width: 1, signed: true },
  { key: "dev_plan", label: "truth vs planned", color: "#ffd23f", width: 1 },
];

const PAD = { l: 52, r: 12, t: 6, b: 20 };

export class Chart {
  constructor(canvas, replay, onSeek) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.t = replay.t;
    this.metrics = replay.metrics;
    this.log = true;
    this.onSeek = onSeek;
    this.time = this.t[0];
    let dragging = false;
    const seek = (e) => {
      const r = canvas.getBoundingClientRect();
      const f = (e.clientX - r.left - PAD.l) / (r.width - PAD.l - PAD.r);
      onSeek(this.t[0] + Math.min(1, Math.max(0, f)) * (this.t.at(-1) - this.t[0]));
    };
    canvas.addEventListener("pointerdown", (e) => { dragging = true; canvas.setPointerCapture(e.pointerId); seek(e); });
    canvas.addEventListener("pointermove", (e) => dragging && seek(e));
    canvas.addEventListener("pointerup", () => (dragging = false));
    new ResizeObserver(() => this.resize()).observe(canvas);
  }

  resize() {
    const dpr = Math.min(devicePixelRatio, 2);
    this.canvas.width = this.canvas.clientWidth * dpr;
    this.canvas.height = this.canvas.clientHeight * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.background = null;
    this.draw(this.time);
  }

  setLog(log) {
    this.log = log;
    this.background = null;
    this.draw(this.time);
  }

  value(s, v) {
    if (v == null) return null;
    return s.signed && this.log ? Math.abs(v) : v;
  }

  range() {
    let lo = Infinity, hi = -Infinity;
    for (const s of SERIES) for (const raw of this.metrics[s.key] || []) {
      const v = this.value(s, raw);
      if (v == null || (this.log && v <= 0)) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    if (!isFinite(lo)) return [0.1, 1];
    if (this.log) return [Math.pow(10, Math.floor(Math.log10(Math.max(lo, 0.01)))), Math.pow(10, Math.ceil(Math.log10(hi)))];
    return [Math.min(0, lo), hi * 1.05 || 1];
  }

  // Axes and series are static: render them once into an offscreen bitmap and blit per frame.
  renderBackground() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    const off = new OffscreenCanvas(this.canvas.width, this.canvas.height);
    const c = off.getContext("2d");
    c.setTransform(this.canvas.width / w, 0, 0, this.canvas.height / h, 0, 0);
    const [lo, hi] = this.range();
    const t0 = this.t[0], t1 = this.t.at(-1);
    const X = (t) => PAD.l + ((t - t0) / (t1 - t0)) * (w - PAD.l - PAD.r);
    const Y = this.log
      ? (v) => PAD.t + (1 - (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (h - PAD.t - PAD.b)
      : (v) => PAD.t + (1 - (v - lo) / (hi - lo)) * (h - PAD.t - PAD.b);
    this.X = X;

    c.font = "11px system-ui";
    c.fillStyle = "#8a94a3";
    c.strokeStyle = "#262c36";
    c.lineWidth = 1;
    const ticks = [];
    if (this.log) for (let e = Math.log10(lo); e <= Math.log10(hi) + 1e-9; e++) ticks.push(Math.pow(10, e));
    else { const step = niceStep((hi - lo) / 5); for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v); }
    c.textAlign = "right";
    for (const v of ticks) {
      const y = Y(v);
      c.beginPath(); c.moveTo(PAD.l, y); c.lineTo(w - PAD.r, y); c.stroke();
      c.fillText(fmtM(v), PAD.l - 4, y + 4);
    }
    c.textAlign = "center";
    const tstep = niceStep((t1 - t0) / 10);
    for (let t = Math.ceil(t0 / tstep) * tstep; t <= t1; t += tstep) c.fillText(`${t.toFixed(0)} s`, X(t), h - 5);

    for (const s of SERIES) {
      const vals = this.metrics[s.key];
      if (!vals) continue;
      c.strokeStyle = s.color;
      c.lineWidth = s.width;
      c.beginPath();
      let pen = false;
      for (let i = 0; i < vals.length; i++) {
        const v = this.value(s, vals[i]);
        if (v == null || (this.log && v <= 0)) { pen = false; continue; }
        const y = Math.min(h - PAD.b, Math.max(PAD.t, Y(v)));
        pen ? c.lineTo(X(this.t[i]), y) : c.moveTo(X(this.t[i]), y);
        pen = true;
      }
      c.stroke();
    }
    this.background = off;
  }

  draw(time) {
    this.time = time;
    if (!this.canvas.width) return;
    if (!this.background) this.renderBackground();
    const c = this.ctx, w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    c.clearRect(0, 0, w, h);
    c.drawImage(this.background, 0, 0, w, h);
    const x = this.X(time);
    c.fillStyle = "rgba(14,17,22,0.45)";
    c.fillRect(x, PAD.t, w - PAD.r - x, h - PAD.t - PAD.b);
    c.strokeStyle = "#e6edf3";
    c.lineWidth = 1;
    c.beginPath(); c.moveTo(x, PAD.t); c.lineTo(x, h - PAD.b); c.stroke();
  }
}

function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

export function fmtM(v) {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1000) return `${(v / 1000).toFixed(a >= 1e4 ? 0 : 1)} km`;
  if (a >= 10) return `${v.toFixed(0)} m`;
  if (a >= 1) return `${v.toFixed(1)} m`;
  return `${v.toFixed(2)} m`;
}
