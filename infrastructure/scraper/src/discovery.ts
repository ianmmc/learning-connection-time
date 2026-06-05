/**
 * School Discovery Module
 *
 * Provides utilities for discovering individual school websites within districts.
 * Based on empirical findings from DISTRICT_WEBSITE_LANDSCAPE_2026.md showing
 * that 80%+ of districts do NOT publish district-wide bell schedules.
 */

import { Browser, Page } from 'playwright';
import { logger } from './logger.js';

export interface SchoolSite {
  url: string;
  name: string;
  level?: 'elementary' | 'middle' | 'high';
  pattern: string; // Which pattern matched
}

export interface DiscoveryResult {
  success: boolean;
  schools: SchoolSite[];
  method: string;
  error?: string;
}

/**
 * State-specific URL patterns for school sites
 * Based on empirical data from DISTRICT_WEBSITE_LANDSCAPE_2026.md
 */
const STATE_PATTERNS: Record<string, string[]> = {
  FL: ['{school}.{district}.k12.fl.us', '{district}.k12.fl.us/{school}'],
  WI: ['{school}.{district}.k12.wi.us', '{district}.k12.wi.us/{school}'],
  OR: ['{school}.{district}.k12.or.us', '{district}.k12.or.us/{school}'],
  CA: ['{district}.org/{school}', '{school}.{district}.org'],
  TX: ['{school}.{district}.net', '{district}.net/{school}', '{school}.{district}.txXXX.net'],
  NY: ['{district}.org/schools/{school}', '{school}.{district}.org'],
  IL: ['{school}.{district}.k12.il.us', '{district}.k12.il.us/{school}'],
  MI: ['{school}.{district}.k12.mi.us', '{district}.k12.mi.us/{school}'],
  PA: ['{school}.{district}.org', '{district}.org/{school}'],
  VA: ['{school}.{district}.org', '{district}.org/{school}'],
  MA: ['{school}.{district}.org', '{district}.org/{school}'],
};

/**
 * Common subdomain prefixes for school sites
 */
const COMMON_PREFIXES = [
  // Elementary
  'elementary', 'elem', 'es', 'primary',
  // Middle
  'middle', 'ms', 'intermediate', 'junior',
  // High
  'high', 'hs', 'senior',
];

/**
 * Extract domain from URL (removes www. prefix)
 */
function extractDomain(url: string): string {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace(/^www\./, '');
  } catch {
    return url.replace(/^www\./, '');
  }
}

/**
 * Get base domain for filtering (e.g., pasco.k12.fl.us from https://www.pasco.k12.fl.us)
 */
function getBaseDomain(url: string): string {
  const domain = extractDomain(url);
  // For k12 domains, keep the full k12.state.us part
  const match = domain.match(/[^.]+\.k12\.[a-z]{2}\.us$/i);
  if (match) return match[0];
  // For other domains, keep last 3 parts
  const parts = domain.split('.');
  return parts.slice(-3).join('.');
}

/**
 * Common school abbreviation patterns (2-4 letter codes)
 */
const SCHOOL_ABBREVIATIONS = [
  // Common elementary abbreviations
  'ces', 'cles', 'ges', 'hes', 'les', 'mes', 'nes', 'pes', 'res', 'ses', 'wes',
  'bes', 'des', 'ees', 'fes', 'jes', 'kes', 'tes', 'ves',
  // Common middle school abbreviations
  'cms', 'gms', 'hms', 'lms', 'mms', 'nms', 'pms', 'rms', 'sms', 'wms',
  'bms', 'dms', 'ems', 'fms', 'jms', 'kms', 'tms', 'vms',
  // Common high school abbreviations
  'chs', 'ghs', 'hhs', 'lhs', 'mhs', 'nhs', 'phs', 'rhs', 'shs', 'whs',
  'bhs', 'dhs', 'ehs', 'fhs', 'jhs', 'khs', 'ths', 'vhs',
  // Direction-based
  'nwes', 'nwms', 'nwhs', 'swes', 'swms', 'swhs',
  'sees', 'sems', 'sehs', 'nees', 'nems', 'nehs',
];

/**
 * Generate subdomain test URLs based on common patterns
 */
export function generateSubdomainTests(
  districtDomain: string,
  state?: string
): string[] {
  const testUrls: string[] = [];

  // Remove www. prefix if present
  const cleanDomain = districtDomain.replace(/^www\./, '');

  // State-specific patterns first (if state provided)
  if (state && STATE_PATTERNS[state]) {
    const patterns = STATE_PATTERNS[state];
    patterns.forEach(pattern => {
      if (pattern.includes('{school}.')) {
        // Subdomain-based pattern
        COMMON_PREFIXES.forEach(prefix => {
          const url = `https://${prefix}.${cleanDomain}`;
          testUrls.push(url);
        });
      }
    });
  }

  // Generic subdomain tests with common prefixes
  COMMON_PREFIXES.forEach(prefix => {
    testUrls.push(`https://${prefix}.${cleanDomain}`);
  });

  // School abbreviations (ces, lhs, gms, etc.)
  SCHOOL_ABBREVIATIONS.forEach(abbr => {
    testUrls.push(`https://${abbr}.${cleanDomain}`);
  });

  return [...new Set(testUrls)]; // Deduplicate
}

/**
 * Test if a URL is accessible (returns 200 or redirects)
 */
export async function testUrlAccessibility(
  browser: Browser,
  url: string,
  timeout: number = 10000
): Promise<boolean> {
  let page: Page | null = null;

  try {
    page = await browser.newPage();

    const response = await page.goto(url, {
      timeout,
      waitUntil: 'domcontentloaded',
    });

    if (!response) {
      return false;
    }

    const status = response.status();
    const finalUrl = page.url();

    // Consider 200 and redirects (301/302/307) as accessible
    const isAccessible = status >= 200 && status < 400;

    // Also check if redirected to a different domain (not accessible)
    if (isAccessible) {
      const originalDomain = extractDomain(url);
      const finalDomain = extractDomain(finalUrl);

      // If redirected to completely different domain, it's not a school site
      if (!finalDomain.includes(originalDomain.split('.')[0])) {
        return false;
      }
    }

    return isAccessible;
  } catch (error) {
    logger.debug(`URL ${url} not accessible: ${(error as Error).message}`);
    return false;
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

/**
 * Extract school links from district website HTML
 */
export async function extractSchoolLinks(
  browser: Browser,
  districtUrl: string,
  timeout: number = 30000
): Promise<SchoolSite[]> {
  let page: Page | null = null;
  const schools: SchoolSite[] = [];

  try {
    page = await browser.newPage();

    await page.goto(districtUrl, {
      timeout,
      waitUntil: 'networkidle',
    });

    // Look for links containing "school" in href or text
    const links = await page.evaluate(() => {
      const allLinks = Array.from(document.querySelectorAll('a'));
      return allLinks
        .filter(link => {
          const href = link.href || '';
          const text = link.textContent || '';
          return (
            href.toLowerCase().includes('school') ||
            text.toLowerCase().includes('school') ||
            href.includes('/schools/')
          );
        })
        .map(link => ({
          url: link.href,
          text: link.textContent?.trim() || '',
        }));
    });

    // Parse links into school sites
    for (const link of links) {
      // Try to determine school level from name
      const text = link.text.toLowerCase();
      let level: SchoolSite['level'] = undefined;

      if (text.includes('elementary') || text.includes('elem')) {
        level = 'elementary';
      } else if (text.includes('middle') || text.includes('junior')) {
        level = 'middle';
      } else if (text.includes('high') || text.includes('senior')) {
        level = 'high';
      }

      schools.push({
        url: link.url,
        name: link.text,
        level,
        pattern: 'extracted_from_district',
      });
    }

    logger.info(`Extracted ${schools.length} school links from ${districtUrl}`);
    return schools;
  } catch (error) {
    logger.error(`Failed to extract school links: ${(error as Error).message}`);
    return [];
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

/**
 * Discover school sites for a district using multiple strategies
 */
export async function discoverSchoolSites(
  browser: Browser,
  districtUrl: string,
  state?: string,
  timeout: number = 30000
): Promise<DiscoveryResult> {
  const districtDomain = extractDomain(districtUrl);
  const schools: SchoolSite[] = [];

  try {
    // Strategy 1: Test common subdomain patterns (in batches for speed)
    logger.info(`Testing subdomain patterns for ${districtDomain}`);
    const subdomainTests = generateSubdomainTests(districtDomain, state);

    // Test in batches of 5 concurrently
    const BATCH_SIZE = 5;
    const MAX_TESTS = 50; // Test up to 50 subdomains
    const testsToRun = subdomainTests.slice(0, MAX_TESTS);

    for (let i = 0; i < testsToRun.length; i += BATCH_SIZE) {
      const batch = testsToRun.slice(i, i + BATCH_SIZE);
      const results = await Promise.all(
        batch.map(async (testUrl) => {
          const isAccessible = await testUrlAccessibility(browser, testUrl, timeout);
          return { testUrl, isAccessible };
        })
      );

      for (const { testUrl, isAccessible } of results) {
        if (isAccessible) {
          const prefix = testUrl.split('//')[1].split('.')[0];
          let level: SchoolSite['level'] = undefined;

          // Infer level from prefix
          if (['elementary', 'elem', 'primary'].includes(prefix) ||
              prefix.endsWith('es') && prefix.length <= 4) {
            level = 'elementary';
          } else if (['middle', 'intermediate', 'junior'].includes(prefix) ||
                     prefix.endsWith('ms') && prefix.length <= 4 ||
                     prefix.endsWith('jhs')) {
            level = 'middle';
          } else if (['high', 'senior'].includes(prefix) ||
                     prefix.endsWith('hs') && prefix.length <= 4) {
            level = 'high';
          }

          schools.push({
            url: testUrl,
            name: `${prefix} school`,
            level,
            pattern: 'subdomain_test',
          });

          logger.info(`Found accessible school site: ${testUrl}`);
        }
      }
    }

    // Strategy 2: Extract links from district website
    if (schools.length < 3) {
      logger.info(`Extracting school links from district site: ${districtUrl}`);
      const extractedSchools = await extractSchoolLinks(browser, districtUrl, timeout);
      schools.push(...extractedSchools);
    }

    // Deduplicate by URL
    const uniqueSchools = Array.from(
      new Map(schools.map(s => [s.url, s])).values()
    );

    return {
      success: uniqueSchools.length > 0,
      schools: uniqueSchools,
      method: uniqueSchools.length > 0 ? 'multi_strategy' : 'none',
    };
  } catch (error) {
    logger.error(`School discovery failed: ${(error as Error).message}`);
    return {
      success: false,
      schools: [],
      method: 'failed',
      error: (error as Error).message,
    };
  }
}

/**
 * Filter schools by grade level
 */
export function filterSchoolsByLevel(
  schools: SchoolSite[],
  level: 'elementary' | 'middle' | 'high'
): SchoolSite[] {
  return schools.filter(s => s.level === level);
}

/**
 * Get representative sample of schools (1 per level)
 * @deprecated Use getSampleByGradeBand for better coverage
 */
export function getRepresentativeSample(schools: SchoolSite[]): SchoolSite[] {
  const sample: SchoolSite[] = [];

  // Get one of each level
  const elementary = filterSchoolsByLevel(schools, 'elementary')[0];
  const middle = filterSchoolsByLevel(schools, 'middle')[0];
  const high = filterSchoolsByLevel(schools, 'high')[0];

  if (elementary) sample.push(elementary);
  if (middle) sample.push(middle);
  if (high) sample.push(high);

  // If we have schools but couldn't determine level, include up to 3
  if (sample.length === 0 && schools.length > 0) {
    sample.push(...schools.slice(0, 3));
  }

  return sample;
}

/**
 * Infer grade level from URL patterns
 * Returns level if detected, undefined otherwise
 */
export function inferLevelFromUrl(url: string): SchoolSite['level'] | undefined {
  const urlLower = url.toLowerCase();

  // Elementary patterns
  const elemPatterns = [
    '/elem', '-elem', '.elem',
    '/es/', '-es.', '/es.',
    'elementary',
    '/primary', '-primary', '.primary',
    '/grade-school', '/gradeschool',
  ];

  // Middle school patterns
  const middlePatterns = [
    '/middle', '-middle', '.middle',
    '/ms/', '-ms.', '/ms.',
    '/junior', '-junior', '.junior',
    '/jhs/', '-jhs.', '/jhs.',
    '/intermediate',
  ];

  // High school patterns
  const highPatterns = [
    '/high', '-high', '.high',
    '/hs/', '-hs.', '/hs.',
    '/senior', '-senior', '.senior',
    '/shs/', '-shs.',
  ];

  if (elemPatterns.some(p => urlLower.includes(p))) return 'elementary';
  if (middlePatterns.some(p => urlLower.includes(p))) return 'middle';
  if (highPatterns.some(p => urlLower.includes(p))) return 'high';

  return undefined;
}

/**
 * Infer grade level from school name/text
 */
export function inferLevelFromText(text: string): SchoolSite['level'] | undefined {
  const textLower = text.toLowerCase();

  // Elementary
  if (
    textLower.includes('elementary') ||
    textLower.includes(' elem ') ||
    textLower.endsWith(' elem') ||
    textLower.includes('primary') ||
    textLower.includes('grade school') ||
    /\bes\b/.test(textLower)  // standalone "ES"
  ) {
    return 'elementary';
  }

  // Middle
  if (
    textLower.includes('middle') ||
    textLower.includes('junior high') ||
    textLower.includes('intermediate') ||
    /\bms\b/.test(textLower) ||  // standalone "MS"
    /\bjhs\b/.test(textLower)    // standalone "JHS"
  ) {
    return 'middle';
  }

  // High
  if (
    textLower.includes('high school') ||
    textLower.includes('senior high') ||
    /\bhs\b/.test(textLower) ||  // standalone "HS"
    /\bshs\b/.test(textLower)    // standalone "SHS"
  ) {
    return 'high';
  }

  return undefined;
}

/**
 * Get sample of schools by grade band (3-4 per band, or all if ≤2)
 *
 * Strategy:
 * - For each grade band with 3+ schools: return 3-4 randomly selected
 * - For grade bands with 1-2 schools: return all
 * - For unknown level: distribute across bands if needed, or include separately
 */
export function getSampleByGradeBand(
  schools: SchoolSite[],
  perBand: number = 4
): SchoolSite[] {
  const sample: SchoolSite[] = [];

  // Group by level
  const elementary = filterSchoolsByLevel(schools, 'elementary');
  const middle = filterSchoolsByLevel(schools, 'middle');
  const high = filterSchoolsByLevel(schools, 'high');
  const unknown = schools.filter(s => s.level === undefined);

  // Helper to sample from array
  const sampleFrom = (arr: SchoolSite[], count: number): SchoolSite[] => {
    if (arr.length <= count) return arr;
    // Shuffle and take first N
    const shuffled = [...arr].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, count);
  };

  // Sample from each band
  sample.push(...sampleFrom(elementary, perBand));
  sample.push(...sampleFrom(middle, perBand));
  sample.push(...sampleFrom(high, perBand));

  // If we have schools with unknown level, try to infer or include some
  if (unknown.length > 0) {
    // Try to re-infer levels from URLs
    const stillUnknown: SchoolSite[] = [];
    for (const school of unknown) {
      const urlLevel = inferLevelFromUrl(school.url);
      if (urlLevel) {
        school.level = urlLevel;
        // Check if this band needs more schools
        const bandCount = sample.filter(s => s.level === urlLevel).length;
        if (bandCount < perBand) {
          sample.push(school);
        }
      } else {
        stillUnknown.push(school);
      }
    }

    // Include up to perBand unknown schools if we have gaps
    const totalBandCoverage = sample.length;
    const maxUnknown = Math.max(0, (perBand * 3) - totalBandCoverage);
    if (maxUnknown > 0 && stillUnknown.length > 0) {
      sample.push(...sampleFrom(stillUnknown, Math.min(maxUnknown, perBand)));
    }
  }

  return sample;
}

/**
 * Enhanced school link extraction from district homepage
 * More comprehensive than basic extractSchoolLinks
 */
export async function extractSchoolLinksEnhanced(
  browser: Browser,
  districtUrl: string,
  timeout: number = 30000
): Promise<SchoolSite[]> {
  let page: Page | null = null;
  const schools: SchoolSite[] = [];

  try {
    page = await browser.newPage();

    await page.goto(districtUrl, {
      timeout,
      waitUntil: 'networkidle',
    });

    // Extract links with multiple strategies
    const links = await page.evaluate(() => {
      const results: Array<{ url: string; text: string; context: string }> = [];
      const seenUrls = new Set<string>();

      // Strategy 1: Links in "schools" or "our schools" sections
      const schoolSections = document.querySelectorAll(
        '[class*="school"], [id*="school"], nav, .menu, .navigation'
      );

      // Strategy 2: All links, filtered by keywords
      const allLinks = Array.from(document.querySelectorAll('a[href]'));

      for (const link of allLinks) {
        const href = link.getAttribute('href') || '';
        const text = (link.textContent || '').trim();

        // Skip empty/anchor/javascript links
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;

        // Build full URL
        let fullUrl: string;
        try {
          fullUrl = new URL(href, window.location.origin).href;
        } catch {
          continue;
        }

        // Skip already seen
        if (seenUrls.has(fullUrl)) continue;

        // Check if this looks like a school link
        const hrefLower = href.toLowerCase();
        const textLower = text.toLowerCase();

        const isSchoolLink = (
          // URL patterns
          hrefLower.includes('/schools/') ||
          hrefLower.includes('/school/') ||
          hrefLower.includes('/es/') ||
          hrefLower.includes('/ms/') ||
          hrefLower.includes('/hs/') ||
          hrefLower.includes('-elementary') ||
          hrefLower.includes('-middle') ||
          hrefLower.includes('-high') ||
          hrefLower.includes('elementary') ||
          hrefLower.includes('middle-school') ||
          hrefLower.includes('highschool') ||
          // Text patterns
          textLower.includes('elementary') ||
          textLower.includes('middle') ||
          textLower.includes('high school') ||
          textLower.includes('junior high') ||
          textLower.includes('primary') ||
          // Generic school link
          (textLower.includes('school') && text.length < 60) // Short school name
        );

        if (isSchoolLink) {
          seenUrls.add(fullUrl);

          // Get surrounding context (parent element text)
          const parent = link.closest('li, div, td');
          const context = parent?.textContent?.trim().substring(0, 100) || '';

          results.push({ url: fullUrl, text, context });
        }
      }

      return results;
    });

    // Process extracted links (in Node.js context, can use helper functions)
    for (const link of links) {
      // Infer level from multiple sources
      let level = inferLevelFromUrl(link.url);
      if (!level) level = inferLevelFromText(link.text);
      if (!level) level = inferLevelFromText(link.context);

      // Skip if this looks like a directory/finder page or non-school content
      const textLower = link.text.toLowerCase();
      const urlLower = link.url.toLowerCase();

      // Get base domain for comparison
      const baseDomain = getBaseDomain(districtUrl);
      const linkDomain = getBaseDomain(link.url);

      // Skip directory/search pages (but remember them for later)
      if (
        textLower.includes('find') ||
        textLower.includes('search') ||
        textLower.includes('locator') ||
        textLower.includes('directory') ||
        textLower.includes('all schools') ||
        textLower === 'schools' ||
        textLower === 'our schools'
      ) {
        continue;
      }

      // Skip news, policies, board, foundation, social media links
      if (
        urlLower.includes('/news') ||
        urlLower.includes('/policy') ||
        urlLower.includes('/board') ||
        urlLower.includes('foundation') ||
        urlLower.includes('/podcast') ||
        urlLower.includes('choice') ||
        urlLower.includes('enrollment') ||
        urlLower.includes('facebook.com') ||
        urlLower.includes('twitter.com') ||
        urlLower.includes('instagram.com') ||
        urlLower.includes('youtube.com')
      ) {
        continue;
      }

      // Skip external domains (different base domain)
      if (!linkDomain.includes(baseDomain) && !baseDomain.includes(linkDomain)) {
        continue;
      }

      schools.push({
        url: link.url,
        name: link.text || 'Unknown School',
        level,
        pattern: 'enhanced_extraction',
      });
    }

    logger.info(`Enhanced extraction found ${schools.length} school links from ${districtUrl}`);
    return schools;
  } catch (error) {
    logger.error(`Enhanced school link extraction failed: ${(error as Error).message}`);
    return [];
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

/**
 * Find school directory link on district homepage
 */
async function findSchoolDirectoryLink(
  browser: Browser,
  districtUrl: string,
  timeout: number = 30000
): Promise<string | null> {
  let page: Page | null = null;

  try {
    page = await browser.newPage();
    await page.goto(districtUrl, { timeout, waitUntil: 'networkidle' });

    // Look for links to school directory/list
    const directoryLink = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a[href]')) as HTMLAnchorElement[];

      // Priority patterns for school directory links
      const patterns = [
        /\/schools\/?$/i,
        /\/our-schools\/?$/i,
        /\/school-list\/?$/i,
        /\/school-directory\/?$/i,
        /\/find-school\/?$/i,
        /\/all-schools\/?$/i,
      ];

      // Text patterns
      const textPatterns = [
        /^schools$/i,
        /^our schools$/i,
        /^find a school$/i,
        /^school directory$/i,
        /^all schools$/i,
        /^school list$/i,
      ];

      for (const link of links) {
        const href = link.getAttribute('href') || '';
        const text = (link.textContent || '').trim();

        // Check URL patterns
        if (patterns.some(p => p.test(href))) {
          return link.href;
        }

        // Check text patterns
        if (textPatterns.some(p => p.test(text))) {
          return link.href;
        }
      }

      return null;
    });

    return directoryLink;
  } catch (error) {
    logger.error(`Failed to find school directory link: ${(error as Error).message}`);
    return null;
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

/**
 * Extract school links from a school directory/list page
 */
async function extractSchoolsFromDirectory(
  browser: Browser,
  directoryUrl: string,
  districtUrl: string,
  timeout: number = 30000
): Promise<SchoolSite[]> {
  let page: Page | null = null;
  const schools: SchoolSite[] = [];

  try {
    page = await browser.newPage();
    await page.goto(directoryUrl, { timeout, waitUntil: 'networkidle' });

    const baseDomain = getBaseDomain(districtUrl);

    // Extract all school links from the directory
    const links = await page.evaluate((baseDomain: string) => {
      const results: Array<{ url: string; text: string }> = [];
      const seenUrls = new Set<string>();

      const allLinks = Array.from(document.querySelectorAll('a[href]'));

      for (const link of allLinks) {
        const href = link.getAttribute('href') || '';
        const text = (link.textContent || '').trim();

        // Skip empty/anchor/javascript/mailto links
        if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) continue;

        // Build full URL
        let fullUrl: string;
        try {
          fullUrl = new URL(href, window.location.origin).href;
        } catch {
          continue;
        }

        // Skip already seen
        if (seenUrls.has(fullUrl)) continue;

        const textLower = text.toLowerCase();
        const urlLower = fullUrl.toLowerCase();

        // Must be on district domain (including subdomains)
        if (!urlLower.includes(baseDomain)) continue;

        // Skip if too short text (likely not a school name)
        if (text.length < 3) continue;

        // Skip section headers (e.g., "Elementary Schools", "Middle Schools", "High Schools", "Junior High Schools")
        if (
          /^(elementary|middle|high|primary|junior|senior|jr)\s*(high)?\s+schools?$/i.test(text) ||
          /schools\/(elementary|middle|high|junior|jr|all)_?(high)?_?schools?/i.test(urlLower)
        ) {
          continue;
        }

        // Skip common non-school links
        if (
          urlLower.includes('/news') ||
          urlLower.includes('/calendar') ||
          urlLower.includes('/contact') ||
          urlLower.includes('/staff') ||
          urlLower.includes('/directions') ||
          urlLower.includes('/employment') ||
          urlLower.endsWith('/schools') ||
          urlLower.endsWith('/schools/') ||
          textLower.includes('more info') ||
          textLower.includes('learn more') ||
          textLower.includes('view all') ||
          textLower === 'schools' ||
          textLower === 'our schools'
        ) {
          continue;
        }

        // Looks like a school if:
        // 1. Text contains school-level keywords
        // 2. URL looks like a school subdomain or path
        // 3. Text matches common school name patterns
        const hasSchoolKeyword = (
          textLower.includes('elementary') ||
          textLower.includes('middle') ||
          textLower.includes('high') ||
          textLower.includes('primary') ||
          textLower.includes('junior') ||
          textLower.includes('intermediate') ||
          textLower.includes('academy') ||
          textLower.includes('magnet') ||
          textLower.includes('school')
        );

        // Check if it's a subdomain (likely a school)
        const urlHostname = new URL(fullUrl).hostname;
        const isSubdomain = urlHostname !== `www.${baseDomain}` &&
                           urlHostname !== baseDomain &&
                           urlHostname.endsWith(baseDomain);

        if (hasSchoolKeyword || isSubdomain) {
          seenUrls.add(fullUrl);
          results.push({ url: fullUrl, text });
        }
      }

      return results;
    }, baseDomain);

    // Process links and infer grade levels
    for (const link of links) {
      const level = inferLevelFromText(link.text) || inferLevelFromUrl(link.url);

      schools.push({
        url: link.url,
        name: link.text,
        level,
        pattern: 'directory_extraction',
      });
    }

    logger.info(`Extracted ${schools.length} schools from directory: ${directoryUrl}`);
    return schools;
  } catch (error) {
    logger.error(`Failed to extract schools from directory: ${(error as Error).message}`);
    return [];
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

/**
 * Enhanced school discovery with grade band sampling
 * Returns 3-4 schools per grade band (or all if ≤2 in a band)
 *
 * Strategy: Follow links to school directory page rather than guessing subdomains
 */
export async function discoverSchoolsWithSampling(
  browser: Browser,
  districtUrl: string,
  state?: string,
  options: {
    timeout?: number;
    perBand?: number;
  } = {}
): Promise<DiscoveryResult & { sample: SchoolSite[] }> {
  const { timeout = 30000, perBand = 4 } = options;
  const allSchools: SchoolSite[] = [];
  const urlsInList = new Set<string>();

  // Strategy 1: Find and follow school directory link (PRIMARY)
  logger.info('Looking for school directory link...');
  const directoryLink = await findSchoolDirectoryLink(browser, districtUrl, timeout);

  if (directoryLink) {
    logger.info(`Found school directory: ${directoryLink}`);
    const directorySchools = await extractSchoolsFromDirectory(
      browser,
      directoryLink,
      districtUrl,
      timeout
    );

    for (const school of directorySchools) {
      if (!urlsInList.has(school.url)) {
        allSchools.push(school);
        urlsInList.add(school.url);
      }
    }

    // Check if we need to follow sub-pages (e.g., /schools/middle_schools)
    // This happens when directory organizes schools by level with separate pages
    const levelCounts = {
      elementary: allSchools.filter(s => s.level === 'elementary').length,
      middle: allSchools.filter(s => s.level === 'middle').length,
      high: allSchools.filter(s => s.level === 'high').length,
    };

    // If we found many elementary but few middle/high, try sub-pages
    if (levelCounts.elementary > 5 && (levelCounts.middle < 3 || levelCounts.high < 3)) {
      logger.info('Found mostly elementary, checking for level-specific sub-pages...');

      // Try common sub-page patterns (including junior high variants)
      const subPages = [
        `${directoryLink}/middle_schools`,
        `${directoryLink}/high_schools`,
        `${directoryLink}/junior_high_schools`,
        `${directoryLink}/jr_high_schools`,
        directoryLink.replace('/schools', '/schools/middle_schools'),
        directoryLink.replace('/schools', '/schools/high_schools'),
        directoryLink.replace('/schools', '/schools/junior_high_schools'),
        directoryLink.replace('/schools', '/schools/jr_high_schools'),
      ];

      for (const subPage of subPages) {
        if (urlsInList.has(subPage)) continue;

        try {
          logger.info(`Checking sub-page: ${subPage}`);
          const subPageSchools = await extractSchoolsFromDirectory(
            browser,
            subPage,
            districtUrl,
            timeout
          );

          for (const school of subPageSchools) {
            if (!urlsInList.has(school.url)) {
              allSchools.push(school);
              urlsInList.add(school.url);
            }
          }
        } catch (error) {
          // Sub-page might not exist, that's OK
          logger.debug(`Sub-page not accessible: ${subPage}`);
        }
      }
    }
  } else {
    logger.info('No school directory link found, trying homepage extraction...');
  }

  // Strategy 2: If directory didn't yield enough schools, try homepage extraction
  if (allSchools.length < 5) {
    logger.info('Trying homepage link extraction...');
    const homepageSchools = await extractSchoolLinksEnhanced(browser, districtUrl, timeout);
    for (const school of homepageSchools) {
      if (!urlsInList.has(school.url)) {
        allSchools.push(school);
        urlsInList.add(school.url);
      }
    }
  }

  // Strategy 3: As last resort, try subdomain testing (for districts without directories)
  if (allSchools.length < 3) {
    logger.info('Few schools found, trying subdomain testing as fallback...');
    const subdomainResult = await discoverSchoolSites(browser, districtUrl, state, timeout);
    for (const school of subdomainResult.schools) {
      if (!urlsInList.has(school.url)) {
        allSchools.push(school);
        urlsInList.add(school.url);
      }
    }
  }

  // Get sample by grade band
  const sample = getSampleByGradeBand(allSchools, perBand);

  // Log summary
  const levelCounts = {
    elementary: allSchools.filter(s => s.level === 'elementary').length,
    middle: allSchools.filter(s => s.level === 'middle').length,
    high: allSchools.filter(s => s.level === 'high').length,
    unknown: allSchools.filter(s => !s.level).length,
  };

  logger.info(`School discovery complete for ${districtUrl}:`, {
    total: allSchools.length,
    ...levelCounts,
    sampleSize: sample.length,
  });

  return {
    success: allSchools.length > 0,
    schools: allSchools,
    sample,
    method: 'enhanced_with_sampling',
  };
}
