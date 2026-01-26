"""
Crawlee HTTP Client

HTTP client for communicating with the Crawlee scraper service.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Default Crawlee service URL
CRAWLEE_BASE_URL = "http://localhost:3000"


@dataclass
class PageData:
    """Rich page metadata from Crawlee mapping."""
    url: str
    title: str
    depth: int
    meta_description: Optional[str]
    h1: Optional[str]
    breadcrumb: Optional[str]
    link_text_used_to_reach_page: str
    time_pattern_count: int
    has_schedule_pdf_link: bool
    keyword_match_count: int
    outbound_link_count: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageData":
        """Create PageData from Crawlee response dict."""
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            depth=data.get("depth", 0),
            meta_description=data.get("metaDescription"),
            h1=data.get("h1"),
            breadcrumb=data.get("breadcrumb"),
            link_text_used_to_reach_page=data.get("linkTextUsedToReachPage", ""),
            time_pattern_count=data.get("timePatternCount", 0),
            has_schedule_pdf_link=data.get("hasSchedulePdfLink", False),
            keyword_match_count=data.get("keywordMatchCount", 0),
            outbound_link_count=data.get("outboundLinkCount", 0),
        )


@dataclass
class MapResult:
    """Result from website mapping."""
    success: bool
    pages: List[PageData]
    pages_visited: int
    pages_with_time_patterns: int
    pages_with_bell_keywords: int
    duration_ms: int
    error: Optional[str] = None


@dataclass
class CaptureResult:
    """Result from PDF capture."""
    url: str
    success: bool
    filename: Optional[str] = None
    filepath: Optional[str] = None
    size_bytes: Optional[int] = None
    title: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CaptureResponse:
    """Response from PDF capture endpoint."""
    success: bool
    results: List[CaptureResult]
    total: int
    successful: int
    failed: int
    duration_ms: int
    error: Optional[str] = None


class CrawleeClient:
    """HTTP client for Crawlee scraper service."""

    def __init__(self, base_url: str = CRAWLEE_BASE_URL, timeout: float = 300.0):
        """
        Initialize Crawlee client.

        Args:
            base_url: Base URL of Crawlee service
            timeout: Request timeout in seconds (default 5 minutes for mapping)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> bool:
        """Check if Crawlee service is healthy."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Crawlee health check failed: {e}")
            return False

    async def map_website(
        self,
        url: str,
        max_requests: int = 100,
        max_depth: int = 4,
        include_globs: Optional[List[str]] = None,
        exclude_globs: Optional[List[str]] = None,
    ) -> MapResult:
        """
        Map a website using Crawlee.

        Args:
            url: Website URL to map
            max_requests: Maximum pages to crawl
            max_depth: Maximum crawl depth
            include_globs: URL patterns to include
            exclude_globs: URL patterns to exclude

        Returns:
            MapResult with pages and statistics
        """
        client = await self._get_client()

        payload = {
            "url": url,
            "maxRequests": max_requests,
            "maxDepth": max_depth,
        }

        if include_globs or exclude_globs:
            payload["patterns"] = {}
            if include_globs:
                payload["patterns"]["includeGlobs"] = include_globs
            if exclude_globs:
                payload["patterns"]["excludeGlobs"] = exclude_globs

        logger.info(f"Mapping website: {url} (max={max_requests}, depth={max_depth})")

        try:
            response = await client.post(
                f"{self.base_url}/map",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            pages = [PageData.from_dict(p) for p in data.get("pages", [])]
            stats = data.get("stats", {})

            return MapResult(
                success=data.get("success", False),
                pages=pages,
                pages_visited=stats.get("pagesVisited", 0),
                pages_with_time_patterns=stats.get("pagesWithTimePatterns", 0),
                pages_with_bell_keywords=stats.get("pagesWithBellKeywords", 0),
                duration_ms=stats.get("durationMs", 0),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Map request failed: {e}")
            return MapResult(
                success=False,
                pages=[],
                pages_visited=0,
                pages_with_time_patterns=0,
                pages_with_bell_keywords=0,
                duration_ms=0,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Map request error: {e}")
            return MapResult(
                success=False,
                pages=[],
                pages_visited=0,
                pages_with_time_patterns=0,
                pages_with_bell_keywords=0,
                duration_ms=0,
                error=str(e),
            )

    async def capture_pages(
        self,
        urls: List[str],
        output_dir: str,
        timeout: int = 30000,
    ) -> CaptureResponse:
        """
        Capture multiple pages as PDFs.

        Args:
            urls: URLs to capture
            output_dir: Directory to save PDFs
            timeout: Navigation timeout in milliseconds

        Returns:
            CaptureResponse with results for each URL
        """
        client = await self._get_client()

        payload = {
            "urls": urls,
            "outputDir": output_dir,
            "timeout": timeout,
        }

        logger.info(f"Capturing {len(urls)} pages to {output_dir}")

        try:
            response = await client.post(
                f"{self.base_url}/capture",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("results", []):
                results.append(CaptureResult(
                    url=r.get("url", ""),
                    success=r.get("success", False),
                    filename=r.get("filename"),
                    filepath=r.get("filepath"),
                    size_bytes=r.get("sizeBytes"),
                    title=r.get("title"),
                    error=r.get("error"),
                ))

            stats = data.get("stats", {})

            return CaptureResponse(
                success=data.get("success", False),
                results=results,
                total=stats.get("total", 0),
                successful=stats.get("successful", 0),
                failed=stats.get("failed", 0),
                duration_ms=stats.get("durationMs", 0),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Capture request failed: {e}")
            return CaptureResponse(
                success=False,
                results=[],
                total=len(urls),
                successful=0,
                failed=len(urls),
                duration_ms=0,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Capture request error: {e}")
            return CaptureResponse(
                success=False,
                results=[],
                total=len(urls),
                successful=0,
                failed=len(urls),
                duration_ms=0,
                error=str(e),
            )
