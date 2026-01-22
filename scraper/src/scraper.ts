/**
 * Crawlee/Playwright Scraper
 *
 * Core scraping functionality with:
 * - JavaScript rendering via Playwright
 * - Security block detection (Cloudflare, WAF, CAPTCHA)
 * - HTML to markdown conversion
 * - Ethical constraints (no bot evasion)
 */

import { Page, Response } from 'playwright';
import { BrowserPool, getBrowserPool } from './pool.js';
import { ScrapeRequest, ScrapeResponse, SecurityBlockIndicators, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';

/**
 * Detect if response indicates security blocking
 */
function detectSecurityBlock(
  response: Response | null,
  html: string
): SecurityBlockIndicators {
  const statusCode = response?.status() ?? 0;

  // Cloudflare challenge patterns
  const cloudflarePatterns = [
    'Checking your browser',
    'Just a moment...',
    'Please Wait... | Cloudflare',
    'cf-browser-verification',
    'cf_chl_prog',
    '__cf_chl_jschl_tk__',
    'Attention Required! | Cloudflare',
  ];

  const cloudflareChallenge = cloudflarePatterns.some(pattern =>
    html.includes(pattern)
  );

  // WAF/403 patterns
  const wafPatterns = [
    'Access Denied',
    'Access to this page has been denied',
    'Request blocked',
    'Forbidden',
    'You don\'t have permission',
    'Error 403',
  ];

  const wafBlocked = statusCode === 403 || wafPatterns.some(pattern =>
    html.includes(pattern)
  );

  // CAPTCHA patterns
  const captchaPatterns = [
    'g-recaptcha',
    'h-captcha',
    'captcha-container',
    'verify you are human',
    'prove you\'re not a robot',
    'challenge-form',
  ];

  const captchaDetected = captchaPatterns.some(pattern =>
    html.toLowerCase().includes(pattern.toLowerCase())
  );

  return {
    cloudflareChallenge,
    wafBlocked,
    captchaDetected,
    statusCode,
  };
}

/**
 * Convert HTML to basic markdown
 */
function htmlToMarkdown(html: string): string {
  return html
    // Remove scripts and styles
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    // Convert headings
    .replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, '\n# $1\n')
    .replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, '\n## $1\n')
    .replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, '\n### $1\n')
    .replace(/<h4[^>]*>([\s\S]*?)<\/h4>/gi, '\n#### $1\n')
    // Convert paragraphs and breaks
    .replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '\n$1\n')
    .replace(/<br[^>]*>/gi, '\n')
    // Convert lists
    .replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n')
    // Convert links and emphasis
    .replace(/<a[^>]+href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')
    .replace(/<(strong|b)[^>]*>([\s\S]*?)<\/\1>/gi, '**$2**')
    .replace(/<(em|i)[^>]*>([\s\S]*?)<\/\1>/gi, '*$2*')
    // Remove remaining tags
    .replace(/<[^>]+>/g, '')
    // Decode entities
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    // Clean up whitespace
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Scrape a single page with JavaScript rendering
 */
export async function scrapePage(
  request: ScrapeRequest,
  pool?: BrowserPool
): Promise<ScrapeResponse> {
  const browserPool = pool ?? getBrowserPool();
  const timeout = request.timeout ?? 30000;
  const waitFor = request.waitFor ?? 0;
  const startTime = Date.now();

  let browser;
  let context;
  let page: Page | undefined;

  try {
    // Acquire browser from pool
    browser = await browserPool.acquire();
    context = await browserPool.createContext(browser, DEFAULT_CONFIG.userAgent);
    page = await context.newPage();

    logger.debug(`Navigating to ${request.url}`);

    // Navigate with networkidle to wait for JS
    const response = await page.goto(request.url, {
      timeout,
      waitUntil: 'networkidle',
    });

    // Additional wait if specified (for slow JS)
    if (waitFor > 0) {
      await page.waitForTimeout(waitFor);
    }

    // Get page content
    const html = await page.content();
    const title = await page.title();

    // Check for security blocks
    const securityIndicators = detectSecurityBlock(response, html);
    const isBlocked =
      securityIndicators.cloudflareChallenge ||
      securityIndicators.wafBlocked ||
      securityIndicators.captchaDetected;

    if (isBlocked) {
      logger.warn(`Security block detected for ${request.url}`, securityIndicators);
      return {
        success: false,
        url: request.url,
        error: 'Security block detected - flagged for manual collection',
        errorCode: 'BLOCKED',
        blocked: true,
        timing: Date.now() - startTime,
      };
    }

    // Check for 404
    if (response?.status() === 404) {
      logger.debug(`404 Not Found: ${request.url}`);
      return {
        success: false,
        url: request.url,
        error: 'Page not found',
        errorCode: 'NOT_FOUND',
        timing: Date.now() - startTime,
      };
    }

    // Success
    const markdown = htmlToMarkdown(html);

    logger.debug(`Successfully scraped ${request.url} (${html.length} bytes)`);

    return {
      success: true,
      url: request.url,
      html,
      markdown,
      title,
      timing: Date.now() - startTime,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    const isTimeout = errorMessage.includes('Timeout') || errorMessage.includes('timeout');

    logger.error(`Scrape failed for ${request.url}: ${errorMessage}`);

    return {
      success: false,
      url: request.url,
      error: errorMessage,
      errorCode: isTimeout ? 'TIMEOUT' : 'NETWORK_ERROR',
      timing: Date.now() - startTime,
    };
  } finally {
    // Clean up
    if (page) {
      try {
        await page.close();
      } catch {
        // Ignore close errors
      }
    }
    if (context) {
      try {
        await context.close();
      } catch {
        // Ignore close errors
      }
    }
    if (browser) {
      browserPool.release(browser);
    }
  }
}

/**
 * Scraper service class for managing state
 */
export class Scraper {
  private pool: BrowserPool;
  private initialized = false;

  constructor() {
    this.pool = getBrowserPool();
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    await this.pool.initialize();
    this.initialized = true;
  }

  async scrape(request: ScrapeRequest): Promise<ScrapeResponse> {
    if (!this.initialized) {
      await this.initialize();
    }
    return scrapePage(request, this.pool);
  }

  getPoolStats() {
    return this.pool.getStats();
  }

  async shutdown(): Promise<void> {
    await this.pool.shutdown();
    this.initialized = false;
  }
}
