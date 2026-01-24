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

// REQ-030: Retry configuration constants
const RETRY_CONFIG = {
  maxRetries: 3,           // Maximum number of retry attempts
  baseDelayMs: 1000,       // Base delay for exponential backoff (1 second)
  maxDelayMs: 8000,        // Maximum delay cap (8 seconds)
  jitterFactor: 0.2,       // Add up to 20% jitter to prevent thundering herd
};

// Error codes that should NOT be retried
const NON_RETRYABLE_ERRORS = new Set([
  'BLOCKED',      // Security blocks - retrying wastes resources and may get IP blacklisted
  'NOT_FOUND',    // 404 errors - page doesn't exist, retrying won't help
  'QUEUE_FULL',   // Queue at capacity - client should retry later
]);

/**
 * Calculate exponential backoff delay with jitter
 * @param attempt - Retry attempt number (1-based)
 * @returns Delay in milliseconds
 */
function calculateBackoffDelay(attempt: number): number {
  // Exponential backoff: base * 2^(attempt-1), capped at max
  const exponentialDelay = Math.min(
    RETRY_CONFIG.baseDelayMs * Math.pow(2, attempt - 1),
    RETRY_CONFIG.maxDelayMs
  );

  // Add jitter to prevent thundering herd
  const jitter = exponentialDelay * RETRY_CONFIG.jitterFactor * Math.random();

  return Math.floor(exponentialDelay + jitter);
}

/**
 * Check if an error code should trigger a retry
 */
function isRetryableError(errorCode: string | undefined): boolean {
  if (!errorCode) return true; // Unknown errors are retryable by default
  return !NON_RETRYABLE_ERRORS.has(errorCode);
}

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
   *
   * REQ-030: Implements retry logic with exponential backoff
   * - Retries transient failures (TIMEOUT, NETWORK_ERROR) up to 3 times
   * - Uses exponential backoff with jitter (base 1s, max 8s)
   * - Does NOT retry security blocks (BLOCKED) or 404s (NOT_FOUND)
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

    let lastError: Error | null = null;
    let lastResponse: ScrapeResponse | null = null;

    // REQ-030: Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.maxRetries + 1; attempt++) {
      try {
        const response = await this.queue.add(async () => {
          // Rate limit per domain
          await this.waitForRateLimit(domain);

          logger.debug(`Processing request for ${request.url} (attempt ${attempt})`);
          return handler(request);
        });

        if (!response) {
          throw new Error('Handler returned undefined');
        }

        // Check if response indicates a retryable failure
        if (!response.success && response.errorCode) {
          if (!isRetryableError(response.errorCode)) {
            // Non-retryable error - return immediately
            logger.debug(
              `Non-retryable error ${response.errorCode} for ${request.url}, not retrying`
            );
            this.stats.pending--;
            this.stats.processed++;
            if (response.blocked) this.stats.blocked++;
            this.stats.failed++;
            return response;
          }

          // Retryable error - check if we should retry
          lastResponse = response;
          if (attempt <= RETRY_CONFIG.maxRetries) {
            const delay = calculateBackoffDelay(attempt);
            logger.info(
              `Retryable error ${response.errorCode} for ${request.url}, ` +
              `retry ${attempt}/${RETRY_CONFIG.maxRetries} after ${delay}ms`
            );
            await new Promise(resolve => setTimeout(resolve, delay));
            continue; // Retry
          }
        }

        // Success or final attempt
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
        lastError = error instanceof Error ? error : new Error('Unknown error');
        const errorMessage = lastError.message;
        const isTimeout = errorMessage.includes('timeout') || errorMessage.includes('Timeout');
        const errorCode = isTimeout ? 'TIMEOUT' : 'NETWORK_ERROR';

        // Check if we should retry this exception
        if (isRetryableError(errorCode) && attempt <= RETRY_CONFIG.maxRetries) {
          const delay = calculateBackoffDelay(attempt);
          logger.info(
            `Exception (${errorCode}) for ${request.url}: ${errorMessage}, ` +
            `retry ${attempt}/${RETRY_CONFIG.maxRetries} after ${delay}ms`
          );
          await new Promise(resolve => setTimeout(resolve, delay));
          continue; // Retry
        }

        // Final attempt failed or non-retryable
        logger.error(
          `Request failed for ${request.url} after ${attempt} attempt(s): ${errorMessage}`
        );
      }
    }

    // All retries exhausted
    this.stats.pending--;
    this.stats.failed++;

    // Return the last response if we have one, otherwise construct error response
    if (lastResponse) {
      logger.error(
        `All ${RETRY_CONFIG.maxRetries} retries exhausted for ${request.url}, ` +
        `last error: ${lastResponse.errorCode}`
      );
      return lastResponse;
    }

    const errorMessage = lastError?.message || 'Unknown error';
    const isTimeout = errorMessage.includes('timeout') || errorMessage.includes('Timeout');

    return {
      success: false,
      url: request.url,
      error: `Failed after ${RETRY_CONFIG.maxRetries + 1} attempts: ${errorMessage}`,
      errorCode: isTimeout ? 'TIMEOUT' : 'NETWORK_ERROR',
      timing: Date.now() - startTime,
    };
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
