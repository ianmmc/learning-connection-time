// Acquisition-pipeline probe: can Crawlee actually FIND bell-schedule pages?
// Runs the real mapWebsite() in two modes per district and reports signal pages.
import { mapWebsite } from './dist/mapper.js';

const INCLUDE = ['**/bell*schedule*', '**/school*hours*', '**/daily*schedule*', '**/start*time*'];
const EXCLUDE = ['**/news/**', '**/calendar/**', '**/athletics/**', '**/sports/**', '**/lunch*menu*', '**/bus*schedule*', '**/testing*schedule*'];

const DISTRICTS = [
  { id: '1100031', name: 'KIPP DC PCS', st: 'DC', url: 'http://www.kippdc.org' },
  { id: '1000200', name: 'Christina School District', st: 'DE', url: 'http://www.christinak12.org/' },
  { id: '5605302', name: 'Sweetwater County SD #1', st: 'WY', url: 'http://www.sweetwater1.org' },
  { id: '0512660', name: 'Springdale School District', st: 'AR', url: 'http://www.springdaleschools.org' },
];

// Proxy for the Ollama ranker: a page that IS a schedule has many clock-times + bell keywords.
const score = (p) => p.timePatternCount + 2 * p.keywordMatchCount + (p.hasSchedulePdfLink ? 10 : 0);
const signal = (p) => p.timePatternCount >= 4 || p.hasSchedulePdfLink;

async function runMode(label, url, req) {
  const t = Date.now();
  let r;
  try {
    r = await mapWebsite(req);
  } catch (e) {
    return { label, error: String(e).slice(0, 200) };
  }
  const secs = ((Date.now() - t) / 1000).toFixed(0);
  const pages = r.pages || [];
  const hits = pages.filter(signal).sort((a, b) => score(b) - score(a));
  return { label, secs, ok: r.success, n: pages.length, stats: r.stats, hits, err: r.error };
}

for (const d of DISTRICTS) {
  console.log(`\n================ ${d.id} ${d.name} (${d.st}) ================`);
  console.log(`seed: ${d.url}`);

  const targeted = await runMode('TARGETED', d.url, {
    url: d.url, maxRequests: 80, maxDepth: 4,
    patterns: { includeGlobs: INCLUDE, excludeGlobs: EXCLUDE },
  });
  const broad = await runMode('BROAD', d.url, {
    url: d.url, maxRequests: 50, maxDepth: 3,
    patterns: { excludeGlobs: EXCLUDE },
  });

  for (const m of [targeted, broad]) {
    if (m.error) { console.log(`  [${m.label}] ERROR: ${m.error}`); continue; }
    console.log(`  [${m.label}] crawled=${m.n} pages in ${m.secs}s  signalPages=${m.hits.length}${m.err ? '  err=' + m.err : ''}`);
    m.hits.slice(0, 4).forEach((p) =>
      console.log(`      ★ times=${p.timePatternCount} kw=${p.keywordMatchCount} pdf=${p.hasSchedulePdfLink} d=${p.depth}  ${p.url}`)
    );
  }
}
console.log('\nDONE');
