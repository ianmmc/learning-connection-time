/**
 * Browser Pool Management
 *
 * Manages a pool of Playwright browser instances for efficient resource usage.
 * Instead of spawning a new browser per request, browsers are reused.
 */

import { chromium, Browser, BrowserContext } from 'playwright';
import { BrowserPoolConfig, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';

interface PooledBrowserInstance {
  browser: Browser;
  id: string;
  inUse: boolean;
  createdAt: Date;
  lastUsed: Date;
  requestCount: number;
}

export class BrowserPool {
  private pool: PooledBrowserInstance[] = [];
  private config: BrowserPoolConfig;
  private isShuttingDown = false;
  private waitQueue: Array<{
    resolve: (browser: Browser) => void;
    reject: (error: Error) => void;
  }> = [];

  constructor(config: BrowserPoolConfig = DEFAULT_CONFIG.pool) {
    this.config = config;
  }

  /**
   * Initialize the pool with browsers
   */
  async initialize(count?: number): Promise<void> {
    const browserCount = count ?? this.config.maxBrowsers;
    logger.info(`Initializing browser pool with ${browserCount} browsers`);

    const launchPromises = [];
    for (let i = 0; i < browserCount; i++) {
      launchPromises.push(this.createBrowser());
    }

    await Promise.all(launchPromises);
    logger.info(`Browser pool initialized: ${this.pool.length} browsers ready`);
  }

  /**
   * Create a new browser instance and add to pool
   */
  private async createBrowser(): Promise<PooledBrowserInstance> {
    const browser = await chromium.launch({
      headless: this.config.browserOptions.headless,
      args: this.config.browserOptions.args,
    });

    const instance: PooledBrowserInstance = {
      browser,
      id: `browser-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      inUse: false,
      createdAt: new Date(),
      lastUsed: new Date(),
      requestCount: 0,
    };

    this.pool.push(instance);
    logger.debug(`Created browser ${instance.id}`);
    return instance;
  }

  /**
   * Acquire a browser from the pool
   */
  async acquire(): Promise<Browser> {
    if (this.isShuttingDown) {
      throw new Error('Pool is shutting down');
    }

    // Try to find an available browser
    const available = this.pool.find(b => !b.inUse);

    if (available) {
      available.inUse = true;
      available.lastUsed = new Date();
      available.requestCount++;
      logger.debug(`Acquired browser ${available.id} (request #${available.requestCount})`);
      return available.browser;
    }

    // If pool isn't at max capacity, create a new browser
    if (this.pool.length < this.config.maxBrowsers) {
      const instance = await this.createBrowser();
      instance.inUse = true;
      instance.requestCount++;
      logger.debug(`Created and acquired new browser ${instance.id}`);
      return instance.browser;
    }

    // Wait for a browser to become available
    logger.debug('All browsers in use, waiting for availability...');
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        const idx = this.waitQueue.findIndex(w => w.resolve === resolve);
        if (idx !== -1) {
          this.waitQueue.splice(idx, 1);
        }
        reject(new Error('Timeout waiting for browser'));
      }, this.config.launchTimeout);

      this.waitQueue.push({
        resolve: (browser: Browser) => {
          clearTimeout(timeout);
          resolve(browser);
        },
        reject: (error: Error) => {
          clearTimeout(timeout);
          reject(error);
        },
      });
    });
  }

  /**
   * Release a browser back to the pool
   */
  release(browser: Browser): void {
    const instance = this.pool.find(b => b.browser === browser);

    if (!instance) {
      logger.warn('Attempted to release unknown browser');
      return;
    }

    instance.inUse = false;
    instance.lastUsed = new Date();
    logger.debug(`Released browser ${instance.id}`);

    // If someone is waiting, give them this browser
    if (this.waitQueue.length > 0) {
      const waiter = this.waitQueue.shift()!;
      instance.inUse = true;
      instance.requestCount++;
      logger.debug(`Immediately reassigned browser ${instance.id} to waiting request`);
      waiter.resolve(instance.browser);
    }
  }

  /**
   * Create a new context for a browser (for isolation)
   */
  async createContext(browser: Browser, userAgent: string): Promise<BrowserContext> {
    return browser.newContext({
      userAgent,
      viewport: { width: 1280, height: 720 },
      ignoreHTTPSErrors: true,
    });
  }

  /**
   * Get pool statistics
   */
  getStats(): {
    total: number;
    inUse: number;
    available: number;
    waiting: number;
    totalRequests: number;
  } {
    const inUse = this.pool.filter(b => b.inUse).length;
    const totalRequests = this.pool.reduce((sum, b) => sum + b.requestCount, 0);

    return {
      total: this.pool.length,
      inUse,
      available: this.pool.length - inUse,
      waiting: this.waitQueue.length,
      totalRequests,
    };
  }

  /**
   * Shutdown the pool and close all browsers
   */
  async shutdown(): Promise<void> {
    logger.info('Shutting down browser pool...');
    this.isShuttingDown = true;

    // Reject all waiting requests
    for (const waiter of this.waitQueue) {
      waiter.reject(new Error('Pool is shutting down'));
    }
    this.waitQueue = [];

    // Close all browsers
    const closePromises = this.pool.map(async (instance) => {
      try {
        await instance.browser.close();
        logger.debug(`Closed browser ${instance.id}`);
      } catch (error) {
        logger.warn(`Error closing browser ${instance.id}:`, error);
      }
    });

    await Promise.all(closePromises);
    this.pool = [];
    logger.info('Browser pool shutdown complete');
  }
}

// Singleton instance
let poolInstance: BrowserPool | null = null;

export function getBrowserPool(config?: BrowserPoolConfig): BrowserPool {
  if (!poolInstance) {
    poolInstance = new BrowserPool(config);
  }
  return poolInstance;
}

export async function shutdownPool(): Promise<void> {
  if (poolInstance) {
    await poolInstance.shutdown();
    poolInstance = null;
  }
}
