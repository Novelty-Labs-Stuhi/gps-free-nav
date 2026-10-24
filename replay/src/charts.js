// Time-linked 2D charts: hover previews a moment in the 3D views, click or drag seeks, and every
// chart draws the shared playhead.
import * as THREE from "three";
import { beamColor, beamLabel } from "./scene.js";

const PAD = { l: 50, r: 10, t: 6, b: 18 };

export function fmtM(v, signed = false) {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v), s = signed && v > 0 ? "+" : "";
  if (a >= 1000) return `${s}${(v / 1000).toFixed(a >= 1e4 ? 0 : 1)} km`;
  if (a >= 10) return `${s}${v.toFixed(0)} m`;
  if (a >= 1) return `${s}${v.toFixed(1)} m`;
  return `${s}${v.toFixed(2)} m`;
}

function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

export function bisect(ts, t) {
  let lo = 0, hi = ts.length - 1;
  if (t <= ts[0]) return 0;
  if (t >= ts[hi]) return hi;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    ts[mid] <= t ? (lo = mid) : (hi = mid);
  }
  return lo;
}

class TimelineCanvas {
  constructor(canvas, t0, t1, { onHover, onSeek, tip }) {
    Object.assign(this, { canvas, t0, t1, onHover, onSeek, tip });
    this.ctx = canvas.getContext("2d");
    this.time = t0;
    this.hover = null;
    let dragging = false;
    canvas.addEventListener("pointerdown", (e) => {
      dragging = true;
      canvas.setPointerCapture(e.pointerId);
      this.click?.(e);
      onSeek(this.tAt(e));
    });
    canvas.addEventListener("pointermove", (e) => {
      const t = this.tAt(e);
      if (dragging) onSeek(t);
      this.hover = { t, y: e.clientY - canvas.getBoundingClientRect().top };
      onHover(t);
      this.showTip(e);
    });
    canvas.addEventListener("pointerup", () => (dragging = false));
    canvas.addEventListener("pointerleave", () => {
      this.hover = null;
      tip.hidden = true;
      onHover(null);
    });
    new ResizeObserver(() => this.resize()).observe(canvas);
  }

  get w() { return this.canvas.clientWidth; }
  get h() { return this.canvas.clientHeight; }
  X(t) { return PAD.l + ((t - this.t0) / (this.t1 - this.t0)) * (this.w - PAD.l - PAD.r); }
  tAt(e) {
    const f = (e.clientX - this.canvas.getBoundingClientRect().left - PAD.l) / (this.w - PAD.l - PAD.r);
    return this.t0 + Math.min(1, Math.max(0, f)) * (this.t1 - this.t0);
  }

  resize() {
    const dpr = Math.min(devicePixelRatio, 2);
    this.canvas.width = this.w * dpr;
    this.canvas.height = this.h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.invalidate();
  }

  invalidate() {
    this.background = null;
    this.draw(this.time);
  }

  showTip(e) {
    const html = this.hover && this.tipHtml(this.hover.t, this.hover.y);
    if (!html) return void (this.tip.hidden = true);
    this.tip.innerHTML = html;
    this.tip.hidden = false;
    const r = this.tip.getBoundingClientRect();
    const x = e.clientX + 14 + r.width > innerWidth ? e.clientX - 14 - r.width : e.clientX + 14;
    this.tip.style.left = `${x}px`;
    this.tip.style.top = `${Math.max(4, e.clientY - r.height - 10)}px`;
  }

  timeAxis(c) {
    c.fillStyle = "#7d8796";
    c.textAlign = "center";
    const step = niceStep((this.t1 - this.t0) / Math.max(2, this.w / 70));
    for (let t = Math.ceil(this.t0 / step) * step; t <= this.t1; t += step) c.fillText(`${t.toFixed(0)} s`, this.X(t), this.h - 4);
  }

  // Static content is rendered once to an offscreen bitmap and blitted with the playhead on top.
  draw(time) {
    this.time = time;
    if (!this.canvas.width || !this.w) return;
    if (!this.background) {
      const off = new OffscreenCanvas(this.canvas.width, this.canvas.height);
      const c = off.getContext("2d");
      c.setTransform(this.canvas.width / this.w, 0, 0, this.canvas.height / this.h, 0, 0);
      c.font = "11px system-ui";
      this.renderBackground(c);
      this.background = off;
    }
    const c = this.ctx, w = this.w, h = this.h;
    c.clearRect(0, 0, w, h);
    c.drawImage(this.background, 0, 0, w, h);
    this.overlay?.(c);
    const x = this.X(time);
    c.fillStyle = "rgba(11,14,19,0.42)";
    c.fillRect(x, PAD.t, w - PAD.r - x, h - PAD.t - PAD.b);
    c.strokeStyle = "#f0f3f6";
    c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x, PAD.t); c.lineTo(x, h - PAD.b); c.stroke();
    if (this.hover) {
      const hx = this.X(this.hover.t);
      c.strokeStyle = "rgba(240,243,246,0.35)";
      c.setLineDash([3, 3]);
      c.beginPath(); c.moveTo(hx, PAD.t); c.lineTo(hx, h - PAD.b); c.stroke();
      c.setLineDash([]);
    }
  }
}

// Line chart of metric series against time; signed series plot their magnitude on a log axis.
export class TimeChart extends TimelineCanvas {
  constructor(canvas, t, metrics, series, opts) {
    super(canvas, t[0], t.at(-1), opts);
    Object.assign(this, { t, metrics, series, log: opts.log ?? true });
    this.hidden = new Set();
  }

  setLog(log) { this.log = log; this.invalidate(); }
  toggle(key) { this.hidden.has(key) ? this.hidden.delete(key) : this.hidden.add(key); this.invalidate(); }

  value(s, v) {
    if (v == null) return null;
    v = s.signed && this.log ? Math.abs(v) : v;
    return this.log && v <= 0 ? null : v;
  }

  range() {
    let lo = Infinity, hi = -Infinity;
    for (const s of this.series) {
      if (this.hidden.has(s.key)) continue;
      for (const raw of this.metrics[s.key] || []) {
        const v = this.value(s, raw);
        if (v == null) continue;
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
    if (!isFinite(lo)) return [0.1, 1];
    if (this.log) return [Math.pow(10, Math.floor(Math.log10(Math.max(lo, 0.01)))), Math.pow(10, Math.ceil(Math.log10(hi)))];
    const pad = (hi - lo) * 0.06 || 1;
    return [Math.min(0, lo - pad), hi + pad];
  }

  renderBackground(c) {
    const { w, h } = this;
    const [lo, hi] = this.range();
    const span = h - PAD.t - PAD.b;
    const Y = this.log
      ? (v) => PAD.t + (1 - (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * span
      : (v) => PAD.t + (1 - (v - lo) / (hi - lo)) * span;
    const ticks = [];
    if (this.log) {
      const every = Math.max(1, Math.ceil(Math.log10(hi / lo) / Math.max(2, span / 18)));
      for (let e = Math.log10(lo); e <= Math.log10(hi) + 1e-9; e += every) ticks.push(Math.pow(10, e));
    } else {
      const step = niceStep((hi - lo) / Math.max(2, span / 28));
      for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v);
    }
    c.strokeStyle = "#1e2530";
    c.lineWidth = 1;
    c.fillStyle = "#7d8796";
    c.textAlign = "right";
    for (const v of ticks) {
      const y = Y(v);
      c.strokeStyle = !this.log && Math.abs(v) < 1e-9 ? "#3a4555" : "#1e2530";
      c.beginPath(); c.moveTo(PAD.l, y); c.lineTo(w - PAD.r, y); c.stroke();
      c.fillText(fmtM(v), PAD.l - 5, y + 4);
    }
    this.timeAxis(c);
    c.save();
    c.beginPath();
    c.rect(PAD.l, PAD.t, w - PAD.l - PAD.r, span);
    c.clip();
    for (const s of this.series) {
      const vals = this.metrics[s.key];
      if (!vals || this.hidden.has(s.key)) continue;
      c.strokeStyle = s.color;
      c.lineWidth = s.width;
      c.beginPath();
      let pen = false;
      for (let i = 0; i < vals.length; i++) {
        const v = this.value(s, vals[i]);
        if (v == null) { pen = false; continue; }
        const x = this.X(this.t[i]), y = Y(v);
        pen ? c.lineTo(x, y) : c.moveTo(x, y);
        pen = true;
      }
      c.stroke();
    }
    c.restore();
  }

  tipHtml(t) {
    const i = bisect(this.t, t);
    return `<b>${(t - this.t0).toFixed(1)} s</b>` + this.series.filter((s) => !this.hidden.has(s.key))
      .map((s) => `<div><i style="background:${s.color}"></i>${s.label}<span>${fmtM(this.metrics[s.key]?.[i], s.signed)}</span></div>`).join("");
  }
}

// Every beam's residual (measured - map) over time: one row per beam, grouped by elevation.
export class BeamHeatmap extends TimelineCanvas {
  constructor(canvas, t, echo, opts) {
    super(canvas, t[0], t.at(-1), opts);
    this.echo = echo;
    this.onBeam = opts.onBeam;
    this.highlight = -1;
    const dirs = echo.dirs_body;
    const elev = (d) => Math.asin(Math.max(-1, Math.min(1, d[2])));
    const az = (d) => (Math.atan2(d[1], d[0]) + 2 * Math.PI) % (2 * Math.PI);
    this.order = dirs.map((_, i) => i).sort((a, b) => elev(dirs[b]) - elev(dirs[a]) || az(dirs[a]) - az(dirs[b]));
    this.row = new Array(dirs.length);
    this.order.forEach((b, r) => (this.row[b] = r));
    this.image = this.buildImage();
  }

  buildImage() {
    const { measured, predicted } = this.echo, k = measured.length, n = this.order.length;
    const img = new ImageData(k, n), c = new THREE.Color();
    for (let j = 0; j < k; j++) {
      for (let r = 0; r < n; r++) {
        const b = this.order[r], m = measured[j][b], p = predicted[j][b];
        const o = (r * k + j) * 4;
        if (m == null) { img.data.set([24, 29, 37, 255], o); continue; }
        beamColor(m, p, c);
        img.data.set([c.r * 255, c.g * 255, c.b * 255, 255], o);
      }
    }
    const off = new OffscreenCanvas(k, n);
    off.getContext("2d").putImageData(img, 0, 0);
    return off;
  }

  rowHeight() { return (this.h - PAD.t - PAD.b) / this.order.length; }
  beamAt(y) {
    const r = Math.floor((y - PAD.t) / this.rowHeight());
    return r >= 0 && r < this.order.length ? this.order[r] : -1;
  }

  renderBackground(c) {
    const et = this.echo.t, x0 = this.X(et[0]), x1 = this.X(et.at(-1) + (et[1] - et[0] || 0.1));
    c.imageSmoothingEnabled = false;
    c.drawImage(this.image, x0, PAD.t, x1 - x0, this.h - PAD.t - PAD.b);
    // Elevation group labels and separators.
    c.fillStyle = "#7d8796";
    c.textAlign = "right";
    c.strokeStyle = "#0b0e13";
    const rh = this.rowHeight();
    let prev = null, start = 0;
    const groups = [];
    this.order.forEach((b, r) => {
      const lab = beamLabel(this.echo.dirs_body[b]).split(" az")[0];
      if (lab !== prev) { if (prev != null) groups.push([prev, start, r]); prev = lab; start = r; }
    });
    groups.push([prev, start, this.order.length]);
    for (const [lab, a, z] of groups) {
      c.fillText(lab.replace("el ", ""), PAD.l - 5, PAD.t + ((a + z) / 2) * rh + 4);
      c.beginPath(); c.moveTo(PAD.l, PAD.t + a * rh); c.lineTo(this.w - PAD.r, PAD.t + a * rh); c.stroke();
    }
    this.timeAxis(c);
  }

  overlay(c) {
    if (this.highlight < 0) return;
    const rh = this.rowHeight(), y = PAD.t + this.row[this.highlight] * rh;
    c.strokeStyle = "#ffffff";
    c.lineWidth = 1;
    c.strokeRect(PAD.l + 0.5, y - 0.5, this.w - PAD.l - PAD.r - 1, Math.max(2, rh) + 1);
  }

  click(e) {
    const b = this.beamAt(e.clientY - this.canvas.getBoundingClientRect().top);
    if (b >= 0 && e.shiftKey) this.onBeam(b === this.highlight ? -1 : b);
  }

  tipHtml(t, y) {
    const b = this.beamAt(y);
    if (b < 0) return null;
    const j = bisect(this.echo.t, t), m = this.echo.measured[j][b], p = this.echo.predicted[j][b];
    return `<b>${beamLabel(this.echo.dirs_body[b])}</b> · ${(t - this.t0).toFixed(1)} s
      <div>measured<span>${m == null ? "no echo" : fmtM(m)}</span></div>
      <div>map predicts<span>${p == null ? "no hit" : fmtM(p)}</span></div>
      <div>residual<span>${m != null && p != null ? fmtM(m - p, true) : "–"}</span></div>
      <div class="muted">shift-click to highlight this beam</div>`;
  }
}
