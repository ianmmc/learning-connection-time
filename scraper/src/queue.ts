/**
 * Request Queue with Rate Limiting
 *
 * Manages concurrent scraping requests with:
 * - Bounded concurrency (max simultaneous requests)
 * - Per-domain rate limiting (respect district servers)
 * - Queue depth limits (backpressure when overwhelmed)
 */

import PQueue from 'p-queue';
import { QueueConfig, ScrapeRequest, ScrapeResponse, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';

interface QueueStats {
  pending: number;
  processed: number;
  failed: number;
  blocked: number;
}

export class RequestQueue {
  private queue: PQueue;
  private config: QueueConfig;
  private domainLastAccess: Map<string, number> = new Map();
  private stats: QueueStats = {
    pending: 0,
    processed: 0,
    failed: 0,
    blocked: 0,
  };

  constructor(config: QueueConfig = DEFAULT_CONFIG.queue) {
    this.config = config;
    this.queue = new PQueue({
      concurrency: config.maxConcurrency,
      timeout: config.timeout,
      throwOnTimeout: true,
    });

    logger.info(`Request queue initialized: concurrency=${config.maxConcurrency}, maxSize=${config.maxQueueSize}`);
  }

  /**
   * Extract domain from URL for rate limiting
   */
  private extractDomain(url: string): string {
    try {
      const parsed = new URL(url);
      return parsed.hostname;
    } catch {
      return 'unknown';
    }
  }

  /**
   * Wait for rate limit if needed for a domain
   */
  private async waitForRateLimit(domain: string): Promise<void> {
    const lastAccess = this.domainLastAccess.get(domain);
    if (lastAccess) {
      const elapsed = Date.now() - lastAccess;
      const waitTime = this.config.requestDelayMs - elapsed;
      if (waitTime > 0) {
        logger.debug(`Rate limiting: waiting ${waitTime}ms for domain ${domain}`);
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
    }
    this.domainLastAccess.set(domain, Date.now());
  }

  /**
   * Add a scrape request to the queue
   */
  async add(
    request: ScrapeRequest,
    handler: (req: ScrapeRequest) => Promise<ScrapeResponse>
  ): Promise<ScrapeResponse> {
    // Check queue depth limit
    if (this.queue.size >= this.config.maxQueueSize) {
      logger.warn(`Queue full (${this.queue.size}/${this.config.maxQueueSize}), rejecting request`);
      return {
        success: false,
        url: request.url,
        error: 'Queue full - try again later',
        errorCode: 'QUEUE_FULL',
        timing: 0,
      };
    }

    this.stats.pending++;
    const domain = this.extractDomain(request.url);
    const startTime = Date.now();

    try {
      const response = await this.queue.add(async () => {
        // Rate limit per domain
        await this.waitForRateLimit(domain);

        logger.debug(`Processing request for ${request.url}`);
        return handler(request);
      });

      if (!response) {
        throw new Error('Handler returned undefined');
      }

      this.stats.pending--;
      this.stats.processed++;

      if (response.blocked) {
        this.stats.blocked++;
      }
      if (!response.success) {
        this.stats.failed++;
      }

      return response;
    } catch (error) {
      this.stats.pending--;
      this.stats.failed++;

      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      const isTimeout = errorMessage.includes('timeout') || errorMessage.includes('Timeout');

      logger.error(`Request failed for ${request.url}: ${errorMessage}`);

      return {
        success: false,
        url: request.url,
        error: errorMessage,
        errorCode: isTimeout ? 'TIMEOUT' : 'NETWORK_ERROR',
        timing: Date.now() - startTime,
      };
    }
  }

  /**
   * Get queue statistics
   */
  getStats(): QueueStats & { queueSize: number; concurrency: number } {
    return {
      ...this.stats,
      queueSize: this.queue.size,
      concurrency: this.queue.concurrency,
    };
  }

  /**
   * Pause the queue
   */
  pause(): void {
    this.queue.pause();
    logger.info('Queue paused');
  }

  /**
   * Resume the queue
   */
  resume(): void {
    this.queue.start();
    logger.info('Queue resumed');
  }

  /**
   * Clear the queue (cancel pending requests)
   */
  clear(): void {
    this.queue.clear();
    this.stats.pending = 0;
    logger.info('Queue cleared');
  }

  /**
   * Wait for all pending requests to complete
   */
  async drain(): Promise<void> {
    logger.info('Draining queue...');
    await this.queue.onIdle();
    logger.info('Queue drained');
  }
}

// Singleton instance
let queueInstance: RequestQueue | null = null;

export function getRequestQueue(config?: QueueConfig): RequestQueue {
  if (!queueInstance) {
    queueInstance = new RequestQueue(config);
  }
  return queueInstance;
}

export function resetRequestQueue(): void {
  if (queueInstance) {
    queueInstance.clear();
  }
  queueInstance = null;
}
