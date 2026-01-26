"""
Ollama Service

Interfaces with Ollama for:
- URL ranking (phi-3-mini)
- PDF text triage (llama3:8b-instruct)
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import yaml

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None

logger = logging.getLogger(__name__)

# Default prompt templates directory
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "config" / "prompts"


@dataclass
class URLScore:
    """Score for a single URL."""
    url: str
    score: float
    reason: str


@dataclass
class PDFTriageResult:
    """Result from PDF triage."""
    score: float
    reason: str
    times_found: List[str]
    is_bell_schedule: bool


class OllamaService:
    """Service for Ollama-based URL ranking and PDF triage."""

    def __init__(
        self,
        url_ranking_model: str = "phi3:mini",
        pdf_triage_model: str = "llama3.1:8b",
        prompts_dir: Optional[Path] = None,
    ):
        """
        Initialize Ollama service.

        Args:
            url_ranking_model: Model for URL ranking (default: phi3:mini - fast, ~2GB)
            pdf_triage_model: Model for PDF triage (default: llama3:8b - accurate, ~5GB)
            prompts_dir: Directory containing prompt templates
        """
        self.url_ranking_model = url_ranking_model
        self.pdf_triage_model = pdf_triage_model
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self._prompts_cache: Dict[str, Dict[str, Any]] = {}

        if not OLLAMA_AVAILABLE:
            logger.warning("Ollama package not installed. Install with: pip install ollama")

    def _load_prompt(self, name: str) -> Dict[str, Any]:
        """Load a prompt template from YAML file."""
        if name in self._prompts_cache:
            return self._prompts_cache[name]

        prompt_file = self.prompts_dir / f"{name}.yaml"
        if prompt_file.exists():
            with open(prompt_file) as f:
                prompt = yaml.safe_load(f)
                self._prompts_cache[name] = prompt
                return prompt

        # Return default prompt if file doesn't exist
        logger.warning(f"Prompt file not found: {prompt_file}, using defaults")
        return self._get_default_prompt(name)

    def _get_default_prompt(self, name: str) -> Dict[str, Any]:
        """Get default prompt if template file doesn't exist."""
        if name == "url_ranking":
            return {
                "model": self.url_ranking_model,
                "temperature": 0.1,
                "max_tokens": 500,
                "system": """You are a URL classifier for school district websites.
Your task is to score pages by likelihood of containing bell schedule information.
Bell schedules contain school start times, end times, and daily period schedules.

Strong positive signals:
- H1 or title contains "bell schedule", "school hours", "daily schedule"
- Link text used to reach page mentions "schedule" or "times"
- Multiple time patterns (8:00 AM, 3:15 PM) found on page
- PDF links with "schedule" in the link text

Strong negative signals:
- "athletic", "sports", "bus", "lunch", "testing" in URL or title
- Calendar/event pages (dates, not daily times)
- News articles""",
                "prompt_template": """Rate these pages from {district_name} school district.
Score each 0.0-1.0 for likelihood of containing bell schedule (start/end times).

Pages:
{pages_data}

Return JSON array: [{{"url": "...", "score": 0.X, "reason": "..."}}]"""
            }
        elif name == "pdf_triage":
            return {
                "model": self.pdf_triage_model,
                "temperature": 0.1,
                "max_tokens": 300,
                "system": """You analyze extracted PDF text to determine if it contains school bell schedule data.
Bell schedules include specific times (e.g., "8:00 AM", "3:15 PM") for school start,
end, lunch, or class periods.""",
                "prompt_template": """Analyze this text extracted from a PDF on a school district website.
Does it contain bell schedule information (specific start/end times)?

Text:
{pdf_text}

Return JSON: {{"score": 0.X, "reason": "...", "times_found": [...]}}"""
            }
        return {}

    def _format_pages_for_ranking(self, pages: List[Dict[str, Any]]) -> str:
        """Format page data for URL ranking prompt."""
        formatted = []
        for i, page in enumerate(pages, 1):
            entry = f"""{i}. URL: {page.get('url', '')}
   Title: {page.get('title', '')}
   H1: {page.get('h1') or 'N/A'}
   Meta: {page.get('meta_description') or 'N/A'}
   Link text: {page.get('link_text_used_to_reach_page') or 'N/A'}
   Breadcrumb: {page.get('breadcrumb') or 'N/A'}
   Time patterns: {page.get('time_pattern_count', 0)}
   Has schedule PDF link: {page.get('has_schedule_pdf_link', False)}
   Keywords: {page.get('keyword_match_count', 0)}"""
            formatted.append(entry)
        return "\n\n".join(formatted)

    def _extract_json_from_response(self, text: str) -> Any:
        """Extract JSON from Ollama response, handling markdown code blocks."""
        # Try to find JSON in code blocks
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if code_block_match:
            text = code_block_match.group(1)

        # Try to find JSON array or object
        json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse JSON from response: {text[:200]}")
            return None

    async def rank_urls(
        self,
        pages: List[Dict[str, Any]],
        district_name: str,
    ) -> List[URLScore]:
        """
        Rank URLs by likelihood of containing bell schedule content.

        Args:
            pages: List of page data from Crawlee
            district_name: Name of the district

        Returns:
            List of URLScore objects sorted by score descending
        """
        if not OLLAMA_AVAILABLE:
            logger.error("Ollama not available, returning heuristic scores")
            return self._heuristic_url_ranking(pages)

        prompt_config = self._load_prompt("url_ranking")
        pages_data = self._format_pages_for_ranking(pages)

        prompt = prompt_config["prompt_template"].format(
            district_name=district_name,
            pages_data=pages_data,
        )

        logger.info(f"Ranking {len(pages)} URLs for {district_name}")

        try:
            response = ollama.chat(
                model=prompt_config.get("model", self.url_ranking_model),
                messages=[
                    {"role": "system", "content": prompt_config.get("system", "")},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": prompt_config.get("temperature", 0.1),
                    "num_predict": prompt_config.get("max_tokens", 500),
                },
            )

            content = response.get("message", {}).get("content", "")
            scores_data = self._extract_json_from_response(content)

            if not scores_data or not isinstance(scores_data, list):
                logger.warning("Invalid response format, using heuristic scores")
                return self._heuristic_url_ranking(pages)

            scores = []
            for item in scores_data:
                scores.append(URLScore(
                    url=item.get("url", ""),
                    score=float(item.get("score", 0)),
                    reason=item.get("reason", ""),
                ))

            # Sort by score descending
            scores.sort(key=lambda x: x.score, reverse=True)
            return scores

        except Exception as e:
            logger.error(f"Ollama URL ranking failed: {e}")
            return self._heuristic_url_ranking(pages)

    def _heuristic_url_ranking(self, pages: List[Dict[str, Any]]) -> List[URLScore]:
        """Fallback heuristic-based URL ranking when Ollama is unavailable."""
        scores = []
        for page in pages:
            score = 0.0
            reasons = []

            # Time patterns are strong signal
            time_count = page.get("time_pattern_count", 0)
            if time_count > 50:
                score += 0.5
                reasons.append(f"{time_count} time patterns")
            elif time_count > 10:
                score += 0.3
                reasons.append(f"{time_count} time patterns")
            elif time_count > 3:
                score += 0.15
                reasons.append(f"{time_count} time patterns")

            # Keywords in URL
            url_lower = page.get("url", "").lower()
            if "bell" in url_lower and "schedule" in url_lower:
                score += 0.3
                reasons.append("URL contains 'bell schedule'")
            elif "schedule" in url_lower:
                score += 0.15
                reasons.append("URL contains 'schedule'")

            # H1 or title
            h1 = (page.get("h1") or "").lower()
            title = (page.get("title") or "").lower()
            if "bell schedule" in h1 or "bell schedule" in title:
                score += 0.2
                reasons.append("Title/H1 contains 'bell schedule'")

            # Keyword match count
            kw_count = page.get("keyword_match_count", 0)
            if kw_count > 10:
                score += 0.1
                reasons.append(f"{kw_count} keywords")

            # Has schedule PDF link
            if page.get("has_schedule_pdf_link"):
                score += 0.1
                reasons.append("Has schedule PDF link")

            # Negative signals
            if any(x in url_lower for x in ["athletic", "sports", "bus", "lunch", "news"]):
                score -= 0.2
                reasons.append("Negative URL pattern")

            score = max(0.0, min(1.0, score))
            scores.append(URLScore(
                url=page.get("url", ""),
                score=score,
                reason="; ".join(reasons) if reasons else "No strong signals",
            ))

        scores.sort(key=lambda x: x.score, reverse=True)
        return scores

    async def triage_pdf(self, pdf_text: str) -> PDFTriageResult:
        """
        Analyze PDF text to determine if it contains bell schedule data.

        Args:
            pdf_text: Extracted text from PDF

        Returns:
            PDFTriageResult with score and analysis
        """
        if not OLLAMA_AVAILABLE:
            logger.error("Ollama not available, returning heuristic triage")
            return self._heuristic_pdf_triage(pdf_text)

        prompt_config = self._load_prompt("pdf_triage")

        # Truncate text if too long
        max_text_len = 4000
        if len(pdf_text) > max_text_len:
            pdf_text = pdf_text[:max_text_len] + "\n...[truncated]"

        prompt = prompt_config["prompt_template"].format(pdf_text=pdf_text)

        logger.info(f"Triaging PDF ({len(pdf_text)} chars)")

        try:
            response = ollama.chat(
                model=prompt_config.get("model", self.pdf_triage_model),
                messages=[
                    {"role": "system", "content": prompt_config.get("system", "")},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": prompt_config.get("temperature", 0.1),
                    "num_predict": prompt_config.get("max_tokens", 300),
                },
            )

            content = response.get("message", {}).get("content", "")
            result_data = self._extract_json_from_response(content)

            if not result_data or not isinstance(result_data, dict):
                logger.warning("Invalid response format, using heuristic triage")
                return self._heuristic_pdf_triage(pdf_text)

            score = float(result_data.get("score", 0))
            return PDFTriageResult(
                score=score,
                reason=result_data.get("reason", ""),
                times_found=result_data.get("times_found", []),
                is_bell_schedule=score >= 0.7,
            )

        except Exception as e:
            logger.error(f"Ollama PDF triage failed: {e}")
            return self._heuristic_pdf_triage(pdf_text)

    def _heuristic_pdf_triage(self, pdf_text: str) -> PDFTriageResult:
        """Fallback heuristic-based PDF triage when Ollama is unavailable."""
        text_lower = pdf_text.lower()

        # Find time patterns
        time_patterns = re.findall(
            r'\d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?',
            pdf_text
        )

        score = 0.0
        reasons = []

        # Time patterns
        if len(time_patterns) > 20:
            score += 0.5
            reasons.append(f"{len(time_patterns)} time patterns found")
        elif len(time_patterns) > 5:
            score += 0.3
            reasons.append(f"{len(time_patterns)} time patterns found")

        # Bell schedule keywords
        if "bell schedule" in text_lower:
            score += 0.3
            reasons.append("Contains 'bell schedule'")
        elif "school hours" in text_lower:
            score += 0.2
            reasons.append("Contains 'school hours'")

        # Period indicators
        period_matches = len(re.findall(r'period\s*\d|1st\s*period|2nd\s*period', text_lower))
        if period_matches > 3:
            score += 0.2
            reasons.append(f"{period_matches} period references")

        # Start/end time keywords
        if any(x in text_lower for x in ["start time", "end time", "dismissal"]):
            score += 0.1
            reasons.append("Contains start/end time keywords")

        score = max(0.0, min(1.0, score))

        return PDFTriageResult(
            score=score,
            reason="; ".join(reasons) if reasons else "No strong signals",
            times_found=time_patterns[:10],  # Limit to first 10
            is_bell_schedule=score >= 0.7,
        )
