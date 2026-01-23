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
 * Extract domain from URL
 */
function extractDomain(url: string): string {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname;
  } catch {
    return url;
  }
}

/**
 * Generate subdomain test URLs based on common patterns
 */
export function generateSubdomainTests(
  districtDomain: string,
  state?: string
): string[] {
  const testUrls: string[] = [];

  // State-specific patterns first (if state provided)
  if (state && STATE_PATTERNS[state]) {
    const patterns = STATE_PATTERNS[state];
    patterns.forEach(pattern => {
      if (pattern.includes('{school}.')) {
        // Subdomain-based pattern
        COMMON_PREFIXES.forEach(prefix => {
          const url = `https://${prefix}.${districtDomain}`;
          testUrls.push(url);
        });
      }
    });
  }

  // Generic subdomain tests
  COMMON_PREFIXES.forEach(prefix => {
    testUrls.push(`https://${prefix}.${districtDomain}`);
  });

  // School abbreviations (lhs, wms, etc.)
  testUrls.push(`https://lhs.${districtDomain}`); // Lincoln High School pattern
  testUrls.push(`https://wms.${districtDomain}`); // Washington Middle School pattern
  testUrls.push(`https://ees.${districtDomain}`); // East Elementary School pattern

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
    // Strategy 1: Test common subdomain patterns
    logger.info(`Testing subdomain patterns for ${districtDomain}`);
    const subdomainTests = generateSubdomainTests(districtDomain, state);

    for (const testUrl of subdomainTests.slice(0, 10)) { // Limit to first 10 tests
      const isAccessible = await testUrlAccessibility(browser, testUrl, timeout);
      if (isAccessible) {
        const prefix = testUrl.split('//')[1].split('.')[0];
        let level: SchoolSite['level'] = undefined;

        if (['elementary', 'elem', 'es', 'primary'].includes(prefix)) {
          level = 'elementary';
        } else if (['middle', 'ms', 'intermediate', 'junior'].includes(prefix)) {
          level = 'middle';
        } else if (['high', 'hs', 'senior'].includes(prefix)) {
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
