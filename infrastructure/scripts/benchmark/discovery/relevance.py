"""Relevance pass: for each captured page, flag whether it actually contains a bell schedule.
Heuristic: clock-time density + bell/schedule keywords. Writes relevance.json + per-tool summary."""
import json, re, subprocess, glob, os
from collections import defaultdict

TIME = re.compile(r'\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?')
KW = re.compile(r'\b(bell|schedule|dismissal|start time|end time|school hours|arrival|first bell|warning bell|period \d)\b', re.I)

def text_of(p):
    try:
        if p.endswith(('.png','.jpg','.jpeg','.gif')):
            return subprocess.run(['tesseract', p, '-'], capture_output=True, text=True, timeout=60).stdout
        return subprocess.run(['pdftotext','-layout', p, '-'], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ''

DROOT='data/benchmark_results/discovery'
tool_hit=defaultdict(set); tool_pages=defaultdict(int); any_hit=set(); districts=[]
for capf in sorted(glob.glob(f'{DROOT}/*/captures.json')):
    did=capf.split('/')[-2]; districts.append(did)
    caps=json.load(open(capf)); capdir=f'{DROOT}/{did}/captures'
    out=[]
    for c in caps:
        if not c.get('ok') or not c.get('file'): continue
        txt=text_of(os.path.join(capdir,c['file']))
        nt=len(TIME.findall(txt)); kw=bool(KW.search(txt))
        rel = nt>=4 and kw
        c2={'url':c['url'],'tools':c['tools'],'kind':c.get('kind'),'n_times':nt,'has_kw':kw,'relevant':rel}
        out.append(c2)
        if rel:
            any_hit.add(did)
            for t in c['tools']: tool_hit[t].add(did); tool_pages[t]+=1
    json.dump(out, open(f'{DROOT}/{did}/relevance.json','w'), indent=2)
    rels=[c for c in out if c['relevant']]
    print(f"\n{did}: {len(rels)} relevant / {len(out)} captured")
    for c in sorted(rels,key=lambda x:-x['n_times'])[:5]:
        print(f"    times={c['n_times']:>3} [{','.join(c['tools'])}]  {c['url'][:72]}")

N=len(districts)
print(f"\n===== DISCOVERY HIT-RATE (n={N} districts) =====")
print(f"{'tool':<12}{'districts w/ ≥1 relevant':>26}{'relevant pages found':>22}")
for t in ['perplexity','google','openrouter']:
    print(f"{t:<12}{len(tool_hit[t]):>20}/{N}{tool_pages[t]:>22}")
print(f"{'ANY tool':<12}{len(any_hit):>20}/{N}")
