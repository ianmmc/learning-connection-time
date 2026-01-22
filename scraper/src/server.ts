/**
 * Express HTTP Server for Bell Schedule Scraper
 *
 * Provides REST API for scraping with:
 * - POST /scrape - scrape a URL
 * - GET /health - health check
 * - GET /status - detailed status
 */

import express, { Request, Response, NextFunction } from 'express';
import { Scraper } from './scraper.js';
import { getRequestQueue } from './queue.js';
import { ScrapeRequest, ServiceStatus, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';

const app = express();
app.use(express.json());

// Initialize scraper and queue
const scraper = new Scraper();
const queue = getRequestQueue();
const startTime = Date.now();

// Request logging middleware
app.use((req: Request, _res: Response, next: NextFunction) => {
  logger.debug(`${req.method} ${req.path}`, {
    body: req.method === 'POST' ? req.body : undefined,
  });
  next();
});

/**
 * POST /scrape
 * Scrape a URL and return the content
 */
app.post('/scrape', async (req: Request, res: Response) => {
  const { url, timeout, waitFor } = req.body as ScrapeRequest & { waitFor?: number };

  // Validate request
  if (!url || typeof url !== 'string') {
    res.status(400).json({
      success: false,
      error: 'Missing or invalid "url" parameter',
    });
    return;
  }

  try {
    new URL(url); // Validate URL format
  } catch {
    res.status(400).json({
      success: false,
      error: 'Invalid URL format',
    });
    return;
  }

  // Add to queue
  const response = await queue.add({ url, timeout, waitFor }, async (request) => {
    return scraper.scrape(request);
  });

  // Set appropriate status code
  if (!response.success) {
    if (response.errorCode === 'QUEUE_FULL') {
      res.status(503);
    } else if (response.errorCode === 'BLOCKED') {
      res.status(403);
    } else if (response.errorCode === 'NOT_FOUND') {
      res.status(404);
    } else {
      res.status(500);
    }
  }

  res.json(response);
});

/**
 * GET /health
 * Simple health check
 */
app.get('/health', (_req: Request, res: Response) => {
  const poolStats = scraper.getPoolStats();
  const queueStats = queue.getStats();

  const healthy = poolStats.total > 0 && queueStats.queueSize < DEFAULT_CONFIG.queue.maxQueueSize;

  res.status(healthy ? 200 : 503).json({
    status: healthy ? 'healthy' : 'unhealthy',
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /status
 * Detailed service status
 */
app.get('/status', (_req: Request, res: Response) => {
  const poolStats = scraper.getPoolStats();
  const queueStats = queue.getStats();

  const status: ServiceStatus = {
    status: poolStats.total > 0 ? 'healthy' : 'unhealthy',
    queueDepth: queueStats.queueSize,
    activeBrowsers: poolStats.inUse,
    maxBrowsers: poolStats.total,
    processed: queueStats.processed,
    failed: queueStats.failed,
    blocked: queueStats.blocked,
    uptime: Math.floor((Date.now() - startTime) / 1000),
  };

  res.json(status);
});

/**
 * GET /
 * Root endpoint with API documentation
 */
app.get('/', (_req: Request, res: Response) => {
  res.json({
    name: 'LCT Bell Schedule Scraper',
    version: '1.0.0',
    endpoints: {
      'POST /scrape': 'Scrape a URL (body: { url: string, timeout?: number, waitFor?: number })',
      'GET /health': 'Health check',
      'GET /status': 'Detailed service status',
    },
    documentation: 'https://github.com/ianmmc/learning-connection-time',
  });
});

// Error handling middleware
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  logger.error('Unhandled error:', err);
  res.status(500).json({
    success: false,
    error: 'Internal server error',
  });
});

// Graceful shutdown
async function shutdown(signal: string) {
  logger.info(`Received ${signal}, shutting down gracefully...`);

  // Stop accepting new requests
  server.close(() => {
    logger.info('HTTP server closed');
  });

  // Drain queue
  await queue.drain();

  // Shutdown scraper (closes browsers)
  await scraper.shutdown();

  logger.info('Shutdown complete');
  process.exit(0);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// Start server
const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : DEFAULT_CONFIG.port;

async function main() {
  logger.info('Initializing scraper...');
  await scraper.initialize();
  logger.info('Scraper initialized');
}

const server = app.listen(PORT, () => {
  logger.info(`Bell Schedule Scraper listening on port ${PORT}`);
  main().catch((error) => {
    logger.error('Failed to initialize scraper:', error);
    process.exit(1);
  });
});

export { app };
