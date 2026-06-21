// Tiered discovery capture (concurrent): direct-download PDFs/images; for HTML render -> innerText
// (main+iframes) as .txt AND a full-page screenshot as .png. Relevance/extraction picks the best source.
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import path from 'path';

const ROOT = process.argv[2];
const CONC = parseInt(process.argv[3] || '5', 10);
const TIME = /\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?/g;

const dirs = readdirSync(ROOT).filter(d => existsSync(path.join(ROOT, d, 'candidates.json')));
const byDistrict = {};
const tasks = [];
for (const did of dirs) {
  const meta = JSON.parse(readFileSync(path.join(ROOT, did, 'candidates.json')));
  const capDir = path.join(ROOT, did, 'captures'); mkdirSync(capDir, { recursive: true });
  byDistrict[did] = { capDir, records: [] };
  for (const c of meta.candidates) tasks.push({ did, c, capDir });
}

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery)' });

async function processTask({ did, c, capDir }) {
  const h = createHash('md5').update(c.url).digest('hex').slice(0, 10);
  const rec = { url: c.url, tools: c.tools, hash: h, ok: false, files: {} };
  try {
    let ct = '';
    try {
      const r = await fetch(c.url, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
      ct = (r.headers.get('content-type') || '').toLowerCase(); rec.final_url = r.url;
      if (ct.includes('pdf') || ct.includes('image')) {
        const ext = ct.includes('pdf') ? 'pdf' : ((ct.split('/')[1] || 'img').split(';')[0]);
        writeFileSync(path.join(capDir, `${h}.${ext}`), Buffer.from(await r.arrayBuffer()));
        rec.kind = ct.includes('pdf') ? 'pdf' : 'image'; rec.files.bin = `${h}.${ext}`; rec.ok = true;
      }
    } catch (e) { /* fall through to render */ }
    if (!rec.ok) {
      const page = await ctx.newPage();
      try {
        await page.goto(c.url, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(2500);
        rec.final_url = page.url();
        let text = '';
        for (const fr of page.frames()) { try { text += '\n' + ((await fr.evaluate(() => document.body ? document.body.innerText : '')) || ''); } catch (e) {} }
        writeFileSync(path.join(capDir, `${h}.txt`), text);
        await page.screenshot({ path: path.join(capDir, `${h}.png`), fullPage: true }).catch(() => {});
        rec.kind = 'html'; rec.files.txt = `${h}.txt`; rec.files.png = `${h}.png`;
        rec.text_times = (text.match(TIME) || []).length; rec.ok = true;
      } finally { await page.close(); }
    }
  } catch (e) { rec.err = String(e).slice(0, 120); }
  byDistrict[did].records.push(rec);
  return rec;
}

let idx = 0, done = 0;
async function worker() {
  while (idx < tasks.length) {
    const t = tasks[idx++];
    await processTask(t);
    if (++done % 25 === 0) console.log(`  ...${done}/${tasks.length} captured`);
  }
}
console.log(`capturing ${tasks.length} candidate URLs across ${dirs.length} districts (concurrency ${CONC})`);
await Promise.all(Array.from({ length: CONC }, () => worker()));

for (const did of Object.keys(byDistrict)) {
  writeFileSync(path.join(ROOT, did, 'captures.json'), JSON.stringify(byDistrict[did].records, null, 2));
}
await browser.close();
console.log(`CAPTURE DONE — ${done} URLs, ${dirs.length} districts`);
