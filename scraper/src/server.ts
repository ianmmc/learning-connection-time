/**
 * Express HTTP Server for Bell Schedule Scraper
 *
 * Provides REST API for scraping with:
 * - POST /scrape - scrape a URL
 * - GET /health - health check
 * - GET /status - detailed status
 */

import express, { Request, Response, NextFunction } from 'express';
import { randomUUID } from 'crypto';
import { Scraper } from './scraper.js';
import { getRequestQueue } from './queue.js';
import { ScrapeRequest, ServiceStatus, DEFAULT_CONFIG } from './types.js';
import { logger } from './logger.js';
import { discoverSchoolSites, getRepresentativeSample } from './discovery.js';

const app = express();
app.use(express.json());

// Initialize scraper and queue
const scraper = new Scraper();
const queue = getRequestQueue();
const startTime = Date.now();

// API Key from environment variable (REQ-028)
const API_KEY = process.env.SCRAPER_API_KEY;

// Extend Request type to include requestId (REQ-031)
declare global {
  namespace Express {
    interface Request {
      requestId?: string;
    }
  }
}

// Request ID middleware - add UUID to every request (REQ-031)
app.use((req: Request, res: Response, next: NextFunction) => {
  req.requestId = randomUUID();
  res.setHeader('X-Request-ID', req.requestId);
  next();
});

// Request logging middleware - includes requestId for correlation
app.use((req: Request, _res: Response, next: NextFunction) => {
  logger.debug(`${req.method} ${req.path}`, {
    requestId: req.requestId,
    body: req.method === 'POST' ? req.body : undefined,
  });
  next();
});

/**
 * API Key authentication middleware (REQ-028)
 * Protects /scrape and /discover endpoints
 * Allows /health, /status, and / to remain public
 */
const requireApiKey = (req: Request, res: Response, next: NextFunction) => {
  // Skip auth if no API key is configured (development mode)
  if (!API_KEY) {
    logger.warn('SCRAPER_API_KEY not set - running without authentication', { requestId: req.requestId });
    return next();
  }

  const providedKey = req.headers['x-api-key'];

  if (!providedKey) {
    logger.warn('Unauthorized request - missing API key', { requestId: req.requestId, path: req.path });
    res.status(401).json({
      success: false,
      error: 'Missing X-API-Key header',
      requestId: req.requestId,
    });
    return;
  }

  if (providedKey !== API_KEY) {
    logger.warn('Unauthorized request - invalid API key', { requestId: req.requestId, path: req.path });
    res.status(401).json({
      success: false,
      error: 'Invalid API key',
      requestId: req.requestId,
    });
    return;
  }

  next();
};

/**
 * POST /scrape
 * Scrape a URL and return the content
 * Protected by API key authentication (REQ-028)
 */
app.post('/scrape', requireApiKey, async (req: Request, res: Response) => {
  const { url, timeout, waitFor } = req.body as ScrapeRequest & { waitFor?: number };

  logger.info('Scrape request received', { requestId: req.requestId, url });

  // Validate request
  if (!url || typeof url !== 'string') {
    res.status(400).json({
      success: false,
      error: 'Missing or invalid "url" parameter',
      requestId: req.requestId,
    });
    return;
  }

  try {
    new URL(url); // Validate URL format
  } catch {
    res.status(400).json({
      success: false,
      error: 'Invalid URL format',
      requestId: req.requestId,
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

  // Include requestId in response (REQ-031)
  res.json({ ...response, requestId: req.requestId });
});

/**
 * POST /discover
 * Discover individual school sites within a district
 * Protected by API key authentication (REQ-028)
 */
app.post('/discover', requireApiKey, async (req: Request, res: Response) => {
  const { districtUrl, state, representativeOnly } = req.body as {
    districtUrl: string;
    state?: string;
    representativeOnly?: boolean;
  };

  logger.info('Discover request received', { requestId: req.requestId, districtUrl });

  // Validate request
  if (!districtUrl || typeof districtUrl !== 'string') {
    res.status(400).json({
      success: false,
      error: 'Missing or invalid "districtUrl" parameter',
      requestId: req.requestId,
    });
    return;
  }

  try {
    new URL(districtUrl); // Validate URL format
  } catch {
    res.status(400).json({
      success: false,
      error: 'Invalid URL format',
      requestId: req.requestId,
    });
    return;
  }

  try {
    logger.info(`Discovering school sites for: ${districtUrl}`, { requestId: req.requestId });

    // Get a browser from the pool
    const browser = await scraper.pool.acquire();

    try {
      // Discover schools
      const result = await discoverSchoolSites(browser, districtUrl, state, 30000);

      if (!result.success) {
        res.status(404).json({
          success: false,
          error: result.error || 'No school sites found',
          schools: [],
          requestId: req.requestId,
        });
        return;
      }

      // Optionally filter to representative sample
      const schools = representativeOnly
        ? getRepresentativeSample(result.schools)
        : result.schools;

      logger.info(`Discovered ${schools.length} school sites for ${districtUrl}`, { requestId: req.requestId });

      res.json({
        success: true,
        districtUrl,
        schools,
        method: result.method,
        totalFound: result.schools.length,
        returned: schools.length,
        requestId: req.requestId,
      });
    } finally {
      await scraper.pool.release(browser);
    }
  } catch (error) {
    logger.error(`School discovery failed: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'School discovery failed',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
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
    version: '1.1.0',
    endpoints: {
      'POST /scrape': 'Scrape a URL (body: { url: string, timeout?: number, waitFor?: number })',
      'POST /discover': 'Discover school sites (body: { districtUrl: string, state?: string, representativeOnly?: boolean })',
      'GET /health': 'Health check',
      'GET /status': 'Detailed service status',
    },
    documentation: 'https://github.com/ianmmc/learning-connection-time',
  });
});

// Error handling middleware - includes requestId for correlation (REQ-031)
app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  logger.error('Unhandled error:', { error: err.message, stack: err.stack, requestId: req.requestId });
  res.status(500).json({
    success: false,
    error: 'Internal server error',
    requestId: req.requestId,
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
