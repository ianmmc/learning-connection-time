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
import { ScrapeRequest, ServiceStatus, DEFAULT_CONFIG, PdfCaptureOptions } from './types.js';
import { logger } from './logger.js';
import { discoverSchoolSites, getRepresentativeSample, discoverSchoolsWithSampling } from './discovery.js';
import { mapWebsite, mapWebsiteAsync, MapRequest } from './mapper.js';
import * as jobManager from './jobManager.js';
import { capturePages, CaptureRequest } from './capturer.js';

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
 *
 * Body parameters:
 *   url: string (required) - URL to scrape
 *   timeout?: number - Navigation timeout in ms (default: 30000)
 *   waitFor?: number - Additional wait after networkidle in ms
 *   capturePdf?: boolean - Capture page as PDF (default: false)
 *   pdfOptions?: PdfCaptureOptions - PDF capture settings
 */
app.post('/scrape', requireApiKey, async (req: Request, res: Response) => {
  const { url, timeout, waitFor, capturePdf, pdfOptions } = req.body as ScrapeRequest & {
    waitFor?: number;
    capturePdf?: boolean;
    pdfOptions?: PdfCaptureOptions;
  };

  logger.info('Scrape request received', {
    requestId: req.requestId,
    url,
    capturePdf: capturePdf ?? false,
  });

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

  // Add to queue with PDF options
  const response = await queue.add(
    { url, timeout, waitFor, capturePdf, pdfOptions },
    async (request) => {
      return scraper.scrape(request);
    }
  );

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
 * POST /discover/sample
 * Enhanced school discovery with grade band sampling (3-4 per band)
 * Protected by API key authentication
 *
 * Body parameters:
 *   districtUrl: string (required) - District homepage URL
 *   state?: string - State code for pattern matching
 *   perBand?: number - Schools per grade band (default: 4)
 */
app.post('/discover/sample', requireApiKey, async (req: Request, res: Response) => {
  const { districtUrl, state, perBand } = req.body as {
    districtUrl: string;
    state?: string;
    perBand?: number;
  };

  logger.info('Enhanced discover request received', { requestId: req.requestId, districtUrl, perBand });

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
    new URL(districtUrl);
  } catch {
    res.status(400).json({
      success: false,
      error: 'Invalid URL format',
      requestId: req.requestId,
    });
    return;
  }

  try {
    logger.info(`Discovering schools with sampling for: ${districtUrl}`, { requestId: req.requestId });

    // Get a browser from the pool
    const browser = await scraper.pool.acquire();

    try {
      const result = await discoverSchoolsWithSampling(browser, districtUrl, state, {
        perBand: perBand || 4,
        timeout: 30000,
      });

      if (!result.success) {
        res.status(404).json({
          success: false,
          error: result.error || 'No school sites found',
          allSchools: [],
          sample: [],
          requestId: req.requestId,
        });
        return;
      }

      // Summary stats
      const levelCounts = {
        elementary: result.schools.filter(s => s.level === 'elementary').length,
        middle: result.schools.filter(s => s.level === 'middle').length,
        high: result.schools.filter(s => s.level === 'high').length,
        unknown: result.schools.filter(s => !s.level).length,
      };

      logger.info(`Enhanced discovery found ${result.schools.length} schools, sampled ${result.sample.length}`, {
        requestId: req.requestId,
      });

      res.json({
        success: true,
        districtUrl,
        allSchools: result.schools,
        sample: result.sample,
        method: result.method,
        stats: {
          totalFound: result.schools.length,
          sampleSize: result.sample.length,
          byLevel: levelCounts,
        },
        requestId: req.requestId,
      });
    } finally {
      await scraper.pool.release(browser);
    }
  } catch (error) {
    logger.error(`Enhanced school discovery failed: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'Enhanced school discovery failed',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
});

/**
 * POST /map
 * Map a district website using Crawlee to collect rich page metadata
 * Protected by API key authentication
 *
 * Body parameters:
 *   url: string (required) - District website URL to map
 *   maxRequests?: number - Maximum pages to crawl (default: 100)
 *   maxDepth?: number - Maximum crawl depth (default: 4)
 *   patterns?: { includeGlobs?: string[], excludeGlobs?: string[] }
 */
app.post('/map', requireApiKey, async (req: Request, res: Response) => {
  const { url, maxRequests, maxDepth, patterns } = req.body as MapRequest;

  logger.info('Map request received', {
    requestId: req.requestId,
    url,
    maxRequests,
    maxDepth,
  });

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

  try {
    const result = await mapWebsite({ url, maxRequests, maxDepth, patterns });
    res.json({ ...result, requestId: req.requestId });
  } catch (error) {
    logger.error(`Map request failed: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'Website mapping failed',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
});

/**
 * POST /map/start
 * Start an async mapping job - returns immediately with job ID
 * Protected by API key authentication
 *
 * Body parameters:
 *   url: string (required) - Website URL to map
 *   maxRequests?: number - Maximum pages to crawl (default: 100)
 *   maxDepth?: number - Maximum crawl depth (default: 4)
 *   patterns?: { includeGlobs?: string[], excludeGlobs?: string[] }
 */
app.post('/map/start', requireApiKey, async (req: Request, res: Response) => {
  const { url, maxRequests, maxDepth, patterns } = req.body as MapRequest;

  logger.info('Async map request received', {
    requestId: req.requestId,
    url,
    maxRequests,
    maxDepth,
  });

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
    new URL(url);
  } catch {
    res.status(400).json({
      success: false,
      error: 'Invalid URL format',
      requestId: req.requestId,
    });
    return;
  }

  try {
    // Start async job - returns immediately
    const jobId = await mapWebsiteAsync({ url, maxRequests, maxDepth, patterns });

    logger.info(`Started async map job ${jobId} for ${url}`, { requestId: req.requestId });

    res.status(202).json({
      success: true,
      jobId,
      url,
      statusUrl: `/map/status/${jobId}`,
      message: 'Mapping job started. Poll status URL for progress.',
      requestId: req.requestId,
    });
  } catch (error) {
    logger.error(`Failed to start async map job: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'Failed to start mapping job',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
});

/**
 * GET /map/status/:jobId
 * Get status and results of an async mapping job
 *
 * Returns:
 *   - While running: { phase: 'crawling', pagesVisited, pagesQueued, ... }
 *   - When complete: { phase: 'completed', pages: [...], stats: {...} }
 *   - On failure: { phase: 'failed', error: '...' }
 */
app.get('/map/status/:jobId', requireApiKey, async (req: Request, res: Response) => {
  const jobId = req.params.jobId as string;

  logger.debug(`Status request for job ${jobId}`, { requestId: req.requestId });

  try {
    const result = await jobManager.getJobResult(jobId);

    if (!result) {
      res.status(404).json({
        success: false,
        error: 'Job not found',
        jobId,
        requestId: req.requestId,
      });
      return;
    }

    const { status, pages, isComplete } = result;

    // Return appropriate response based on job state
    if (status.phase === 'failed') {
      res.status(500).json({
        success: false,
        jobId,
        phase: status.phase,
        error: status.error,
        url: status.url,
        startedAt: status.startedAt,
        completedAt: status.completedAt,
        requestId: req.requestId,
      });
      return;
    }

    if (isComplete) {
      // Return full results
      res.json({
        success: true,
        jobId,
        phase: status.phase,
        url: status.url,
        pages,
        stats: {
          pagesVisited: status.pagesVisited,
          pagesWithTimePatterns: status.pagesWithTimePatterns,
          pagesWithBellKeywords: status.pagesWithBellKeywords,
          durationMs: status.completedAt
            ? new Date(status.completedAt).getTime() - new Date(status.startedAt).getTime()
            : undefined,
        },
        startedAt: status.startedAt,
        completedAt: status.completedAt,
        requestId: req.requestId,
      });
    } else {
      // Return progress update
      res.json({
        success: true,
        jobId,
        phase: status.phase,
        url: status.url,
        progress: {
          pagesVisited: status.pagesVisited,
          pagesQueued: status.pagesQueued,
          pagesWithTimePatterns: status.pagesWithTimePatterns,
          pagesWithBellKeywords: status.pagesWithBellKeywords,
        },
        startedAt: status.startedAt,
        updatedAt: status.updatedAt,
        requestId: req.requestId,
      });
    }
  } catch (error) {
    logger.error(`Failed to get job status: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'Failed to get job status',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
});

/**
 * GET /map/jobs
 * List all mapping jobs (for debugging/admin)
 */
app.get('/map/jobs', requireApiKey, async (req: Request, res: Response) => {
  try {
    const jobs = await jobManager.listJobs();
    res.json({
      success: true,
      jobs,
      count: jobs.length,
      requestId: req.requestId,
    });
  } catch (error) {
    logger.error(`Failed to list jobs: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'Failed to list jobs',
      details: (error as Error).message,
      requestId: req.requestId,
    });
  }
});

/**
 * POST /capture
 * Capture multiple URLs as PDFs
 * Protected by API key authentication
 *
 * Body parameters:
 *   urls: string[] (required) - URLs to capture as PDFs
 *   outputDir: string (required) - Directory to save PDFs
 *   timeout?: number - Navigation timeout in ms (default: 30000)
 *   pdfOptions?: { format?, scale?, margin? }
 */
app.post('/capture', requireApiKey, async (req: Request, res: Response) => {
  const { urls, outputDir, timeout, pdfOptions } = req.body as CaptureRequest;

  logger.info('Capture request received', {
    requestId: req.requestId,
    urlCount: urls?.length,
    outputDir,
  });

  // Validate request
  if (!urls || !Array.isArray(urls) || urls.length === 0) {
    res.status(400).json({
      success: false,
      error: 'Missing or invalid "urls" parameter (must be non-empty array)',
      requestId: req.requestId,
    });
    return;
  }

  if (!outputDir || typeof outputDir !== 'string') {
    res.status(400).json({
      success: false,
      error: 'Missing or invalid "outputDir" parameter',
      requestId: req.requestId,
    });
    return;
  }

  // Validate all URLs
  for (const url of urls) {
    try {
      new URL(url);
    } catch {
      res.status(400).json({
        success: false,
        error: `Invalid URL format: ${url}`,
        requestId: req.requestId,
      });
      return;
    }
  }

  try {
    const result = await capturePages({ urls, outputDir, timeout, pdfOptions });
    res.json({ ...result, requestId: req.requestId });
  } catch (error) {
    logger.error(`Capture request failed: ${(error as Error).message}`, { requestId: req.requestId });
    res.status(500).json({
      success: false,
      error: 'PDF capture failed',
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
    version: '2.2.0',
    endpoints: {
      'POST /scrape': 'Scrape a URL (body: { url, timeout?, waitFor?, capturePdf?, pdfOptions? })',
      'POST /discover': 'Discover school sites (body: { districtUrl, state?, representativeOnly? })',
      'POST /discover/sample': 'Enhanced discovery with grade band sampling (body: { districtUrl, state?, perBand? })',
      'POST /map': 'Map a district website synchronously (body: { url, maxRequests?, maxDepth?, patterns? })',
      'POST /map/start': 'Start async mapping job (body: { url, maxRequests?, maxDepth?, patterns? })',
      'GET /map/status/:jobId': 'Get async job status and results',
      'GET /map/jobs': 'List all mapping jobs',
      'POST /capture': 'Capture multiple URLs as PDFs (body: { urls, outputDir, timeout?, pdfOptions? })',
      'GET /health': 'Health check',
      'GET /status': 'Detailed service status',
    },
    asyncMapping: {
      description: 'For long-running crawls, use /map/start to get a job ID, then poll /map/status/:jobId',
      workflow: '1. POST /map/start → {jobId} | 2. GET /map/status/:jobId → progress or results',
    },
    mapEndpoint: {
      description: 'Crawls a district website and returns rich page metadata for URL ranking',
      returns: 'Array of pages with: url, title, h1, metaDescription, breadcrumb, timePatternCount, hasSchedulePdfLink, keywordMatchCount',
    },
    captureEndpoint: {
      description: 'Captures multiple URLs as PDFs to a specified directory',
      returns: 'Array of capture results with: url, success, filename, filepath, sizeBytes',
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
