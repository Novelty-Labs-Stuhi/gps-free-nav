"""Experiment viewer: data/viz/index.html plus per-run files it loads on demand.

Shows the leaderboard (overall and per scenario, with integrity), every run's true and estimated path on
a shaded relief of its world, error and reported uncertainty along the route, and the saved studies.
Run trajectories come from data/runs/<experiment>/ (written by `gpsfree eval`); missing ones are skipped."""
import base64
import io
import json

import numpy as np
from PIL import Image

from gpsfree.evaluate import load_scenario, load_suite, suite_fingerprint, suite_scenarios
from gpsfree.paths import DATA, EXPERIMENTS, RUNS
from gpsfree.studies import STUDIES
from gpsfree.trajectory import path_length
from gpsfree.world import World

VIZ = DATA / "viz"
VIZ_HZ = 2


def _relief(world: World, n=384):
    (x0, y0, _), (x1, y1, _) = world.meta["bounds"]
    xs, ys = np.linspace(x0, x1, n), np.linspace(y1, y0, n)  # image rows go north -> south
    gx, gy = np.meshgrid(xs, ys)
    h = world.height(np.c_[gx.ravel(), gy.ravel()]).reshape(n, n)
    h = np.where(np.isfinite(h), h, np.nanmin(h[np.isfinite(h)]))
    dy, dx = np.gradient(h, (y1 - y0) / n, (x1 - x0) / n)
    slope, aspect = np.arctan(np.hypot(dx, dy)), np.arctan2(dy, -dx)
    az, alt = np.radians(315), np.radians(45)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    t = (h - h.min()) / max(np.ptp(h), 1)
    lo, hi = np.array([214, 222, 196]), np.array([150, 130, 110])
    rgb = (lo + (hi - lo) * t[..., None]) * (0.45 + 0.55 * shade[..., None])
    buf = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(buf, "PNG")
    return {"png": base64.b64encode(buf.getvalue()).decode(), "bounds": [x0, y0, x1, y1]}


def _run_file(exp, sid, i):
    return RUNS / exp / f"{sid}__r{i:02d}.json"


def build(experiments=None, jobs=None):
    suite = load_suite()
    current = suite_fingerprint()
    results = {}
    for p in sorted(EXPERIMENTS.glob("*/results.json")):
        r = json.loads(p.read_text())
        if (not experiments or r["experiment"] in experiments) and "overall" in r.get("summary", {}):
            results[r["experiment"]] = r
    scen = suite_scenarios(suite)
    scenarios = [{"id": s, **{k: load_scenario(s)[k] for k in ("name", "world", "description")}} for s in scen]
    step = int(round(suite["score_rate_hz"] / VIZ_HZ))
    available = {}
    for exp, r in results.items():
        for run in r["runs"]:
            f = _run_file(exp, run["scenario"], run["run"])
            if not f.exists():
                continue
            d = json.loads(f.read_text())
            truth, est = np.array(d["truth"]), np.array(d["estimate"])
            unc = d.get("uncertainty") or [None] * len(truth)
            sl = slice(None, None, step)
            out = VIZ / "runs" / exp / f.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "t": np.round(np.array(d["t"])[sl], 1).tolist(),
                "truth": np.round(truth[sl, :2], 1).tolist(), "est": np.round(est[sl, :2], 1).tolist(),
                "err": np.round(np.linalg.norm(est - truth, axis=1)[sl], 2).tolist(),
                "dist": np.round(path_length(truth)[sl], 1).tolist(),
                "unc": unc[::step], "score": d.get("score_log10")}, separators=(",", ":")))
            available.setdefault(exp, []).append(f"{run['scenario']}__r{run['run']:02d}")
    worlds = {sc["world"]: _relief(World(sc["world"])) for sc in scenarios}
    from gpsfree.algorithm import Algorithm
    from gpsfree.evaluate import load_algorithm
    board = [{"exp": e, "hardware": r.get("hardware"), "stale": r["suite"] != current, "summary": r["summary"],
              "ranger": r.get("ranger") if load_algorithm(e).on_echo is not Algorithm.on_echo else None}
             for e, r in results.items()]
    studies = [json.loads(p.read_text()) for p in sorted(STUDIES.glob("*.json"))]
    payload = json.dumps({"suite": current, "runs_per_scenario": suite["runs_per_scenario"], "floor": suite["error_floor_m"],
                          "alert": suite["lost_threshold_m"], "scenarios": scenarios, "worlds": worlds, "board": board,
                          "available": available, "studies": studies}, separators=(",", ":"))
    out = VIZ / "index.html"
    out.write_text(TEMPLATE.replace("/*DATA*/null", payload))
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>gpsfree runs</title>
<style>
:root{--bg:#f6f5f1;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e0d8;--truth:#111}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--panel:#21211e;--ink:#ecebe6;--muted:#9a9990;--line:#34332f;--truth:#fff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:18px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0}select,button{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
main{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:16px 20px}
@media (max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px}
.exp{display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer;font-size:13px}
.sw{width:12px;height:12px;border-radius:3px;flex:none}.exp .s{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
.right{display:grid;gap:16px;min-width:0}
h2{font-size:15px;margin:22px 0 10px}.study{display:grid;gap:10px;margin-bottom:16px}.study h3{margin:0;font-size:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:900px){.two{grid-template-columns:1fr}}.two canvas{height:240px}canvas{width:100%;display:block;border-radius:8px}
#map{aspect-ratio:1.6;cursor:grab;background:#ccc}#chart{height:260px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.muted{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right}td:first-child,th:first-child{text-align:left}
input[type=range]{flex:1;min-width:160px}
</style></head><body>
<header><h1>gpsfree · benchmark viewer</h1>
<label>scenario <select id="route"></select></label><label>run <select id="seed"></select></label>
<span class="muted" id="suite"></span></header>
<main>
<div class="card"><div class="muted" style="margin-bottom:6px">Experiments · run score in m (click to toggle)</div><div id="exps"></div>
<div class="row" style="margin-top:10px"><button id="all">all</button><button id="none">none</button></div></div>
<div class="right">
<div class="card"><canvas id="map"></canvas>
<div class="row" style="margin-top:8px"><button id="play">▶</button><input type="range" id="time" min="0" max="1000" value="1000"><span id="tlabel" class="muted"></span>
<button id="fit">fit truth</button></div>
<div class="muted">Black = true path. Dot = position at the slider time. Drag to pan, scroll to zoom.</div></div>
<div class="card"><canvas id="chart"></canvas><div class="muted">True 3D error (m, log scale) vs distance travelled, selected run. Shaded band: the 95% radius the method reports (top of chart = "I don't know"). Dashed red: alert limit.</div></div>
<div class="card"><div class="muted" id="desc" style="margin-bottom:8px"></div><table id="board"></table></div>
<div class="card"><div class="muted" style="margin-bottom:6px">Median score per scenario (m). Colour: green good, red bad (log scale).</div><div style="overflow-x:auto"><table id="matrix"></table></div></div>
</div></main>
<section id="studies" style="padding:0 20px 30px"></section>
<script>
const D=/*DATA*/null;
const mfmt=v=>(v>=1000?(v/1000).toLocaleString(undefined,{maximumFractionDigits:1})+" km":v.toLocaleString(undefined,{maximumFractionDigits:2})+" m");
const PAL=["#1f77b4","#d62728","#2ca02c","#ff7f0e","#9467bd","#8c564b","#e377c2","#17becf","#bcbd22","#7f7f7f","#393b79","#ad494a"];
const exps=D.board.map(b=>b.exp);const color=Object.fromEntries(exps.map((e,i)=>[e,PAL[i%PAL.length]]));
const best=e=>{const b=D.board.find(x=>x.exp===e);return b?b.summary.overall.score_m:Infinity};
exps.sort((a,b)=>best(a)-best(b));
const on=new Set(exps.slice(0,3));let frac=1,playing=false;
const $=id=>document.getElementById(id);$("suite").textContent="suite "+D.suite;
$("route").innerHTML=D.scenarios.map(s=>`<option value="${s.id}">${s.name}</option>`).join("");
$("seed").innerHTML=[...Array(D.runs_per_scenario).keys()].map(i=>`<option value="${i}">${i}</option>`).join("");
const cache={};let current=[];
const key=()=>`${$("route").value}__r${String($("seed").value).padStart(2,"0")}`;
const scen=()=>D.scenarios.find(s=>s.id===$("route").value);
async function load(){const k=key(),sc=scen();const out=[];
for(const e of exps){if(!(D.available[e]||[]).includes(k))continue;const id=e+"/"+k;
if(!(id in cache)){try{cache[id]=await (await fetch(`runs/${e}/${k}.json`)).json()}catch{cache[id]=null}}
if(cache[id])out.push({exp:e,world:sc.world,...cache[id]})}
current=out;$("desc").textContent=sc.name+": "+sc.description;render()}
const sel=()=>current;
function drawExps(){const runs=sel();$("exps").innerHTML=exps.map(e=>{const r=runs.find(x=>x.exp===e);const sc=r&&r.score!=null?Math.pow(10,r.score).toLocaleString(undefined,{maximumFractionDigits:1}):"—";
return `<div class="exp" data-e="${e}" style="opacity:${on.has(e)?1:.4}"><span class="sw" style="background:${color[e]}"></span>${e}<span class="s">${sc}</span></div>`}).join("");
document.querySelectorAll(".exp").forEach(el=>el.onclick=()=>{const e=el.dataset.e;on.has(e)?on.delete(e):on.add(e);render()})}
// ---- map
const map=$("map"),mc=map.getContext("2d");let view=null;const imgs={};
function img(w){if(!imgs[w]){imgs[w]=new Image();imgs[w].onload=render;imgs[w].src="data:image/png;base64,"+D.worlds[w].png}return imgs[w]}
function fit(){const r=sel()[0];if(!r)return;let xs=r.truth.map(p=>p[0]),ys=r.truth.map(p=>p[1]);const pad=150;
view={cx:(Math.min(...xs)+Math.max(...xs))/2,cy:(Math.min(...ys)+Math.max(...ys))/2,span:Math.max(Math.max(...xs)-Math.min(...xs),(Math.max(...ys)-Math.min(...ys))*1.6)+2*pad}}
function size(c){const r=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=r.width*d;c.height=r.height*d;return [c.width,c.height,d]}
function drawMap(){const [W,H,dpr]=size(map);const runs=sel();if(!runs.length)return;if(!view)fit();
const s=W/view.span,X=x=>W/2+(x-view.cx)*s,Y=y=>H/2-(y-view.cy)*s;const w=runs[0].world,b=D.worlds[w].bounds,im=img(w);
mc.fillStyle="#bbb";mc.fillRect(0,0,W,H);if(im.complete)mc.drawImage(im,X(b[0]),Y(b[3]),(b[2]-b[0])*s,(b[3]-b[1])*s);
const path=(pts,col,lw,n)=>{mc.strokeStyle=col;mc.lineWidth=lw*dpr;mc.beginPath();pts.slice(0,n).forEach((p,i)=>i?mc.lineTo(X(p[0]),Y(p[1])):mc.moveTo(X(p[0]),Y(p[1])));mc.stroke()};
const n=Math.max(2,Math.round(frac*runs[0].t.length));const truth=getComputedStyle(document.body).getPropertyValue("--truth");
path(runs[0].truth,"#111",3,n);
for(const r of runs.filter(r=>on.has(r.exp))){path(r.est,color[r.exp],2,n);const p=r.est[n-1];mc.fillStyle=color[r.exp];mc.beginPath();mc.arc(X(p[0]),Y(p[1]),5*dpr,0,7);mc.fill()}
const p=runs[0].truth[n-1];mc.fillStyle="#111";mc.beginPath();mc.arc(X(p[0]),Y(p[1]),5*dpr,0,7);mc.fill();
// scale bar
const m=Math.pow(10,Math.floor(Math.log10(view.span/5)));mc.fillStyle="#111";mc.fillRect(12*dpr,H-18*dpr,m*s,4*dpr);mc.font=`${12*dpr}px system-ui`;mc.fillText(m>=1000?m/1000+" km":m+" m",12*dpr,H-24*dpr);
const t=runs[0].t[n-1];$("tlabel").textContent=`t=${t.toFixed(0)} s · ${runs[0].dist[n-1].toFixed(0)} m travelled`}
let drag=null;map.onmousedown=e=>drag=[e.clientX,e.clientY];addEventListener("mouseup",()=>drag=null);
addEventListener("mousemove",e=>{if(!drag||!view)return;const s=view.span/map.clientWidth;view.cx-=(e.clientX-drag[0])*s;view.cy+=(e.clientY-drag[1])*s;drag=[e.clientX,e.clientY];render()});
map.onwheel=e=>{e.preventDefault();if(view){view.span*=Math.exp(e.deltaY*0.0015);render()}};
// ---- chart
const ch=$("chart"),cc=ch.getContext("2d");
function drawChart(){const [W,H,dpr]=size(ch);const runs=sel().filter(r=>on.has(r.exp));cc.clearRect(0,0,W,H);if(!runs.length)return;
const L=50*dpr,B=24*dpr,T=8*dpr,R=10*dpr;const dmax=Math.max(...runs.map(r=>r.dist[r.dist.length-1]));
let emax=Math.max(10,...runs.map(r=>Math.max(...r.err)));const emin=Math.min(1,...runs.map(r=>Math.min(...r.err.filter(e=>e>0))));
const lo=Math.max(-2,Math.floor(Math.log10(emin))),hi=Math.ceil(Math.log10(emax));
const X=d=>L+(W-L-R)*d/dmax,Y=e=>H-B-(H-B-T)*(Math.log10(Math.max(e,10**lo))-lo)/(hi-lo||1);
cc.strokeStyle=getComputedStyle(document.body).getPropertyValue("--line");cc.fillStyle=getComputedStyle(document.body).getPropertyValue("--muted");cc.font=`${11*dpr}px system-ui`;cc.lineWidth=dpr;
for(let k=lo;k<=hi;k++){cc.beginPath();cc.moveTo(L,Y(10**k));cc.lineTo(W-R,Y(10**k));cc.stroke();cc.fillText((10**k).toLocaleString(undefined,{maximumFractionDigits:2})+" m",4*dpr,Y(10**k)+4*dpr)}
cc.strokeStyle="#c0392b";cc.setLineDash([6,4]);cc.beginPath();cc.moveTo(L,Y(D.alert));cc.lineTo(W-R,Y(D.alert));cc.stroke();cc.setLineDash([]);
cc.fillStyle="#c0392b";cc.fillText("alert limit",W-R-70*dpr,Y(D.alert)-4*dpr);cc.fillStyle=getComputedStyle(document.body).getPropertyValue("--muted");
for(let d=0;d<=dmax;d+=500)cc.fillText(d+" m",X(d)-10*dpr,H-6*dpr);
for(const r of runs){if(r.unc&&r.unc.some(u=>u!==null)){cc.fillStyle=color[r.exp]+"22";cc.beginPath();
r.unc.forEach((u,i)=>{const y=u==="inf"?T:(u===null?H-B:Y(u));i?cc.lineTo(X(r.dist[i]),y):cc.moveTo(X(r.dist[i]),y)});cc.lineTo(X(r.dist[r.dist.length-1]),H-B);cc.lineTo(X(r.dist[0]),H-B);cc.fill()}
cc.strokeStyle=color[r.exp];cc.lineWidth=2*dpr;cc.beginPath();r.err.forEach((e,i)=>i?cc.lineTo(X(r.dist[i]),Y(e)):cc.moveTo(X(r.dist[i]),Y(e)));cc.stroke()}
const n=Math.max(1,Math.round(frac*runs[0].t.length))-1;cc.strokeStyle="#888";cc.setLineDash([4,4]);cc.beginPath();cc.moveTo(X(runs[0].dist[n]),T);cc.lineTo(X(runs[0].dist[n]),H-B);cc.stroke();cc.setLineDash([])}
const pct=v=>v===undefined||v===null?"no claim":Math.round(v*100)+"%";
function drawBoard(){const rows=[...D.board].sort((a,b)=>a.summary.overall.score_m-b.summary.overall.score_m);
$("board").innerHTML="<tr><th>experiment</th><th>sensors</th><th>score m</th><th>worst scenario</th><th>runs lost</th><th>misleading</th><th>silent</th></tr>"+
rows.map(r=>{const o=r.summary.overall;return `<tr><td><span class="sw" style="display:inline-block;background:${color[r.exp]||'#999'}"></span> ${r.exp}${r.stale?" ⚠ stale":""}</td><td>${(r.hardware||"suite IMU")+(r.ranger?" + "+r.ranger:"")}</td><td>${mfmt(+o.score_m.toPrecision(3))}</td><td>${o.worst_scenario} ${mfmt(+o.worst_score_m.toPrecision(3))}</td><td>${pct(o.lost_frac)}</td><td>${pct(o.misleading_frac)}</td><td>${pct(o.silent_failure_frac)}</td></tr>`}).join("");
const hue=v=>{const t=Math.max(0,Math.min(1,(Math.log10(Math.max(v,1)))/4));return `hsl(${120-120*t} 55% 42% / .9)`};
$("matrix").innerHTML="<tr><th>experiment</th>"+D.scenarios.map(s=>`<th title="${s.description}">${s.name}</th>`).join("")+"</tr>"+
rows.map(r=>"<tr><td>"+r.exp+"</td>"+D.scenarios.map(s=>{const x=r.summary[s.id];return x?`<td style="background:${hue(x.score_m)};color:#fff;cursor:pointer" data-s="${s.id}" title="lost ${pct(x.lost_frac)}">${mfmt(+x.score_m.toPrecision(2))}</td>`:"<td>—</td>"}).join("")+"</tr>").join("");
document.querySelectorAll("#matrix td[data-s]").forEach(td=>td.onclick=()=>{$("route").value=td.dataset.s;view=null;load()})}
// ---- studies
const SPAL=["#2b6cb0","#2f855a","#d69e2e","#c53030","#6b46c1","#319795"];
function axes(c,W,H,dpr,L,B,T,R,lo,hi,yfmt){const ctx=c.getContext("2d");const css=getComputedStyle(document.body);
ctx.strokeStyle=css.getPropertyValue("--line");ctx.fillStyle=css.getPropertyValue("--muted");ctx.font=`${11*dpr}px system-ui`;ctx.lineWidth=dpr;
const Y=v=>H-B-(H-B-T)*(Math.log10(Math.max(v,10**lo))-lo)/(hi-lo||1);
for(let k=lo;k<=hi;k++){ctx.beginPath();ctx.moveTo(L,Y(10**k));ctx.lineTo(W-R,Y(10**k));ctx.stroke();ctx.fillText(yfmt(10**k),4*dpr,Y(10**k)+4*dpr)}return [ctx,Y]}
function champ(){const b=D.board.filter(x=>x.exp!=="terrain_ekf"&&!x.stale).map(x=>({exp:x.exp,score_m:x.summary.overall.score_m}));return b.length?b.reduce((a,c)=>c.score_m<a.score_m?c:a):null}
function barChart(c,st){const [W,H,dpr]=size(c);const L=56*dpr,B=24*dpr,T=10*dpr,R=10*dpr;const v=st.variants;const ch=st.reference===false?null:champ();
const vals=v.map(x=>x.score_m).concat(ch?[ch.score_m]:[]);const lo=Math.floor(Math.log10(Math.min(...vals)))-1,hi=Math.ceil(Math.log10(Math.max(...vals)*1.2));
const [ctx,Y]=axes(c,W,H,dpr,L,B,T,R,lo,hi,mfmt);const bw=(W-L-R)/v.length;
v.forEach((x,i)=>{ctx.fillStyle=SPAL[i%SPAL.length];const y=Y(x.score_m);ctx.fillRect(L+i*bw+bw*0.2,y,bw*0.6,H-B-y);
ctx.fillStyle=getComputedStyle(document.body).getPropertyValue("--ink");ctx.textAlign="center";ctx.fillText(mfmt(+x.score_m.toPrecision(3)),L+i*bw+bw/2,y-4*dpr);
ctx.textAlign="left"});
if(ch){ctx.strokeStyle="#c0392b";ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(L,Y(ch.score_m));ctx.lineTo(W-R,Y(ch.score_m));ctx.stroke();ctx.setLineDash([]);
ctx.fillStyle="#c0392b";ctx.fillText(`champion ${ch.exp}: ${mfmt(ch.score_m)}`,L+6*dpr,Y(ch.score_m)-5*dpr)}
ctx.fillStyle=getComputedStyle(document.body).getPropertyValue("--muted");ctx.fillText("score (geometric-mean error, log scale)",L,H-4*dpr)}
function curveChart(c,st){const [W,H,dpr]=size(c);const L=56*dpr,B=24*dpr,T=10*dpr,R=10*dpr;const v=st.variants;
const all=v.flatMap(x=>x.curve.p90.concat(x.curve.median)).filter(e=>e>0);const lo=Math.max(-2,Math.floor(Math.log10(Math.min(...all)))),hi=Math.ceil(Math.log10(Math.max(...all)));
const [ctx,Y]=axes(c,W,H,dpr,L,B,T,R,lo,hi,mfmt);const dmax=Math.max(...v.map(x=>x.curve.dist[x.curve.dist.length-1]));const X=d=>L+(W-L-R)*d/dmax;
for(let d=0;d<=dmax;d+=1000)ctx.fillText(mfmt(d),X(d)-8*dpr,H-6*dpr);
v.forEach((x,i)=>{ctx.strokeStyle=SPAL[i%SPAL.length];for(const [key,dash,lw] of [["p90",[4,4],1],["median",[],2.2]]){ctx.setLineDash(dash.map(q=>q*dpr));ctx.lineWidth=lw*dpr;ctx.beginPath();
x.curve[key].forEach((e,j)=>j?ctx.lineTo(X(x.curve.dist[j]),Y(e)):ctx.moveTo(X(x.curve.dist[j]),Y(e)));ctx.stroke()}ctx.setLineDash([])})}
function drawStudies(){const el=$("studies");if(!D.studies||!D.studies.length){el.innerHTML="";return}
el.innerHTML="<h2>Studies · terrain_ekf under stress</h2>"+D.studies.map((st,k)=>`<div class="card study"><h3>${st.title}</h3><div class="muted">${st.question}</div>
<div class="row">${st.variants.map((x,i)=>`<span class="exp" style="cursor:default"><span class="sw" style="background:${SPAL[i%SPAL.length]}"></span>${x.label}</span>`).join("")}</div>
<div class="two"><div><canvas id="sb${k}"></canvas></div><div><canvas id="sc${k}"></canvas><div class="muted">Error vs distance travelled, all runs. Solid: median. Dashed: 90th percentile.</div></div></div>
<table><tr><th>variant</th><th>score</th><th>median RMS error</th><th>worst run RMS</th><th>runs ever over 50 m</th><th>median distance before 50 m</th></tr>${st.variants.map(x=>`<tr><td>${x.label}</td><td>${mfmt(+x.score_m.toPrecision(3))}</td><td>${mfmt(+x.median_rms_m.toPrecision(3))}</td><td>${mfmt(+x.worst_rms_m.toPrecision(3))}</td><td>${x.lost_runs} of ${x.runs}</td><td>${mfmt(Math.round(x.lost_at_m))}</td></tr>`).join("")}</table>
<div class="muted">${st.notes}</div></div>`).join("");
D.studies.forEach((st,k)=>{barChart($("sb"+k),st);curveChart($("sc"+k),st)})}
function render(){drawExps();drawMap();drawChart()}
$("route").onchange=()=>{view=null;load()};$("seed").onchange=load;$("fit").onclick=()=>{fit();render()};
$("time").oninput=e=>{frac=e.target.value/1000;render()};
$("all").onclick=()=>{exps.forEach(e=>on.add(e));render()};$("none").onclick=()=>{on.clear();render()};
$("play").onclick=()=>{playing=!playing;$("play").textContent=playing?"❚❚":"▶";if(playing&&frac>=1)frac=0;tick()};
function tick(){if(!playing)return;frac=Math.min(1,frac+0.002);$("time").value=frac*1000;render();if(frac>=1){playing=false;$("play").textContent="▶"}else requestAnimationFrame(tick)}
addEventListener("resize",()=>{render();drawStudies()});drawBoard();load();drawStudies();
</script></body></html>
"""
