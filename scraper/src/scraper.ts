/**
 * Crawlee/Playwright Scraper
 *
 * Core scraping functionality with:
 * - JavaScript rendering via Playwright
 * - Security block detection (Cloudflare, WAF, CAPTCHA)
 * - HTML to markdown conversion (REQ-029: DOMPurify + Turndown)
 * - Ethical constraints (no bot evasion)
 */

import { Page, Response } from 'playwright';
import { JSDOM } from 'jsdom';
import createDOMPurify from 'dompurify';
import TurndownService from 'turndown';
import { BrowserPool, getBrowserPool } from './pool.js';
import { ScrapeRequest, ScrapeResponse, SecurityBlockIndicators, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';

// Initialize DOMPurify with jsdom window (REQ-029)
// Type casting needed because JSDOM's Window doesn't exactly match DOMPurify's expected WindowLike
const jsdomWindow = new JSDOM('').window;
const DOMPurify = createDOMPurify(jsdomWindow as unknown as Parameters<typeof createDOMPurify>[0]);

// Initialize Turndown for HTML to Markdown conversion (REQ-029)
const turndownService = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced',
  emDelimiter: '*',
});

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
 * Convert HTML to sanitized markdown (REQ-029)
 *
 * Uses DOMPurify for XSS-safe sanitization and Turndown for conversion.
 * This replaces the previous regex-based approach which was vulnerable to XSS.
 */
function htmlToMarkdown(html: string): string {
  try {
    // Sanitize HTML with DOMPurify - removes scripts, event handlers, dangerous elements
    const sanitized = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr',
        'ul', 'ol', 'li',
        'a', 'strong', 'b', 'em', 'i', 'u',
        'blockquote', 'pre', 'code',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'div', 'span',
      ],
      ALLOWED_ATTR: ['href', 'title'],  // Only allow safe attributes
      FORBID_TAGS: ['script', 'style', 'iframe', 'form', 'input', 'object', 'embed'],
      FORBID_ATTR: ['onclick', 'onerror', 'onload', 'onmouseover', 'onfocus', 'onblur'],
    });

    // Convert sanitized HTML to Markdown using Turndown
    const markdown = turndownService.turndown(sanitized);

    // Clean up excessive whitespace
    return markdown
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  } catch (error) {
    logger.warn('HTML to Markdown conversion failed, returning empty string', { error });
    return '';
  }
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
  public pool: BrowserPool; // Made public for school discovery
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
