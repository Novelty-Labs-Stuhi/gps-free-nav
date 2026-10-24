// The run browser: every replay in data/replays/index.json, grouped by experiment, filterable by
// scenario/world/text, with the numbers that rank a run visible without opening it. When collapsed it
// becomes a rail of grade-coloured dots that still switches runs with one click.
import { fmtM } from "./charts.js";

export const LOST_M = 50;  // suite lost_threshold_m
export const grade = (m) => (m == null ? "none" : m < 10 ? "good" : m < LOST_M ? "warn" : "bad");
export const fmtS = (s) => (s == null ? "–" : s >= 100 ? `${s.toFixed(0)} s` : `${s.toFixed(s && s < 10 ? 1 : 0)} s`);
export const fmtPct = (f) => (f == null ? "–" : `${(f * 100).toFixed(f > 0.995 && f < 1 ? 1 : 0)}%`);

// Index entries are objects; very old indexes were "<experiment>/<run_id>" strings. Summary fields are
// optional, so an index written before they existed still lists every run.
// The run's integrity verdict at a glance: did it ever believe a wrong position without saying so?
function integrityBadge(e) {
  if (e.silent_failure === "yes") return `<b class="badge bad" title="Error over ${LOST_M} m while claiming to be within it, for ${fmtS(e.hmi_s)}">silent failure</b>`;
  if (e.silent_failure === "late") return `<b class="badge warn" title="Declared itself lost, but only after the time-to-alert">late alarm</b>`;
  if (e.declared_lost_s != null) return `<b class="badge muted" title="Declared itself lost at ${fmtS(e.declared_lost_s)}">declares lost</b>`;
  return "";
}

export function normalizeEntry(e) {
  if (typeof e === "string") e = { id: e };
  const [experiment = "?", run_id = e.id] = e.id.split("/");
  e = { experiment, run_id, scenario: "–", ...e };
  // run_id is "<world>__<route>__s<seed>" from export_sample.py; other ids keep whatever parts don't
  // repeat the world or scenario, so "boreal__r00" in scenario boreal reads "r00".
  const parts = e.run_id.split("__");
  e.world ??= parts.length === 3 ? parts[0] : "–";
  e.seed = parts.length > 1 && /^s\d+$/.test(parts.at(-1)) ? parts.pop().slice(1) : null;
  const rest = parts.filter((p) => p !== e.world && p !== e.scenario);
  e.route = (rest.length ? rest : parts).join(" · ");
  e.haystack = [e.experiment, e.scenario, e.scenario_name, e.world, e.run_id].filter(Boolean).join(" ").toLowerCase();
  return e;
}

// Log-scaled error sparkline with the lost threshold dashed, as inline SVG.
function sparkline(err) {
  const pts = (err || []).map((v) => (v == null ? null : Math.log10(Math.max(v, 0.05))));
  const vals = pts.filter((v) => v != null);
  if (vals.length < 2) return "";
  const lostY = Math.log10(LOST_M);
  const lo = Math.min(...vals, -1), hi = Math.max(...vals, lostY + 0.3), W = 64, H = 20;
  const y = (v) => (H - 1.5 - ((v - lo) / (hi - lo)) * (H - 3)).toFixed(1);
  const x = (i) => ((i / (pts.length - 1)) * W).toFixed(1);
  let d = "";
  pts.forEach((v, i) => { if (v != null) d += `${d && pts[i - 1] != null ? "L" : "M"}${x(i)} ${y(v)}`; });
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" x2="${W}" y1="${y(lostY)}" y2="${y(lostY)}" class="lost" />
    <path d="${d}" /></svg>`;
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const uniq = (xs) => [...new Set(xs)].sort();

export class RunBrowser {
  constructor(root, entries, { prefs, savePrefs, onPick }) {
    Object.assign(this, { root, entries, prefs, savePrefs, onPick });
    this.current = null;
    this.query = "";
    this.list = root.querySelector("#runList");
    this.rail = root.querySelector("#railRuns");
    this.search = root.querySelector("#search");
    this.search.oninput = () => { this.query = this.search.value.trim().toLowerCase(); this.render(); };
    this.search.onkeydown = (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); this.step(e.key === "ArrowDown" ? 1 : -1); }
      if (e.key === "Enter") { const v = this.visible(); if (v.length && !v.includes(this.cur())) this.pick(v[0].id); this.search.blur(); }
      if (e.key === "Escape") { e.stopPropagation(); this.search.value ? (this.search.value = "", this.search.oninput()) : this.search.blur(); }
    };
    root.querySelectorAll("[data-sort]").forEach((b) => (b.onclick = () => {
      prefs.sort = b.dataset.sort;
      savePrefs();
      this.render();
    }));
    this.renderFilters();
    this.render();
  }

  cur() { return this.entries.find((e) => e.id === this.current); }

  // Unknown ids (a deep link to a run missing from the index) still get a row.
  setCurrent(id) {
    if (!this.entries.some((e) => e.id === id)) this.entries.unshift(normalizeEntry(id));
    this.current = id;
    this.render();
    this.root.querySelector(".run.on")?.scrollIntoView({ block: "nearest" });
  }

  pick(id) { if (id !== this.current) this.onPick(id); }

  filters() { return this.prefs.runFilter || (this.prefs.runFilter = {}); }

  renderFilters() {
    const holder = this.root.querySelector("#filters"), f = this.filters();
    holder.replaceChildren();
    for (const key of ["scenario", "world"]) {
      const values = uniq(this.entries.map((e) => e[key]));
      if (!values.includes(f[key])) delete f[key];
      // Scenario is always offered (it's the axis the benchmark varies); world only once there are several.
      if (key === "world" && values.length < 2) continue;
      const row = document.createElement("div");
      row.className = "filter";
      row.innerHTML = `<span>${key}</span>`;
      for (const v of [null, ...values]) {
        const b = document.createElement("button");
        const n = v == null ? this.entries.length : this.entries.filter((e) => e[key] === v).length;
        b.className = `chip small${(f[key] ?? null) === v ? " on" : ""}`;
        b.innerHTML = `${esc(v ?? "all")}<em>${n}</em>`;
        b.onclick = () => {
          v == null ? delete f[key] : (f[key] = v);
          this.savePrefs();
          this.renderFilters();
          this.render();
        };
        row.append(b);
      }
      holder.append(row);
    }
  }

  // Runs passing the filters, in display order (groups, then rows): what ↑/↓ walks through.
  visible() {
    const f = this.filters(), words = this.query.split(/\s+/).filter(Boolean);
    const rows = this.entries.filter((e) => (!f.scenario || e.scenario === f.scenario) && (!f.world || e.world === f.world)
      && words.every((w) => e.haystack.includes(w)));
    const byScore = this.prefs.sort === "score";
    const score = (e) => e.score_m ?? Infinity;
    // With several scenarios on show, each experiment is split into scenario sub-groups.
    this.splitScenario = !f.scenario && uniq(this.entries.map((e) => e.scenario)).length > 1;
    const sub = (a, b) => (this.splitScenario ? a.scenario.localeCompare(b.scenario) : 0);
    const groups = new Map();
    for (const e of rows) (groups.get(e.experiment) || groups.set(e.experiment, []).get(e.experiment)).push(e);
    const ordered = [...groups.entries()].map(([exp, runs]) => {
      runs.sort(byScore ? (a, b) => sub(a, b) || score(a) - score(b) || a.id.localeCompare(b.id) : (a, b) => sub(a, b) || a.id.localeCompare(b.id));
      return { exp, runs, best: Math.min(...runs.map(score)) };
    });
    ordered.sort(byScore ? (a, b) => a.best - b.best || a.exp.localeCompare(b.exp) : (a, b) => a.exp.localeCompare(b.exp));
    this.groups = ordered;
    return ordered.flatMap((g) => (this.prefs.collapsed?.[g.exp] && !g.runs.some((e) => e.id === this.current) ? [] : g.runs));
  }

  step(dir) {
    const v = this.visible();
    if (!v.length) return;
    const i = v.findIndex((e) => e.id === this.current);
    const next = v[i < 0 ? 0 : Math.min(v.length - 1, Math.max(0, i + dir))];
    this.pick(next.id);
  }

  render() {
    this.visible();
    const groups = this.groups, total = this.entries.length;
    const multiWorld = !this.filters().world && uniq(this.entries.map((e) => e.world)).length > 1;
    this.root.querySelectorAll("[data-sort]").forEach((b) => b.classList.toggle("on", (this.prefs.sort || "name") === b.dataset.sort));
    const shown = groups.reduce((n, g) => n + g.runs.length, 0);
    this.root.querySelector("#runCount").textContent = shown === total ? `${total} run${total === 1 ? "" : "s"}` : `${shown} of ${total} runs`;

    if (!total) {
      this.list.innerHTML = `<div class="empty"><b>No replays yet</b><p>Export one with</p>
        <code>uv run python replay/export_sample.py ins_compass</code></div>`;
      this.rail.replaceChildren();
      return;
    }
    if (!groups.length) {
      this.list.innerHTML = `<div class="empty"><b>No runs match</b><p>Try a different search or filter.</p><button id="clearFilters">Clear filters</button></div>`;
      this.list.querySelector("#clearFilters").onclick = () => {
        this.prefs.runFilter = {};
        this.savePrefs();
        this.search.value = this.query = "";
        this.renderFilters();
        this.render();
      };
    } else {
      this.list.replaceChildren(...groups.map((g) => this.renderGroup(g, multiWorld)));
    }

    // The rail mirrors the list as dots so a collapsed sidebar can still switch runs.
    this.rail.replaceChildren(...groups.map((g) => {
      const box = document.createElement("div");
      box.className = "rail-group";
      box.title = g.exp;
      for (const e of g.runs) {
        const b = document.createElement("button");
        b.className = `dot ${grade(e.score_m)}${e.id === this.current ? " on" : ""}`;
        b.title = `${e.experiment} / ${e.route}${e.seed != null ? ` · seed ${e.seed}` : ""}\nscore ${fmtM(e.score_m)} · ${e.scenario}`;
        b.onclick = () => this.pick(e.id);
        box.append(b);
      }
      return box;
    }));
  }

  renderGroup(g, multiWorld) {
    const collapsed = !!this.prefs.collapsed?.[g.exp];
    const sec = document.createElement("section");
    sec.className = `group${collapsed ? " collapsed" : ""}`;
    const head = document.createElement("button");
    head.className = "group-head";
    head.title = collapsed ? "Expand" : "Collapse";
    head.innerHTML = `<svg viewBox="0 0 10 10" class="chev"><path d="M3 2l4 3-4 3" /></svg>
      <b>${esc(g.exp)}</b><span>${g.runs.length}</span>
      ${isFinite(g.best) ? `<em class="${grade(g.best)}" title="Best score in this group">best ${fmtM(g.best)}</em>` : ""}`;
    head.onclick = () => {
      this.prefs.collapsed = { ...this.prefs.collapsed, [g.exp]: !collapsed };
      this.savePrefs();
      this.render();
    };
    sec.append(head);
    if (collapsed) {
      // Keep the current run visible even inside a collapsed group.
      const cur = g.runs.find((e) => e.id === this.current);
      if (cur) sec.append(this.renderRow(cur));
      return sec;
    }
    let scen = null;
    for (const e of g.runs) {
      if (this.splitScenario && e.scenario !== scen) {
        scen = e.scenario;
        const h = document.createElement("div");
        h.className = "subgroup";
        const worlds = uniq(g.runs.filter((x) => x.scenario === scen).map((x) => x.world));
        const name = g.runs.find((x) => x.scenario === scen)?.scenario_name;
        h.innerHTML = `${esc(name || scen)}${multiWorld ? `<span>${esc(worlds.join(", "))}</span>` : ""}`;
        sec.append(h);
      }
      sec.append(this.renderRow(e));
    }
    return sec;
  }

  renderRow(e) {
    const b = document.createElement("button");
    const g = grade(e.score_m), on = e.id === this.current;
    b.className = `run ${g}${on ? " on" : ""}`;
    b.dataset.id = e.id;
    if (on) b.setAttribute("aria-current", "true");
    const has = e.score_m !== undefined;
    if (!has) b.classList.add("bare");
    const meta = has
      ? `<span title="Final error">final <b>${fmtM(e.final_err_m)}</b></span>
         <span title="Time with error over ${LOST_M} m" class="${e.time_over_50_s > 0 ? "bad" : ""}">lost <b>${fmtS(e.time_over_50_s)}</b></span>
         <span title="Returned echoes that agree with the map">echo <b>${fmtPct(e.echo_agree)}</b></span>`
      : `<span title="This index entry predates run summaries; re-run update_index() in replay/export_sample.py">${esc(e.scenario)} · ${esc(e.world)} · no summary yet</span>`;
    b.innerHTML = `
      <span class="name">${esc(e.route)}${e.seed != null ? `<small>s${esc(e.seed)}</small>` : ""}${integrityBadge(e)}</span>
      ${sparkline(e.err)}
      <span class="score" title="Score: geometric-mean error">${has ? fmtM(e.score_m) : ""}</span>
      <span class="meta">${meta}</span>`;
    b.title = `${e.id}\n${e.scenario} · ${e.world}`;
    b.onclick = () => this.pick(e.id);
    return b;
  }
}
