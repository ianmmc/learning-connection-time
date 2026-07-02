#!/usr/bin/env python3
"""
Ollama-based Intelligent URL and School Selection

Uses local LLMs for:
- Semantic ranking of discovered URLs by likelihood of containing bell schedules
- Intelligent selection of representative school samples

Requires: ollama server running locally (default: http://localhost:11434)
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


@dataclass
class ScoredURL:
    """URL with relevance score and reasoning"""
    url: str
    score: float  # 0.0 to 1.0
    reason: str
    url_patterns_found: List[str] = None

    def __post_init__(self):
        if self.url_patterns_found is None:
            self.url_patterns_found = []


@dataclass
class School:
    """School information for sampling"""
    name: str
    url: str
    grade_level: str  # 'elementary', 'middle', 'high', 'k8', 'k12', 'unknown'
    enrollment: Optional[int] = None


class OllamaSelector:
    """
    Intelligent selector using local Ollama LLMs for URL ranking and school selection.

    Provides semantic analysis to complement pattern-based discovery:
    - Ranks URLs by likelihood of containing bell schedule information
    - Selects representative school samples across grade levels

    Falls back gracefully to pattern matching if Ollama is unavailable.
    """

    # Common bell schedule URL patterns for fallback
    SCHEDULE_PATTERNS = [
        r'bell[-_\s]?schedule',
        r'school[-_\s]?hours',
        r'daily[-_\s]?schedule',
        r'start[-_\s]?time',
        r'dismissal',
        r'arrival',
        r'hours[-_\s]?of[-_\s]?operation',
        r'school[-_\s]?day',
        r'calendar',
        r'schedule[-_\s]?information',
    ]

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout: int = 30
    ):
        """
        Initialize Ollama selector.

        Args:
            model: Ollama model to use (default: llama3.1:8b)
            base_url: Ollama API base URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self._ollama_available = None

    def is_available(self) -> bool:
        """Check if Ollama server is available"""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            self._ollama_available = response.status_code == 200
        except requests.RequestException:
            self._ollama_available = False
            logger.warning("Ollama not available, will use pattern-based fallback")

        return self._ollama_available

    def rank_schedule_urls(
        self,
        urls: List[str],
        district_name: str = "",
        max_results: int = 10
    ) -> List[ScoredURL]:
        """
        Rank URLs by likelihood of containing bell schedule information.

        Args:
            urls: List of URLs to rank
            district_name: District name for context
            max_results: Maximum number of results to return

        Returns:
            List of ScoredURL objects, sorted by score descending
        """
        if not urls:
            return []

        # Always run pattern matching first
        pattern_scores = self._score_urls_by_pattern(urls)

        # Try Ollama for semantic ranking if available
        if self.is_available() and len(urls) <= 50:  # Limit for performance
            try:
                llm_scores = self._rank_with_ollama(urls, district_name)
                # Combine pattern and LLM scores (70% LLM, 30% pattern)
                combined = self._combine_scores(pattern_scores, llm_scores)
            except Exception as e:
                logger.warning(f"Ollama ranking failed, using pattern fallback: {e}")
                combined = pattern_scores
        else:
            combined = pattern_scores

        # Sort by score and return top results
        sorted_urls = sorted(combined, key=lambda x: x.score, reverse=True)
        return sorted_urls[:max_results]

    def _score_urls_by_pattern(self, urls: List[str]) -> List[ScoredURL]:
        """Score URLs based on pattern matching"""
        results = []
        for url in urls:
            url_lower = url.lower()
            patterns_found = []
            score = 0.0

            for pattern in self.SCHEDULE_PATTERNS:
                if re.search(pattern, url_lower):
                    patterns_found.append(pattern)
                    score += 0.2  # Each pattern match adds to score

            # Cap at 1.0
            score = min(score, 1.0)

            # Slight bonus for common paths
            if '/parents' in url_lower or '/families' in url_lower:
                score = min(score + 0.1, 1.0)
            if '/about' in url_lower or '/information' in url_lower:
                score = min(score + 0.05, 1.0)

            # Penalty for unlikely paths
            if '/news' in url_lower or '/blog' in url_lower:
                score = max(score - 0.2, 0.0)
            if '/sports' in url_lower or '/athletics' in url_lower:
                score = max(score - 0.3, 0.0)

            reason = f"Pattern match: {', '.join(patterns_found)}" if patterns_found else "No patterns found"
            results.append(ScoredURL(
                url=url,
                score=score,
                reason=reason,
                url_patterns_found=patterns_found
            ))

        return results

    def _rank_with_ollama(
        self,
        urls: List[str],
        district_name: str
    ) -> List[ScoredURL]:
        """Use Ollama LLM for semantic URL ranking"""
        # Prepare URL list for prompt (truncate if too many)
        url_list = "\n".join(f"{i+1}. {url}" for i, url in enumerate(urls[:30]))

        prompt = f"""You are analyzing URLs from a school district website to find pages likely to contain bell schedule information (school start/end times, daily schedules).

District: {district_name or 'Unknown'}

URLs to analyze:
{url_list}

For each URL, assess the likelihood (0.0-1.0) that it contains bell schedule information based on:
- URL path keywords (schedule, hours, times, bell, calendar)
- Common school website navigation patterns
- Typical locations for schedule information

Return ONLY a valid JSON array with format:
[{{"url": "...", "score": 0.X, "reason": "brief reason"}}]

Focus on URLs with scheduling-related keywords. Be skeptical of generic pages like news, sports, or staff directories."""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for consistency
                        "num_predict": 2000,
                    }
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            output = result.get('response', '')

            # Parse JSON from response
            rankings = self._parse_json_rankings(output, urls)
            return rankings

        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def _parse_json_rankings(
        self,
        output: str,
        original_urls: List[str]
    ) -> List[ScoredURL]:
        """Parse JSON rankings from LLM output"""
        # Try to extract JSON array from response
        try:
            # Look for JSON array in output
            json_match = re.search(r'\[[\s\S]*\]', output)
            if json_match:
                rankings = json.loads(json_match.group())
            else:
                logger.warning("No JSON array found in Ollama response")
                return []

            results = []
            url_set = set(original_urls)

            for item in rankings:
                url = item.get('url', '')
                score = float(item.get('score', 0.0))
                reason = item.get('reason', 'LLM assessment')

                # Validate URL is in original list
                if url in url_set:
                    results.append(ScoredURL(
                        url=url,
                        score=min(max(score, 0.0), 1.0),  # Clamp to [0, 1]
                        reason=f"LLM: {reason}"
                    ))

            return results

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Ollama JSON response: {e}")
            return []

    def _combine_scores(
        self,
        pattern_scores: List[ScoredURL],
        llm_scores: List[ScoredURL]
    ) -> List[ScoredURL]:
        """Combine pattern and LLM scores with weighting"""
        # Create lookup for LLM scores
        llm_lookup = {s.url: s for s in llm_scores}

        combined = []
        for pattern_result in pattern_scores:
            llm_result = llm_lookup.get(pattern_result.url)

            if llm_result:
                # Weighted combination: 70% LLM, 30% pattern
                combined_score = 0.7 * llm_result.score + 0.3 * pattern_result.score
                reason = f"{llm_result.reason}; Pattern: {pattern_result.score:.2f}"
            else:
                combined_score = pattern_result.score
                reason = pattern_result.reason

            combined.append(ScoredURL(
                url=pattern_result.url,
                score=combined_score,
                reason=reason,
                url_patterns_found=pattern_result.url_patterns_found
            ))

        return combined

    def select_school_sample(
        self,
        schools: List[School],
        district_grade_range: str = "PK-12",
        sample_size: int = 3
    ) -> List[School]:
        """
        Select a representative sample of schools across grade levels.

        Args:
            schools: List of discovered schools
            district_grade_range: Grade range served by district (e.g., "PK-12", "K-8")
            sample_size: Number of schools to sample per grade level

        Returns:
            List of selected schools (up to sample_size per level)
        """
        if not schools:
            return []

        # Group schools by grade level
        by_level: Dict[str, List[School]] = {
            'elementary': [],
            'middle': [],
            'high': [],
            'unknown': []
        }

        for school in schools:
            level = self._classify_grade_level(school)
            by_level[level].append(school)

        # Determine which levels to sample based on district grade range
        levels_to_sample = self._get_levels_from_range(district_grade_range)

        # Select samples from each level
        selected = []
        for level in levels_to_sample:
            level_schools = by_level.get(level, [])
            if level_schools:
                # Use Ollama to pick best candidates if available, otherwise random
                if self.is_available() and len(level_schools) > sample_size:
                    try:
                        picked = self._select_with_ollama(level_schools, sample_size)
                    except Exception as e:
                        logger.warning(f"Ollama selection failed: {e}")
                        picked = level_schools[:sample_size]
                else:
                    picked = level_schools[:sample_size]

                selected.extend(picked)

        # If no schools found in target levels, use unknown category
        if not selected and by_level['unknown']:
            selected = by_level['unknown'][:sample_size]

        return selected

    def _classify_grade_level(self, school: School) -> str:
        """Classify school grade level from name or existing classification"""
        if school.grade_level and school.grade_level != 'unknown':
            return school.grade_level

        name_lower = school.name.lower()

        # Elementary indicators
        elem_patterns = ['elementary', 'primary', 'grade school', 'k-5', 'k-4']
        if any(p in name_lower for p in elem_patterns):
            return 'elementary'

        # Middle school indicators
        middle_patterns = ['middle', 'junior high', 'intermediate', '6-8', '7-8']
        if any(p in name_lower for p in middle_patterns):
            return 'middle'

        # High school indicators
        high_patterns = ['high school', 'secondary', 'senior high', '9-12', '10-12']
        if any(p in name_lower for p in high_patterns):
            return 'high'

        return 'unknown'

    def _get_levels_from_range(self, grade_range: str) -> List[str]:
        """Determine which grade levels to sample based on district range"""
        range_lower = grade_range.lower()

        # Check for specific ranges
        if 'k-8' in range_lower or 'pk-8' in range_lower:
            return ['elementary', 'middle']
        if 'k-12' in range_lower or 'pk-12' in range_lower:
            return ['elementary', 'middle', 'high']
        if '9-12' in range_lower:
            return ['high']
        if 'k-5' in range_lower or 'k-6' in range_lower:
            return ['elementary']

        # Default to all levels
        return ['elementary', 'middle', 'high']

    def _select_with_ollama(
        self,
        schools: List[School],
        count: int
    ) -> List[School]:
        """Use Ollama to select best school candidates for schedule discovery"""
        school_list = "\n".join(
            f"{i+1}. {s.name} ({s.grade_level})"
            for i, s in enumerate(schools)
        )

        prompt = f"""Select the {count} best schools from this list for finding bell schedule information.

Prefer:
- Schools with generic/standard names (not special programs)
- Schools likely to have public-facing websites
- Schools that seem representative of typical district schools

Schools:
{school_list}

Return ONLY a JSON array of school indices (1-based): [1, 3, 5]"""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 100}
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            output = response.json().get('response', '')

            # Parse indices from response
            json_match = re.search(r'\[[\d,\s]+\]', output)
            if json_match:
                indices = json.loads(json_match.group())
                selected = []
                for idx in indices[:count]:
                    if 1 <= idx <= len(schools):
                        selected.append(schools[idx - 1])
                return selected

        except Exception as e:
            logger.warning(f"Ollama school selection failed: {e}")

        # Fallback to first N
        return schools[:count]


def main():
    """Test the Ollama selector"""
    logging.basicConfig(level=logging.INFO)

    selector = OllamaSelector()

    # Test URL ranking
    test_urls = [
        "https://district.org/schools",
        "https://district.org/bell-schedule",
        "https://district.org/parents/school-hours",
        "https://district.org/athletics/sports-schedule",
        "https://district.org/about/daily-schedule",
        "https://district.org/news/latest",
        "https://district.org/calendar",
    ]

    print("Testing URL ranking...")
    if selector.is_available():
        print(f"Ollama available with model: {selector.model}")
    else:
        print("Ollama not available, using pattern matching only")

    rankings = selector.rank_schedule_urls(test_urls, "Test District")
    for r in rankings:
        print(f"  {r.score:.2f} - {r.url}")
        print(f"         {r.reason}")


if __name__ == '__main__':
    main()
