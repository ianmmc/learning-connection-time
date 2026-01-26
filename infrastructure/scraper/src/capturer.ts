/**
 * PDF Capturer
 *
 * Captures multiple pages as PDFs using Playwright.
 * Used after Ollama ranks URLs to capture the most promising pages.
 */

import { chromium, Browser, Page } from 'playwright';
import * as fs from 'fs/promises';
import * as path from 'path';
import { logger } from './logger.js';

/**
 * Capture request parameters
 */
export interface CaptureRequest {
  urls: string[];
  outputDir: string;
  timeout?: number;
  pdfOptions?: {
    format?: 'Letter' | 'A4';
    scale?: number;
    margin?: {
      top?: string;
      bottom?: string;
      left?: string;
      right?: string;
    };
  };
}

/**
 * Single capture result
 */
export interface CaptureResult {
  url: string;
  success: boolean;
  filename?: string;
  filepath?: string;
  sizeBytes?: number;
  error?: string;
  title?: string;
  modalsDismissed?: boolean;
}

/**
 * Capture response
 */
export interface CaptureResponse {
  success: boolean;
  results: CaptureResult[];
  stats: {
    total: number;
    successful: number;
    failed: number;
    durationMs: number;
  };
  error?: string;
}

/**
 * CSS to inject for hiding modal overlays globally.
 * This is high-leverage: works across frameworks, survives A/B tests.
 */
const MODAL_HIDING_CSS = `
  *[role="dialog"],
  *[aria-modal="true"],
  .modal,
  .modal-backdrop,
  .overlay,
  .popup,
  .cookie,
  .consent,
  .cookie-banner,
  .consent-modal,
  [class*="modal-overlay"],
  [class*="popup-overlay"],
  [class*="Backdrop"] {
    display: none !important;
    visibility: hidden !important;
  }
  body {
    overflow: auto !important;
  }
`;

/**
 * Common selectors for modal dismiss buttons.
 * Expanded based on ChatGPT/Perplexity recommendations.
 */
const DISMISS_SELECTORS = [
  // Explicit close/dismiss buttons
  'button:has-text("Close")',
  'button:has-text("Dismiss")',
  'button:has-text("Got it")',
  'button:has-text("OK")',
  'button:has-text("Accept")',
  'button:has-text("Accept All")',
  'button:has-text("Agree")',
  'button:has-text("Continue")',
  'button:has-text("No Thanks")',
  "button:has-text(\"Don't Show Again\")",
  'a:has-text("Close")',
  'a:has-text("Dismiss")',
  // Aria-label patterns (case-insensitive matching)
  '[aria-label="Close"]',
  '[aria-label="close"]',
  '[aria-label="Dismiss"]',
  '[aria-label="Close dialog"]',
  '[aria-label="Close modal"]',
  '[aria-label="accept cookies"]',
  'button[aria-label*="close" i]',
  'button[aria-label*="dismiss" i]',
  // Known consent framework buttons
  '#onetrust-accept-btn-handler',
  'button#acceptCookie',
  'button[aria-label="dismiss cookie message"]',
  '.cookie-banner button:first-of-type',
  // Common class patterns
  '.close-button',
  '.modal-close',
  '.popup-close',
  '.dialog-close',
  '.btn-close',
  // X button patterns (more specific to avoid false positives)
  'button.close',
  '.modal button:has-text("×")',
  '.popup button:has-text("×")',
];

/**
 * Setup page for modal handling.
 * Call this once when creating a new page to handle JS dialogs.
 */
function setupPageDialogHandler(page: Page): void {
  // Handle native JS dialogs (alert, confirm, prompt)
  page.on('dialog', async (dialog) => {
    logger.debug(`Dismissing JS dialog: ${dialog.type()} - ${dialog.message()}`);
    await dialog.dismiss().catch(() => {});
  });
}

/**
 * Dismiss modal overlays before PDF capture.
 *
 * Strategy hierarchy (most robust to most brittle):
 * 1. CSS injection to hide overlays globally (high leverage)
 * 2. Click dismiss buttons if needed (necessary evil)
 * 3. DOM removal as last resort (nuclear option)
 */
async function dismissModals(page: Page): Promise<boolean> {
  let dismissed = false;

  // Phase 1: Inject CSS to hide modals globally (high leverage)
  try {
    await page.addStyleTag({ content: MODAL_HIDING_CSS });
    logger.debug('Injected modal-hiding CSS');
    dismissed = true;
  } catch (error) {
    logger.debug(`CSS injection failed: ${(error as Error).message}`);
  }

  // Phase 2: Try clicking dismiss buttons (necessary evil)
  for (const selector of DISMISS_SELECTORS) {
    try {
      const element = page.locator(selector).first();
      if (await element.isVisible({ timeout: 500 })) {
        await element.click({ timeout: 1000 });
        logger.debug(`Dismissed modal with selector: ${selector}`);
        dismissed = true;
        // Wait briefly for animation
        await page.waitForTimeout(300);
        break;
      }
    } catch {
      // Element not found or not clickable, continue to next selector
    }
  }

  // Phase 3: Remove remaining overlay elements from DOM (last resort)
  try {
    const removedCount = await page.evaluate(() => {
      let removed = 0;
      // Target common overlay patterns
      const overlaySelectors = [
        'div[class*="modal"][style*="position"]',
        'div[class*="popup"][style*="position"]',
        'div[class*="overlay"][style*="position"]',
        'div[role="dialog"]',
        'div[aria-modal="true"]',
      ];

      for (const selector of overlaySelectors) {
        const elements = document.querySelectorAll(selector);
        elements.forEach((el) => {
          const style = window.getComputedStyle(el);
          // Only remove if it's positioned fixed/absolute and covers significant area
          if (
            (style.position === 'fixed' || style.position === 'absolute') &&
            parseInt(style.zIndex || '0') > 100
          ) {
            el.remove();
            removed++;
          }
        });
      }

      // Also check for backdrop/overlay elements
      const backdropSelectors = [
        '.modal-backdrop',
        '.overlay-backdrop',
        '[class*="backdrop"]',
        '[class*="Backdrop"]',
        '#cookieModal',
        '.cookie-modal',
        '.cookie-banner',
        '.consent-modal',
      ];

      for (const selector of backdropSelectors) {
        const elements = document.querySelectorAll(selector);
        elements.forEach((el) => {
          el.remove();
          removed++;
        });
      }

      return removed;
    });

    if (removedCount > 0) {
      logger.debug(`Removed ${removedCount} overlay elements from DOM`);
      dismissed = true;
    }
  } catch (error) {
    logger.debug(`DOM overlay removal failed: ${(error as Error).message}`);
  }

  return dismissed;
}

/**
 * Generate a safe filename from URL
 */
function urlToFilename(url: string, index: number): string {
  try {
    const urlObj = new URL(url);
    // Take the path, replace slashes and special chars
    let name = urlObj.pathname
      .replace(/^\//, '')
      .replace(/\//g, '_')
      .replace(/[^a-zA-Z0-9_-]/g, '')
      .substring(0, 50);

    if (!name || name === '') {
      name = 'index';
    }

    return `page_${String(index).padStart(3, '0')}_${name}.pdf`;
  } catch {
    return `page_${String(index).padStart(3, '0')}.pdf`;
  }
}

/**
 * Capture a single page as PDF
 */
async function capturePage(
  page: Page,
  url: string,
  outputPath: string,
  timeout: number,
  pdfOptions: CaptureRequest['pdfOptions']
): Promise<CaptureResult> {
  try {
    // Navigate to page
    await page.goto(url, {
      waitUntil: 'networkidle',
      timeout,
    });

    // Dismiss any modal overlays before capture
    const modalsDismissed = await dismissModals(page);
    if (modalsDismissed) {
      logger.info(`Dismissed modal overlays on ${url}`);
      // Wait for any animations to complete
      await page.waitForTimeout(500);
    }

    // Get page title
    const title = await page.title();

    // Default PDF options
    const options = {
      path: outputPath,
      format: pdfOptions?.format || 'Letter',
      scale: pdfOptions?.scale || 0.9,
      margin: pdfOptions?.margin || {
        top: '0.5in',
        bottom: '0.5in',
        left: '0.5in',
        right: '0.5in',
      },
      printBackground: true,
    } as const;

    // Capture PDF
    await page.pdf(options);

    // Get file size
    const stats = await fs.stat(outputPath);

    logger.info(`Captured PDF: ${url} -> ${outputPath} (${stats.size} bytes)`);

    return {
      url,
      success: true,
      filename: path.basename(outputPath),
      filepath: outputPath,
      sizeBytes: stats.size,
      title,
      modalsDismissed,
    };
  } catch (error) {
    logger.error(`Failed to capture ${url}: ${(error as Error).message}`);
    return {
      url,
      success: false,
      error: (error as Error).message,
    };
  }
}

/**
 * Capture multiple URLs as PDFs
 */
export async function capturePages(request: CaptureRequest): Promise<CaptureResponse> {
  const startTime = Date.now();
  const results: CaptureResult[] = [];
  const timeout = request.timeout || 30000;

  logger.info(`Starting PDF capture: ${request.urls.length} URLs`, {
    outputDir: request.outputDir,
    timeout,
  });

  // Ensure output directory exists
  try {
    await fs.mkdir(request.outputDir, { recursive: true });
  } catch (error) {
    return {
      success: false,
      results: [],
      stats: {
        total: request.urls.length,
        successful: 0,
        failed: request.urls.length,
        durationMs: Date.now() - startTime,
      },
      error: `Failed to create output directory: ${(error as Error).message}`,
    };
  }

  let browser: Browser | null = null;

  try {
    // Launch browser
    browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const context = await browser.newContext({
      userAgent:
        'LCT-BellScheduleScraper/1.0 (Educational Research; https://github.com/ianmmc/learning-connection-time)',
      viewport: { width: 1280, height: 1024 },
    });

    // Process URLs sequentially to avoid overwhelming servers
    for (let i = 0; i < request.urls.length; i++) {
      const url = request.urls[i];
      const filename = urlToFilename(url, i + 1);
      const outputPath = path.join(request.outputDir, filename);

      const page = await context.newPage();
      // Setup dialog handler to auto-dismiss JS alerts/confirms/prompts
      setupPageDialogHandler(page);
      try {
        const result = await capturePage(page, url, outputPath, timeout, request.pdfOptions);
        results.push(result);
      } finally {
        await page.close();
      }

      // Small delay between captures to be respectful
      if (i < request.urls.length - 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }

    const successful = results.filter((r) => r.success).length;
    const failed = results.filter((r) => !r.success).length;
    const durationMs = Date.now() - startTime;

    logger.info(`PDF capture complete`, {
      total: request.urls.length,
      successful,
      failed,
      durationMs,
    });

    return {
      success: failed === 0,
      results,
      stats: {
        total: request.urls.length,
        successful,
        failed,
        durationMs,
      },
    };
  } catch (error) {
    logger.error(`PDF capture failed: ${(error as Error).message}`);
    return {
      success: false,
      results,
      stats: {
        total: request.urls.length,
        successful: results.filter((r) => r.success).length,
        failed: request.urls.length - results.filter((r) => r.success).length,
        durationMs: Date.now() - startTime,
      },
      error: (error as Error).message,
    };
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}
