/**
 * TypeScript types for LCT Bell Schedule Scraper
 */

// Request types
export interface ScrapeRequest {
  url: string;
  timeout?: number;  // milliseconds, default 30000
  waitFor?: number;  // additional wait after networkidle, milliseconds
}

export interface ScrapeResponse {
  success: boolean;
  url: string;
  html?: string;
  markdown?: string;
  title?: string;
  error?: string;
  errorCode?: string;  // 'TIMEOUT' | 'BLOCKED' | 'NOT_FOUND' | 'NETWORK_ERROR'
  timing: number;  // milliseconds
  blocked?: boolean;  // true if security block detected
}

// Status types
export interface ServiceStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  queueDepth: number;
  activeBrowsers: number;
  maxBrowsers: number;
  processed: number;
  failed: number;
  blocked: number;
  uptime: number;  // seconds
}

// Browser pool types
export interface BrowserPoolConfig {
  maxBrowsers: number;
  launchTimeout: number;
  browserOptions: {
    headless: boolean;
    args?: string[];
  };
}

export interface PooledBrowser {
  id: string;
  inUse: boolean;
  createdAt: Date;
  lastUsed: Date;
}

// Queue types
export interface QueueConfig {
  maxConcurrency: number;
  maxQueueSize: number;
  requestDelayMs: number;  // delay between requests to same domain
  timeout: number;
}

export interface QueuedRequest {
  id: string;
  request: ScrapeRequest;
  addedAt: Date;
  resolve: (response: ScrapeResponse) => void;
  reject: (error: Error) => void;
}

// Security detection
export interface SecurityBlockIndicators {
  cloudflareChallenge: boolean;
  wafBlocked: boolean;
  captchaDetected: boolean;
  statusCode: number;
}

// Extraction types (for future bell schedule extraction)
export interface BellScheduleData {
  startTime?: string;  // e.g., "8:00 AM"
  endTime?: string;    // e.g., "3:00 PM"
  instructionalMinutes?: number;
  schoolLevel?: 'elementary' | 'middle' | 'high' | 'unknown';
  source: string;      // URL where data was found
  confidence: 'high' | 'medium' | 'low';
}

// Configuration
export interface ScraperConfig {
  port: number;
  pool: BrowserPoolConfig;
  queue: QueueConfig;
  userAgent: string;
  respectRobotsTxt: boolean;
  logLevel: 'debug' | 'info' | 'warn' | 'error';
}

// Default configuration
export const DEFAULT_CONFIG: ScraperConfig = {
  port: 3000,
  pool: {
    maxBrowsers: 5,
    launchTimeout: 30000,
    browserOptions: {
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  },
  queue: {
    maxConcurrency: 5,
    maxQueueSize: 100,
    requestDelayMs: 1000,
    timeout: 60000,
  },
  userAgent: 'LCT-BellScheduleScraper/1.0 (Educational Research; https://github.com/ianmmc/learning-connection-time)',
  respectRobotsTxt: true,
  logLevel: 'info',
};
