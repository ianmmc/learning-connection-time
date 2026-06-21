"""Close the loop: extract from DISCOVERED captures, grouped by discovery tool, scored vs GT.
For each (district, tool): input = concat of that tool's relevant captures' best text (text/pdf/OCR),
capped. Run Gemini 2.5 Flash + Mistral Large 2512; score modal-minutes (+/-15) vs ground truth."""
import json, glob, re, subprocess, os, sys, statistics
from pathlib import Path
sys.path.insert(0,'infrastructure/scripts/benchmark')
from extractors import make_extractor, MAX_TEXT_LEN
from score_minutes import gt_minutes_by_band, model_band_values
TIME=re.compile(r'\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?')
DROOT=Path('data/benchmark_results/discovery')
TOOLS=['claude','openrouter','perplexity']
man={d['district_id']:d for d in json.load(open('data/benchmark/ground_truth_manifest.json'))['districts']}
def run(cmd):
    try: return subprocess.run(cmd,capture_output=True,text=True,timeout=90).stdout
    except Exception: return ''
_tc={}
def best_text(capdir, files, hsh):
    if hsh in _tc: return _tc[hsh]
    cands=[]
    if files.get('txt') and (capdir/files['txt']).exists(): cands.append(open(capdir/files['txt']).read())
    if files.get('bin') and (capdir/files['bin']).exists():
        p=str(capdir/files['bin']); cands.append(run(['pdftotext','-layout',p,'-']) if p.endswith('.pdf') else run(['tesseract',p,'-']))
    if files.get('png') and (capdir/files['png']).exists():
        cands.append(run(['tesseract',str(capdir/files['png']),'-']))
    best=max(cands,key=lambda t:len(TIME.findall(t)),default='')
    _tc[hsh]=best; return best

# build per-(district,tool) inputs
inputs=defaultdict=__import__('collections').defaultdict(dict)
districts_by_tool={t:set() for t in TOOLS}
for relf in glob.glob(f'{DROOT}/*/relevance.json'):
    did=relf.split('/')[-2]; capdir=DROOT/did/'captures'
    caps={c['hash']:c for c in json.load(open(DROOT/did/'captures.json'))}
    rels=[c for c in json.load(open(relf)) if c['relevant']]
    if not rels: continue
    for t in TOOLS:
        texts=[]
        for c in rels:
            if t in c['tools']:
                cap=caps.get(c.get('hash')) or next((x for x in caps.values() if x['url']==c['url']),None)
                if cap: texts.append(best_text(capdir,cap.get('files',{}),cap['hash']))
        if texts:
            joined='\n\n'.join(texts)
            if len(joined)>MAX_TEXT_LEN: joined=joined[:MAX_TEXT_LEN]
            inputs[did][t]=joined; districts_by_tool[t].add(did)
print("inputs built. districts/tool:",{t:len(s) for t,s in districts_by_tool.items()})

MODELS={"gemini-2.5-flash":"gemini:gemini-2.5-flash","mistral-large-2512":"openrouter:mistralai/mistral-large-2512"}
res={(m,t):[0,0,0,0] for m in MODELS for t in TOOLS}  # matched,total,dist,dist_hit
for mname,spec in MODELS.items():
    ex=make_extractor(spec)
    for did,perTool in inputs.items():
        gtb=gt_minutes_by_band(man[did])
        if not gtb: continue
        for t,text in perTool.items():
            try:
                out=ex.extract(text,did,man[did]['district_name'],man[did]['state'])
                mb=model_band_values(out.get('schedules',[]),'mode')
            except Exception as e:
                mb={}
            matched=sum(1 for b,g in gtb.items() if b in mb and abs(mb[b]-g)<=15)
            r=res[(mname,t)]; r[0]+=matched; r[1]+=len(gtb); r[2]+=1; r[3]+= (1 if matched else 0)
    print(f"  [{mname}] done")
print(f"\n=== EXTRACTION FROM DISCOVERED PAGES — modal-minutes +/-15, by discovery tool ===")
print(f"{'model':<20}{'tool':<12}{'band match%':>12}{'bands':>10}{'dist hit%':>11}{'districts':>11}")
for m in MODELS:
    for t in TOOLS:
        ma,to,dn,dh=res[(m,t)]
        print(f"{m:<20}{t:<12}{(100*ma/to if to else 0):>11.1f}%{f'{ma}/{to}':>10}{(100*dh/dn if dn else 0):>10.0f}%{dn:>11}")
