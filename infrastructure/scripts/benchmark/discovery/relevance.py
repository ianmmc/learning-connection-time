"""Relevance pass (tiered): prefer text layer (.txt innerText / pdftotext on .pdf),
fall back to OCR of the full-page screenshot (.png) when text is thin. Flags schedule pages."""
import json, re, subprocess, glob, os
from collections import defaultdict
TIME=re.compile(r'\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?')
KW=re.compile(r'\b(bell|schedule|dismissal|start time|end time|school hours|arrival|first bell|period \d)\b',re.I)
def run(cmd,timeout=90):
    try: return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout).stdout
    except Exception: return ''
def pdftotext(p): return run(['pdftotext','-layout',p,'-'])
def ocr(p): return run(['tesseract',p,'-'])
DROOT='data/benchmark_results/discovery'
tool_hit=defaultdict(set); tool_pages=defaultdict(int); any_hit=set(); districts=[]
for capf in sorted(glob.glob(f'{DROOT}/*/captures.json')):
    did=capf.split('/')[-2]; districts.append(did); capdir=f'{DROOT}/{did}/captures'
    out=[]
    for c in json.load(open(capf)):
        if not c.get('ok'): continue
        f=c.get('files',{}); best_n=0; best_txt=''; src='none'
        # text layer
        if f.get('txt') and os.path.exists(os.path.join(capdir,f['txt'])):
            t=open(os.path.join(capdir,f['txt'])).read(); n=len(TIME.findall(t))
            if n>best_n: best_n,best_txt,src=n,t,'text'
        if f.get('bin'):
            p=os.path.join(capdir,f['bin'])
            t=pdftotext(p) if f['bin'].endswith('.pdf') else ocr(p)
            n=len(TIME.findall(t))
            if n>best_n: best_n,best_txt,src=n,t,('pdf' if f['bin'].endswith('.pdf') else 'image-ocr')
        # OCR-screenshot fallback when text layer is thin
        if best_n<4 and f.get('png') and os.path.exists(os.path.join(capdir,f['png'])):
            t=ocr(os.path.join(capdir,f['png'])); n=len(TIME.findall(t))
            if n>best_n: best_n,best_txt,src=n,t,'screenshot-ocr'
        rel = best_n>=4 and bool(KW.search(best_txt))
        out.append({'url':c['url'],'tools':c['tools'],'kind':c.get('kind'),'src':src,'n_times':best_n,'relevant':rel})
        if rel:
            any_hit.add(did)
            for t_ in c['tools']: tool_hit[t_].add(did); tool_pages[t_]+=1
    json.dump(out,open(f'{DROOT}/{did}/relevance.json','w'),indent=2)
    rels=[c for c in out if c['relevant']]
    print(f"\n{did}: {len(rels)} relevant / {len(out)} captured")
    for c in sorted(rels,key=lambda x:-x['n_times'])[:6]:
        print(f"    times={c['n_times']:>3} via {c['src']:<14} [{','.join(c['tools'])}]  {c['url'][:62]}")
N=len(districts)
print(f"\n===== DISCOVERY HIT-RATE (n={N}) =====")
print(f"{'tool':<12}{'districts w/ >=1 relevant':>26}{'relevant pages':>16}")
for t_ in ['perplexity','openrouter','claude']:
    print(f"{t_:<12}{len(tool_hit[t_]):>20}/{N}{tool_pages[t_]:>16}")
print(f"{'ANY tool':<12}{len(any_hit):>20}/{N}")
