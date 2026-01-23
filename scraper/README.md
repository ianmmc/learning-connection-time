# LCT Bell Schedule Scraper

HTTP service for scraping bell schedules from school district websites with JavaScript rendering support.

## Features

- **JavaScript Rendering**: Uses Playwright to render JS-heavy pages (Canvas LMS, SchoolWires, Edlio)
- **Browser Pool**: Manages 5-10 browser instances for efficient resource usage
- **Request Queue**: Bounds concurrency and rate limits per domain
- **Security Block Detection**: Detects Cloudflare, WAF, and CAPTCHA challenges
- **Ethical Scraping**: No bot evasion, respects security blocks

## Quick Start

### Local Development

```bash
# Install dependencies
npm install

# Install Playwright browsers
npx playwright install chromium

# Run in development mode (with hot reload)
npm run dev

# Or build and run
npm run build
npm start
```

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or from project root (includes postgres)
cd .. && docker-compose up -d scraper
```

## API Reference

### POST /scrape

Scrape a URL and return the content.

**Request:**
```json
{
  "url": "https://example.edu/bell-schedule",
  "timeout": 30000,
  "waitFor": 2000
}
```

**Response (success):**
```json
{
  "success": true,
  "url": "https://example.edu/bell-schedule",
  "html": "<html>...",
  "markdown": "# Bell Schedule\n...",
  "title": "Bell Schedule - Example School",
  "timing": 1523
}
```

**Response (blocked):**
```json
{
  "success": false,
  "url": "https://example.edu/bell-schedule",
  "error": "Security block detected - flagged for manual collection",
  "errorCode": "BLOCKED",
  "blocked": true,
  "timing": 2341
}
```

### GET /health

Health check endpoint.

```json
{
  "status": "healthy",
  "timestamp": "2026-01-21T12:00:00.000Z"
}
```

### GET /status

Detailed service status.

```json
{
  "status": "healthy",
  "queueDepth": 3,
  "activeBrowsers": 2,
  "maxBrowsers": 5,
  "processed": 150,
  "failed": 12,
  "blocked": 5,
  "uptime": 3600
}
```

### POST /discover ⭐ NEW

Discover individual school websites within a district.

**Background:** Research shows 80%+ of districts do NOT publish district-wide bell schedules. This endpoint uses multiple strategies to find school-level sites.

**Request:**
```json
{
  "districtUrl": "https://district.org",
  "state": "WI",
  "representativeOnly": true
}
```

**Response (success):**
```json
{
  "success": true,
  "districtUrl": "https://district.org",
  "schools": [
    {
      "url": "https://hs.district.org",
      "name": "high school",
      "level": "high",
      "pattern": "subdomain_test"
    },
    {
      "url": "https://ms.district.org",
      "name": "middle school",
      "level": "middle",
      "pattern": "subdomain_test"
    }
  ],
  "method": "multi_strategy",
  "totalFound": 5,
  "returned": 2
}
```

**Discovery Methods:**
1. **Subdomain Testing** - Tests common patterns (hs.district.org, elementary.district.org)
2. **Link Extraction** - Parses district "Schools" directory page
3. **State-Specific Patterns** - Uses state-specific URL conventions (e.g., .k12.wi.us)

## Usage from Python

```python
import requests

SCRAPER_URL = "http://localhost:3000"

def scrape_bell_schedule(url: str, timeout: int = 30) -> dict | None:
    """Scrape a URL using the scraper service."""
    try:
        response = requests.post(
            f"{SCRAPER_URL}/scrape",
            json={"url": url, "timeout": timeout * 1000},
            timeout=timeout + 10
        )
        data = response.json()
        if data.get("success"):
            return data
        return None
    except requests.RequestException:
        return None
```

## Usage from Bash (for subagents)

```bash
# Scrape a URL
curl -X POST http://localhost:3000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.edu/bell-schedule"}'

# Check status
curl http://localhost:3000/status
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 3000 | HTTP server port |
| `LOG_LEVEL` | info | Logging level (debug, info, warn, error) |
| `NODE_ENV` | development | Environment (development, production) |

Pool/queue settings are configured in `src/types.ts`:

```typescript
export const DEFAULT_CONFIG = {
  pool: {
    maxBrowsers: 5,           // Max concurrent browsers
    launchTimeout: 30000,     // Browser launch timeout
  },
  queue: {
    maxConcurrency: 5,        // Max concurrent requests
    maxQueueSize: 100,        // Max queued requests
    requestDelayMs: 1000,     // Delay between requests to same domain
  },
};
```

## Ethical Constraints

This scraper follows the project's ethical guidelines:

1. **Respect security blocks**: On Cloudflare/WAF/CAPTCHA detection, requests are flagged for manual collection rather than bypassed
2. **No bot evasion**: Uses honest user-agent, no fingerprint spoofing
3. **Rate limiting**: Delays requests to the same domain
4. **Transparency**: All attempts and outcomes are logged

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HTTP Server                          │
│                   (Express.js)                          │
├─────────────────────────────────────────────────────────┤
│                  Request Queue                          │
│         (p-queue with rate limiting)                    │
├─────────────────────────────────────────────────────────┤
│                  Browser Pool                           │
│        (5-10 Playwright instances)                      │
├─────────────────────────────────────────────────────────┤
│                    Scraper                              │
│     (Page navigation + security detection)              │
└─────────────────────────────────────────────────────────┘
```

## Parallel Subagent Usage

For running a swarm of subagents across 50 states:

1. Start the scraper service
2. Launch subagents in parallel (each assigned states/districts)
3. Each subagent calls `POST /scrape` with their URLs
4. Service manages queueing and browser pool automatically
5. Subagents receive responses as requests complete

The service handles backpressure automatically - if queue is full, requests get a 503 response.
