// Capture discovery candidate URLs as PDF/image for inspection + relevance scoring.
// Usage: node capture_discovery.mjs <abs discovery dir>
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import path from 'path';

const ROOT = process.argv[2];
const dirs = readdirSync(ROOT).filter(d => existsSync(path.join(ROOT, d, 'candidates.json')));
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery benchmark)' });

for (const did of dirs) {
  const meta = JSON.parse(readFileSync(path.join(ROOT, did, 'candidates.json')));
  const capDir = path.join(ROOT, did, 'captures'); mkdirSync(capDir, { recursive: true });
  const records = [];
  for (const c of meta.candidates) {
    const h = createHash('md5').update(c.url).digest('hex').slice(0, 10);
    const rec = { url: c.url, tools: c.tools, hash: h, ok: false };
    try {
      let ct = '';
      try { const r = await fetch(c.url, { method: 'GET', redirect: 'follow', signal: AbortSignal.timeout(20000) });
            ct = (r.headers.get('content-type') || '').toLowerCase(); rec.final_url = r.url;
            if (ct.includes('pdf') || ct.includes('image')) {
              const ext = ct.includes('pdf') ? 'pdf' : (ct.split('/')[1] || 'img').split(';')[0];
              const buf = Buffer.from(await r.arrayBuffer());
              writeFileSync(path.join(capDir, `${h}.${ext}`), buf);
              rec.kind = ct.includes('pdf') ? 'pdf' : 'image'; rec.file = `${h}.${ext}`; rec.ok = true;
            }
      } catch (e) { /* fall through to render */ }
      if (!rec.ok) {  // HTML or fetch failed -> render with Playwright
        const page = await ctx.newPage();
        try {
          await page.goto(c.url, { waitUntil: 'networkidle', timeout: 30000 }).catch(()=>{});
          rec.final_url = page.url();
          await page.pdf({ path: path.join(capDir, `${h}.pdf`), printBackground: true }).catch(async()=>{
            await page.screenshot({ path: path.join(capDir, `${h}.png`), fullPage: true }); rec.file = `${h}.png`; rec.kind='screenshot';
          });
          if (!rec.file) { rec.file = `${h}.pdf`; rec.kind = 'html-pdf'; }
          rec.ok = true;
        } finally { await page.close(); }
      }
    } catch (e) { rec.err = String(e).slice(0, 120); }
    records.push(rec);
    console.log(`  [${did}] ${rec.ok ? 'OK ' : 'FAIL'} ${rec.kind||''} ${c.url.slice(0,70)}`);
  }
  writeFileSync(path.join(ROOT, did, 'captures.json'), JSON.stringify(records, null, 2));
}
await browser.close();
console.log('CAPTURE DONE');
