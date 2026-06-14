"""District x Model crosstab of matched/GT-bands, for mode AND max aggregation.
Layers modality + derived difficulty. Writes CSVs + JSON (for the dashboard) + prints pattern analysis.
Columns = full-41 models (any *__tables run with >=39 scored districts)."""
import json, csv, glob, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_minutes import gt_minutes_by_band, model_band_values

ROOT = Path("."); RES = ROOT/"data"/"benchmark_results"; TOL = 15
man = {d["district_id"]: d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}

def short(dirname):
    s = dirname.replace("__tables","").replace("openrouter_","").replace("pplx_","")
    for p in ("google_","openai_","mistralai_","meta-llama_","deepseek_","qwen_","x-ai_","cohere_","ibm-granite_","nvidia_","anthropic_","gemini_"):
        s = s.replace(p,"")
    return s

# full-41 model runs: *__tables with >=39 districts that have extraction files in manifest
models = []
for d in sorted(glob.glob(str(RES/"*__tables"))):
    name = Path(d).name
    n = len([x for x in glob.glob(d+"/*/extraction_result.json") if Path(x).parent.name in man and gt_minutes_by_band(man[Path(x).parent.name])])
    if n >= 39: models.append(name)
print(f"{len(models)} full-41 models: {[short(m) for m in models]}\n")

# districts with GT bands
dists = [did for did,d in man.items() if gt_minutes_by_band(d)]

def cell(model_dir, did, agg):
    f = RES/model_dir/did/"extraction_result.json"
    if not f.exists(): return None
    try: ex = json.loads(f.read_text())
    except Exception: return None
    gtb = gt_minutes_by_band(man[did]); mb = model_band_values(ex.get("schedules",[]), agg)
    matched = sum(1 for b,gm in gtb.items() if b in mb and abs(mb[b]-gm)<=TOL)
    return matched, len(gtb)

def build(agg):
    rows=[]; per_model_matched=defaultdict(int); per_model_total=defaultdict(int)
    per_modality=defaultdict(lambda: defaultdict(lambda:[0,0]))  # modality->model->[matched,total]
    for did in dists:
        d=man[did]; gtb=gt_minutes_by_band(d); modality="/".join(d.get("modality",[]) or ["?"])
        row={"district_id":did,"name":d["district_name"],"state":d["state"],"modality":modality,"gt_bands":len(gtb)}
        msum=0; mtot=0
        for m in models:
            c=cell(m,did,agg)
            if c is None: row[short(m)]=""; continue
            mt,tt=c; row[short(m)]=f"{mt}/{tt}"
            per_model_matched[m]+=mt; per_model_total[m]+=tt
            per_modality[modality][m][0]+=mt; per_modality[modality][m][1]+=tt
            msum+=mt; mtot+=tt
        row["_difficulty"]=round(msum/mtot,3) if mtot else 0.0  # avg band-match-rate across models
        row["_models_full"]=sum(1 for m in models if row[short(m)] and row[short(m)].split("/")[0]==row[short(m)].split("/")[1])
        rows.append(row)
    rows.sort(key=lambda r:r["_difficulty"])
    return rows, per_model_matched, per_model_total, per_modality

for agg in ("mode","max"):
    rows,pmm,pmt,pmod = build(agg)
    cols=["district_id","name","state","modality","gt_bands","_difficulty","_models_full"]+[short(m) for m in models]
    with open(RES/f"crosstab_{agg}.csv","w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader()
        for r in rows: w.writerow(r)
    json.dump({"agg":agg,"models":[short(m) for m in models],"rows":rows},
              open(RES/f"crosstab_{agg}.json","w"),indent=1)
    print(f"=== AGG={agg} : per-model total matched bands ===")
    for m in sorted(models,key=lambda m:-pmm[m]/max(pmt[m],1)):
        print(f"   {pmm[m]:>3}/{pmt[m]:<3} ({100*pmm[m]/max(pmt[m],1):4.1f}%)  {short(m)}")

# mode-vs-max delta (hidden path) + difficulty + modality, computed once on mode rows
rows_mode,pmm_mode,pmt_mode,pmod_mode=build("mode")
_,pmm_max,pmt_max,_=build("max")
print("\n=== HIDDEN-PATH: mode -> max gain per model (bands recovered by 'longest-day') ===")
for m in sorted(models,key=lambda m:(pmm_max[m]-pmm_mode[m]),reverse=True):
    g=pmm_max[m]-pmm_mode[m]
    if g: print(f"   +{g:>2} bands  {short(m)}  ({100*pmm_mode[m]/max(pmt_mode[m],1):.0f}% -> {100*pmm_max[m]/max(pmt_max[m],1):.0f}%)")

print("\n=== DISTRICT DIFFICULTY (avg band-match-rate across models, mode) ===")
buckets=defaultdict(int)
for r in rows_mode:
    b = "0 nobody" if r["_difficulty"]==0 else ("hard <25%" if r["_difficulty"]<.25 else ("mid 25-60%" if r["_difficulty"]<.6 else "easy >60%"))
    buckets[b]+=1
for b in ["0 nobody","hard <25%","mid 25-60%","easy >60%"]: print(f"   {b:<14} {buckets[b]} districts")
print("\n   Universally HARD (rate<=0.1):")
for r in rows_mode:
    if r["_difficulty"]<=0.1: print(f"      {r['_difficulty']:.2f}  [{r['modality']}]  {r['district_id']} {r['name'][:34]}")

print("\n=== PER-MODALITY model leaderboard (mode, % bands matched) ===")
for modality in sorted(pmod_mode):
    tot_d=sum(1 for r in rows_mode if r["modality"]==modality)
    best=sorted(pmod_mode[modality].items(), key=lambda kv:-(kv[1][0]/max(kv[1][1],1)))
    print(f"\n  [{modality}] ({tot_d} districts) top 5:")
    for m,(mt,tt) in best[:5]:
        print(f"      {100*mt/max(tt,1):4.0f}%  ({mt}/{tt})  {short(m)}")
print(f"\nWrote crosstab_mode.csv / crosstab_max.csv (+ .json) to {RES}")
