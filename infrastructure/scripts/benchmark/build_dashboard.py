"""Self-contained interactive crosstab dashboard (heatmap + filters). No server/deps."""
import json
from pathlib import Path
RES = Path("data/benchmark_results")
mode = json.load(open(RES/"crosstab_mode.json")); mx = json.load(open(RES/"crosstab_max.json"))
DATA = {"mode": mode, "max": mx}
html = """<!doctype html><meta charset=utf-8><title>Bell-schedule extraction crosstab</title>
<style>
 body{font:13px/1.4 -apple-system,Arial;margin:16px;color:#222}
 h1{font-size:18px} .ctl{margin:10px 0} button{padding:4px 10px;margin-right:6px;cursor:pointer}
 button.on{background:#2563eb;color:#fff;border-color:#2563eb}
 table{border-collapse:collapse;font-size:11px} th,td{border:1px solid #ddd;padding:2px 5px;text-align:center;white-space:nowrap}
 th.rot{height:120px;vertical-align:bottom} th.rot div{writing-mode:vertical-rl;transform:rotate(180deg);max-height:115px}
 td.dist{text-align:left;max-width:220px;overflow:hidden;text-overflow:ellipsis}
 .meta{background:#f7f7f7;position:sticky;left:0}
 .legend span{display:inline-block;padding:2px 8px;margin-right:4px}
</style>
<h1>Bell-schedule extraction — district × model (matched / GT bands)</h1>
<div class=ctl>
 Aggregation: <button id=bmode class=on onclick="setAgg('mode')">mode</button><button id=bmax onclick="setAgg('max')">max (longest-day)</button>
 &nbsp;&nbsp;Modality: <select id=mod onchange=render()></select>
 &nbsp;&nbsp;Sort: <button onclick="sortBy('_difficulty');render()">difficulty</button><button onclick="sortBy('name');render()">name</button>
</div>
<div class=legend>Cell color = bands matched fraction:
 <span style="background:#d73027;color:#fff">0%</span><span style="background:#fee08b">~50%</span><span style="background:#1a9850;color:#fff">100%</span>
 &nbsp; difficulty = avg match-rate across all models</div>
<div id=tbl></div>
<script>
const DATA=__DATA__; let agg='mode', sortKey='_difficulty';
function color(s){ if(s==='')return '#fff'; const [m,t]=s.split('/').map(Number); const f=t?m/t:0;
  const r=Math.round(215+(26-215)*f), g=Math.round(48+(152-48)*f), b=Math.round(39+(80-39)*f); return `rgb(${r},${g},${b})`; }
function setAgg(a){agg=a;document.getElementById('bmode').className=a==='mode'?'on':'';document.getElementById('bmax').className=a==='max'?'on':'';render();}
function sortBy(k){sortKey=k;}
function modalities(){const s=new Set(DATA.mode.rows.map(r=>r.modality));return ['(all)',...[...s].sort()];}
function init(){const sel=document.getElementById('mod');modalities().forEach(m=>{const o=document.createElement('option');o.textContent=m;sel.appendChild(o);});render();}
function render(){
 const d=DATA[agg], models=d.models; let rows=d.rows.slice();
 const mf=document.getElementById('mod').value; if(mf&&mf!=='(all)')rows=rows.filter(r=>r.modality===mf);
 rows.sort((a,b)=> sortKey==='name'? a.name.localeCompare(b.name): a._difficulty-b._difficulty);
 // per-model totals over shown rows
 const tot={}; models.forEach(m=>tot[m]=[0,0]); rows.forEach(r=>models.forEach(m=>{if(r[m]){const[x,y]=r[m].split('/').map(Number);tot[m][0]+=x;tot[m][1]+=y;}}));
 let h='<table><tr><th class="meta rot"><div>district</div></th><th class=rot><div>modality</div></th><th class=rot><div>GT</div></th><th class=rot><div>difficulty</div></th>';
 models.forEach(m=>h+=`<th class=rot><div>${m}</div></th>`); h+='</tr>';
 h+='<tr><td class="meta" style="text-align:right">OVERALL %</td><td></td><td></td><td></td>';
 models.forEach(m=>{const f=tot[m][1]?100*tot[m][0]/tot[m][1]:0;h+=`<td style="background:${color(tot[m][0]+'/'+tot[m][1])};color:#fff">${f.toFixed(0)}</td>`;});h+='</tr>';
 rows.forEach(r=>{const dc=color(Math.round(r._difficulty*10)+'/10');
  h+=`<tr><td class="dist meta" title="${r.district_id} ${r.name}">${r.name}</td><td>${r.modality}</td><td>${r.gt_bands}</td><td style="background:${dc};color:#fff">${(r._difficulty*100).toFixed(0)}</td>`;
  models.forEach(m=>h+=`<td style="background:${color(r[m]||'')}" >${r[m]||''}</td>`); h+='</tr>';});
 h+='</table>'; document.getElementById('tbl').innerHTML=h;
}
init();
</script>"""
out = RES/"crosstab_dashboard.html"
out.write_text(html.replace("__DATA__", json.dumps(DATA)))
print("wrote", out, f"({out.stat().st_size//1024} KB, self-contained)")
