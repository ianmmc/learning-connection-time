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
class SchoolSite:
    """School site discovered from a district."""
    url: str
    name: str
    level: Optional[str]  # 'elementary', 'middle', 'high', or None
    pattern: str  # How it was discovered


@dataclass
class DiscoveryResult:
    """Result from school discovery."""
    success: bool
    schools: List[SchoolSite]
    sample: List[SchoolSite]  # Grade-band sampled subset
    method: str
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

    async def discover_schools(
        self,
        district_url: str,
        state: Optional[str] = None,
        per_band: int = 4,
        timeout: int = 30000,
    ) -> DiscoveryResult:
        """
        Discover school sites from a district website.

        Args:
            district_url: District website URL
            state: State code (e.g., 'FL') for state-specific patterns
            per_band: Number of schools to sample per grade band (default: 4)
            timeout: Navigation timeout in milliseconds

        Returns:
            DiscoveryResult with all schools and sampled subset
        """
        client = await self._get_client()

        payload = {
            "districtUrl": district_url,
            "perBand": per_band,
            "timeout": timeout,
        }
        if state:
            payload["state"] = state

        logger.info(f"Discovering schools for {district_url} (perBand={per_band})")

        try:
            response = await client.post(
                f"{self.base_url}/discover/sample",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Parse schools
            schools = []
            for s in data.get("schools", []):
                schools.append(SchoolSite(
                    url=s.get("url", ""),
                    name=s.get("name", ""),
                    level=s.get("level"),
                    pattern=s.get("pattern", "unknown"),
                ))

            # Parse sample
            sample = []
            for s in data.get("sample", []):
                sample.append(SchoolSite(
                    url=s.get("url", ""),
                    name=s.get("name", ""),
                    level=s.get("level"),
                    pattern=s.get("pattern", "unknown"),
                ))

            return DiscoveryResult(
                success=data.get("success", False),
                schools=schools,
                sample=sample,
                method=data.get("method", "unknown"),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"School discovery failed: {e}")
            return DiscoveryResult(
                success=False,
                schools=[],
                sample=[],
                method="error",
                error=str(e),
            )
        except Exception as e:
            logger.error(f"School discovery error: {e}")
            return DiscoveryResult(
                success=False,
                schools=[],
                sample=[],
                method="error",
                error=str(e),
            )

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

    async def start_map_job(
        self,
        url: str,
        max_requests: int = 30,
        max_depth: int = 3,
        exclude_globs: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Start an async mapping job.

        Args:
            url: Website URL to map
            max_requests: Maximum pages to crawl
            max_depth: Maximum crawl depth
            exclude_globs: URL patterns to exclude

        Returns:
            Job ID if successful, None otherwise
        """
        client = await self._get_client()

        payload = {
            "url": url,
            "maxRequests": max_requests,
            "maxDepth": max_depth,
        }
        if exclude_globs:
            payload["patterns"] = {"excludeGlobs": exclude_globs}

        try:
            response = await client.post(
                f"{self.base_url}/map/start",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("jobId")
        except Exception as e:
            logger.error(f"Failed to start map job: {e}")
            return None

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of an async mapping job.

        Returns:
            Job status dict or None if not found
        """
        client = await self._get_client()

        try:
            response = await client.get(f"{self.base_url}/map/status/{job_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return None

    async def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> MapResult:
        """
        Wait for an async mapping job to complete.

        Args:
            job_id: Job ID to wait for
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            MapResult when job completes
        """
        import asyncio
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return MapResult(
                    success=False,
                    pages=[],
                    pages_visited=0,
                    pages_with_time_patterns=0,
                    pages_with_bell_keywords=0,
                    duration_ms=int(elapsed * 1000),
                    error=f"Job timed out after {timeout}s",
                )

            status = await self.get_job_status(job_id)
            if not status:
                return MapResult(
                    success=False,
                    pages=[],
                    pages_visited=0,
                    pages_with_time_patterns=0,
                    pages_with_bell_keywords=0,
                    duration_ms=0,
                    error="Job not found",
                )

            phase = status.get("phase")

            if phase == "completed":
                pages = [PageData.from_dict(p) for p in status.get("pages", [])]
                stats = status.get("stats", {})
                return MapResult(
                    success=True,
                    pages=pages,
                    pages_visited=stats.get("pagesVisited", len(pages)),
                    pages_with_time_patterns=stats.get("pagesWithTimePatterns", 0),
                    pages_with_bell_keywords=stats.get("pagesWithBellKeywords", 0),
                    duration_ms=stats.get("durationMs", 0),
                )

            if phase == "failed":
                return MapResult(
                    success=False,
                    pages=[],
                    pages_visited=0,
                    pages_with_time_patterns=0,
                    pages_with_bell_keywords=0,
                    duration_ms=0,
                    error=status.get("error", "Job failed"),
                )

            # Still running, wait and poll again
            await asyncio.sleep(poll_interval)

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
