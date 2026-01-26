/**
 * Crawlee-based Website Mapper
 *
 * Maps a district website and collects rich metadata for each page
 * to enable intelligent URL ranking by Ollama.
 */

import { PlaywrightCrawler, RequestQueue, Configuration } from 'crawlee';
import { Page } from 'playwright';
import { logger } from './logger.js';

// Bell schedule related keywords
const BELL_KEYWORDS = ['bell', 'schedule', 'times', 'hours', 'start', 'end', 'dismissal', 'period'];

/**
 * Rich page data collected during crawl for Ollama ranking
 */
export interface CrawleePageData {
  // Core identifiers
  url: string;
  title: string;
  depth: number;

  // Lightweight metadata
  metaDescription: string | null;
  h1: string | null;
  breadcrumb: string | null;

  // Navigation context
  linkTextUsedToReachPage: string;

  // Content signals
  timePatternCount: number;
  hasSchedulePdfLink: boolean;

  // Classification helpers
  keywordMatchCount: number;
  outboundLinkCount: number;
}

/**
 * Map request parameters
 */
export interface MapRequest {
  url: string;
  maxRequests?: number;
  maxDepth?: number;
  patterns?: {
    includeGlobs?: string[];
    excludeGlobs?: string[];
  };
}

/**
 * Map response
 */
export interface MapResponse {
  success: boolean;
  pages: CrawleePageData[];
  stats: {
    pagesVisited: number;
    pagesWithTimePatterns: number;
    pagesWithBellKeywords: number;
    durationMs: number;
  };
  error?: string;
}

/**
 * Extract rich metadata from a page
 */
async function extractPageData(
  page: Page,
  url: string,
  depth: number,
  linkText: string
): Promise<CrawleePageData> {
  const title = await page.title();

  // Meta description
  const metaDescription = await page
    .$eval('meta[name="description"]', (el) => el.getAttribute('content'))
    .catch(() => null);

  // H1 tag
  const h1 = await page
    .$eval('h1', (el) => el.textContent?.trim() || null)
    .catch(() => null);

  // Breadcrumb - try multiple selectors
  const breadcrumb = await page
    .$eval(
      'nav[aria-label*="breadcrumb"], .breadcrumb, [class*="breadcrumb"]',
      (el) => el.textContent?.replace(/\s+/g, ' ').trim() || null
    )
    .catch(() => null);

  // Time pattern count (e.g., "8:00 AM", "3:15 PM")
  const timePatternCount = await page.evaluate(() => {
    const text = document.body.innerText;
    const matches = text.match(/\d{1,2}:\d{2}\s*(AM|PM|am|pm|a\.m\.|p\.m\.)?/g);
    return matches ? matches.length : 0;
  });

  // Check for PDF links with "schedule" in text
  const hasSchedulePdfLink = await page.evaluate(() => {
    const pdfLinks = document.querySelectorAll('a[href$=".pdf"], a[href*=".pdf?"]');
    return Array.from(pdfLinks).some((a) =>
      /schedule|bell|times|hours/i.test(a.textContent || '')
    );
  });

  // Keyword match count in visible content
  const keywordMatchCount = await page.evaluate((keywords: string[]) => {
    const text = (document.body.innerText || '').toLowerCase();
    return keywords.reduce((count, kw) => {
      const regex = new RegExp(kw, 'gi');
      const matches = text.match(regex);
      return count + (matches ? matches.length : 0);
    }, 0);
  }, BELL_KEYWORDS);

  // Outbound link count
  const outboundLinkCount = await page.$$eval('a[href]', (links) => links.length);

  return {
    url,
    title: title.substring(0, 200),
    depth,
    metaDescription: metaDescription?.substring(0, 500) || null,
    h1: h1?.substring(0, 200) || null,
    breadcrumb: breadcrumb?.substring(0, 200) || null,
    linkTextUsedToReachPage: linkText.substring(0, 100),
    timePatternCount,
    hasSchedulePdfLink,
    keywordMatchCount,
    outboundLinkCount,
  };
}

/**
 * Map a district website using Crawlee
 */
export async function mapWebsite(mapRequest: MapRequest): Promise<MapResponse> {
  const startTime = Date.now();
  const pages: CrawleePageData[] = [];
  const maxRequests = mapRequest.maxRequests || 100;
  const maxDepth = mapRequest.maxDepth || 4;
  const patterns = mapRequest.patterns;

  logger.info(`Starting website map: ${mapRequest.url}`, {
    maxRequests,
    maxDepth,
    patterns,
  });

  // Configure Crawlee to use in-memory storage (no persistent files)
  const config = new Configuration({
    persistStorage: false,
    purgeOnStart: true,
  });

  try {
    // Create request queue
    const requestQueue = await RequestQueue.open(undefined, { config });

    // Add initial URL
    await requestQueue.addRequest({
      url: mapRequest.url,
      userData: { depth: 0, linkText: '' },
    });

    const crawler = new PlaywrightCrawler(
      {
        requestQueue,
        maxRequestsPerCrawl: maxRequests,
        maxConcurrency: 3,
        requestHandlerTimeoutSecs: 60,
        navigationTimeoutSecs: 30,

        // Browser launch options
        launchContext: {
          launchOptions: {
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
          },
        },

        async requestHandler({ request, page, enqueueLinks, log }) {
          const depth = (request.userData.depth as number) || 0;
          const linkText = (request.userData.linkText as string) || '';

          // Skip if too deep
          if (depth > maxDepth) {
            return;
          }

          try {
            // Wait for content to load
            await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

            // Extract page data
            const pageData = await extractPageData(page, request.url, depth, linkText);
            pages.push(pageData);

            log.info(
              `Mapped: ${request.url} (depth: ${depth}, times: ${pageData.timePatternCount}, keywords: ${pageData.keywordMatchCount})`
            );

            // Enqueue links from same domain
            await enqueueLinks({
              strategy: 'same-domain',
              globs: patterns?.includeGlobs,
              exclude: patterns?.excludeGlobs,
              transformRequestFunction: (req) => {
                // Get link text for the new request
                const newLinkText = req.userData?.linkText || '';
                req.userData = {
                  depth: depth + 1,
                  linkText: newLinkText,
                };
                return req;
              },
            });
          } catch (error) {
            log.warning(`Failed to extract data from ${request.url}: ${(error as Error).message}`);
          }
        },

        async failedRequestHandler({ request, log }) {
          log.error(`Failed to crawl: ${request.url}`);
        },
      },
      config
    );

    await crawler.run();

    const durationMs = Date.now() - startTime;
    const pagesWithTimePatterns = pages.filter((p) => p.timePatternCount > 0).length;
    const pagesWithBellKeywords = pages.filter((p) => p.keywordMatchCount > 0).length;

    logger.info(`Website map complete: ${mapRequest.url}`, {
      pagesVisited: pages.length,
      pagesWithTimePatterns,
      pagesWithBellKeywords,
      durationMs,
    });

    return {
      success: true,
      pages,
      stats: {
        pagesVisited: pages.length,
        pagesWithTimePatterns,
        pagesWithBellKeywords,
        durationMs,
      },
    };
  } catch (error) {
    logger.error(`Website map failed: ${(error as Error).message}`);
    return {
      success: false,
      pages: [],
      stats: {
        pagesVisited: 0,
        pagesWithTimePatterns: 0,
        pagesWithBellKeywords: 0,
        durationMs: Date.now() - startTime,
      },
      error: (error as Error).message,
    };
  }
}
