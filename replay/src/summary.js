// Run-level numbers shared by the page and the dev server (vite.config.js builds the run index with
// them), so this module must not import anything browser-only.

export const ALERT_M = 50;          // suite lost_threshold_m: the horizontal alert limit
export const TIME_TO_ALERT_S = 6;   // ICAO LPV-200 time-to-alert: how long misleading output may last
const SPARK_POINTS = 60;

// "Agrees" means within 3 sigma of the suite's echo noise (0.05 m + 1 % of range).
export const agreeBand = (range) => 3 * (0.05 + 0.01 * range);

// The method's reported 95 % horizontal radius per pose: a number, Infinity ("inf": I don't know
// where I am) or null (no claim). Returns null when the replay has no uncertainty field at all.
export function uncertaintyOf(R) {
  if (!Array.isArray(R.uncertainty)) return null;
  return R.uncertainty.map((u) => (u === "inf" || u === Infinity ? Infinity : typeof u === "number" ? u : null));
}

const claims = (u) => u != null && isFinite(u);
// An alarm is the method saying its position is not good enough: lost, or a radius past the limit.
const alarm = (u) => u != null && u >= ALERT_M;

// Integrity of the reported radius against the true error.
// - misleading: the error is outside the radius, as a share of the time a finite radius was claimed.
// - hazardous (HMI): error over the alert limit while the radius says it is within it.
// - silent: "yes" if a hazardous episode outlasts the time-to-alert without an alarm, "late" if the
//   alarm came but after the time-to-alert, "no" otherwise, null if the method never claims a radius.
export function integrity(t, err, unc) {
  const n = t.length, dt = n > 1 ? (t[n - 1] - t[0]) / (n - 1) : 0;
  const hmi = new Array(n).fill(false);
  if (!unc) return { hmi, claimed: false, misleading: null, claimS: 0, hmiS: 0, silent: null, firstHmiT: null, lostT: null, alarmT: null };
  let claimed = 0, outside = 0, hmiN = 0, firstHmi = -1, lost = -1;
  for (let i = 0; i < n; i++) {
    const u = unc[i], e = err[i];
    if (u === Infinity && lost < 0) lost = i;
    if (!claims(u)) continue;
    claimed++;
    if (e == null) continue;
    if (e > u) outside++;
    if (e > ALERT_M && u < ALERT_M) {
      hmi[i] = true;
      hmiN++;
      if (firstHmi < 0) firstHmi = i;
    }
  }
  // Walk the hazardous episodes and see how each one ended.
  let silent = claimed ? "no" : null, alarmT = null;
  for (let i = 0; i < n;) {
    if (!hmi[i]) { i++; continue; }
    let j = i;
    while (j < n && hmi[j]) j++;
    const long = (j - i) * dt > TIME_TO_ALERT_S, alarmed = j < n && alarm(unc[j]);
    if (alarmed && alarmT == null) alarmT = t[j];
    if (long && !alarmed) silent = "yes";
    else if (long && silent === "no") silent = "late";
    i = j;
  }
  return {
    hmi, claimed: claimed > 0, misleading: claimed ? outside / claimed : null, claimS: claimed * dt, hmiS: hmiN * dt,
    silent, firstHmiT: firstHmi >= 0 ? t[firstHmi] : null, lostT: lost >= 0 ? t[lost] : null, alarmT,
  };
}

const last = (xs) => { for (let i = xs.length - 1; i >= 0; i--) if (xs[i] != null) return xs[i]; return null; };
const rnd = (v, nd = 2) => (v == null || !isFinite(v) ? null : Math.round(v * 10 ** nd) / 10 ** nd);

// Compact per-run numbers for the run browser, from a parsed replay.json.
export function runSummary(R) {
  const t = R.t || [], err = R.metrics?.err || [], n = t.length;
  const dt = n > 1 ? (t[n - 1] - t[0]) / (n - 1) : 0;
  const vals = err.filter((e) => e != null);
  let agree = 0, total = 0;
  (R.echo?.measured || []).forEach((row, j) => row.forEach((m, b) => {
    if (m == null) return;
    total++;
    const p = R.echo.predicted[j][b];
    if (p != null && Math.abs(m - p) <= agreeBand(p)) agree++;
  }));
  // Sparkline: max error in each bucket, so short excursions still show.
  const k = Math.max(1, Math.ceil(err.length / SPARK_POINTS)), spark = [];
  for (let i = 0; i < err.length; i += k) {
    const xs = err.slice(i, i + k).filter((e) => e != null);
    spark.push(xs.length ? rnd(Math.max(...xs), xs[0] < 10 ? 2 : 0) : null);
  }
  const I = integrity(t, err, uncertaintyOf(R));
  return {
    scenario_name: R.scenario_name ?? null,
    score_m: rnd(R.score_m ?? last(R.metrics?.geo_mean_err || [])),
    final_err_m: rnd(last(err)),
    worst_err_m: rnd(vals.length ? Math.max(...vals) : null),
    time_over_50_s: rnd(vals.filter((e) => e > ALERT_M).length * dt, 1),
    duration_s: n ? rnd(t[n - 1] - t[0], 1) : null,
    echo_agree: total ? rnd(agree / total, 3) : null,
    misleading: rnd(I.misleading, 3),
    silent_failure: I.silent,
    hmi_s: rnd(I.hmiS, 1),
    declared_lost_s: I.lostT != null ? rnd(I.lostT - t[0], 1) : null,
    err: spark,
  };
}
