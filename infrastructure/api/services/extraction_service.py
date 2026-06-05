"""
extraction_service.py - Ollama-based bell schedule time extraction

PURPOSE:
    Extracts structured bell schedule data (start times, end times, grade levels)
    from PDF text using Ollama LLM. This is an automated extraction step that
    produces data for Claude verification.

CONTEXT - ENRICHMENT PIPELINE POSITION:
    This service is Step 1 of 5 in the Phase 8 Enrichment Pipeline:
    1. Ollama extraction (POST /enrich/extract) → extraction_result.json  <-- THIS SERVICE
    2. Claude verification → verified_extraction.json
    3. calculate_minutes.py → enrichment_ready.json
    4. import_bell_schedules.py → database + import_result.json
    5. verify_enrichment.py → verification_report.json

    This service handles step 1: Automated LLM extraction of times from PDF text.
    It produces extraction_result.json which Claude then verifies against source.

INPUT:
    - PDF text (string) from active/*.txt files
    - District metadata (district_id, district_name, state)

OUTPUT:
    - ExtractionResult dataclass containing:
        - schedules: List of extracted bell schedules with times
        - confidence: Overall extraction confidence
        - raw_response: Original LLM response for debugging
    - JSON written to: data/raw/bell_schedule_pdfs/{state}/{district}/extraction_result.json

DEPENDENCIES:
    - ollama (pip install ollama)
    - yaml (standard library or pip install pyyaml)

SEE ALSO:
    - Plan: ~/.claude/plans/crispy-brewing-blanket.md (Phase 8)
    - Related: ollama_service.py (PDF triage), enrich.py (API endpoint)
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None

from infrastructure.api.services.ollama_launcher import ensure_ollama_running

logger = logging.getLogger(__name__)


@dataclass
class ExtractedSchedule:
    """A single extracted bell schedule entry."""
    grade_level: str  # "elementary", "middle", "high"
    start_time: str   # "HH:MM" format (24-hour)
    end_time: str     # "HH:MM" format (24-hour)
    school_name: Optional[str] = None
    source_file: Optional[str] = None
    confidence: str = "medium"  # "high", "medium", "low"
    raw_text_snippet: str = ""  # Source text for verification
    notes: str = ""


@dataclass
class ExtractionResult:
    """Result from bell schedule extraction."""
    district_id: str
    district_name: str
    state: str
    extraction_date: str
    extractor: str = "ollama"
    schedules: List[ExtractedSchedule] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    raw_response: Optional[str] = None  # For debugging

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["schedules"] = [asdict(s) for s in self.schedules]
        return result


class ExtractionService:
    """Service for extracting bell schedule times from PDF text using Ollama."""

    # Extraction model - uses same model as PDF triage for consistency
    DEFAULT_MODEL = "llama3.1:8b"

    # System prompt for extraction - Updated with negative signals (Phase 9)
    SYSTEM_PROMPT = """You are a data extraction specialist for school bell schedules.

Your task is to extract specific START and END times for the school day from PDF text.
Bell schedules contain when school starts and ends, sometimes broken down by grade level
(elementary, middle, high school).

CRITICAL - TIMES TO SKIP (these are NOT school hours):
- "Office Hours" - administrative staff hours, not student hours
- "Library Hours" - when library is open
- "Before/After Care" - extended day programs
- "Breakfast served/begins" - pre-school services
- "Campus closes" - building hours, not instruction
- "Building Hours" - facility hours, not instruction
- "Extended Day" - optional programs, not regular school

EXTRACTION RULES:
1. Look for labels like "School Hours", "School Begins", "Dismissal", "First Bell"
2. If times are given per period, use Period 1 start as school start and LAST PERIOD end as school end
   - Common error: Don't use intermediate period end times
3. Convert all times to 24-hour HH:MM format (e.g., "8:30 AM" → "08:30", "3:15 PM" → "15:15")
4. If multiple grade levels have different times, extract EACH ONE separately
5. If document has multiple schools, try to extract representative times for EACH grade band
6. Include a raw text snippet showing where you found the times
7. Set confidence to "high" if times are explicitly stated with "School Hours" or "Dismissal" labels,
   "medium" if inferred from periods, "low" if uncertain

GRADE LEVEL DETECTION - USE THESE PATTERNS:
- Elementary/Primary: school name contains "elementary", "primary", "ES", "Elem", "K-5", "K-6"
- Middle/Junior High: school name contains "middle", "junior", "MS", "JH", "6-8", "7-8"
- High: school name contains "high school", "HS", "senior", "9-12", "secondary"
- If document is organized by grade level sections, extract from each section

IMPORTANT: If the document has data for elementary, middle, AND high schools, you MUST
extract at least one schedule for EACH grade level. Missing a grade level is an error.

OUTPUT FORMAT (JSON):
{
  "schedules": [
    {
      "grade_level": "high",
      "start_time": "08:10",
      "end_time": "14:35",
      "school_name": "Fivay High School",
      "confidence": "high",
      "raw_text_snippet": "School Hours: 8:10 AM - 2:35 PM",
      "notes": "Times explicitly stated on bell schedule page"
    }
  ]
}

If you cannot find any bell schedule times, return:
{"schedules": [], "error": "No bell schedule times found in text"}
"""

    USER_PROMPT_TEMPLATE = """Extract bell schedule start and end times from this school district PDF text.
District: {district_name} ({state})

PDF TEXT:
{pdf_text}

Return ONLY valid JSON with the extracted schedules. Include the raw_text_snippet showing
exactly where you found the times."""

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize extraction service.

        Args:
            model: Ollama model to use for extraction
        """
        self.model = model

        if not OLLAMA_AVAILABLE:
            logger.warning("Ollama package not installed. Install with: pip install ollama")

    def _normalize_time(self, time_str: str) -> Optional[str]:
        """
        Normalize time string to HH:MM 24-hour format.

        Examples:
            "8:30 AM" → "08:30"
            "3:15 PM" → "15:15"
            "08:00" → "08:00"
        """
        if not time_str:
            return None

        time_str = time_str.strip().upper()

        # Try to parse various formats
        patterns = [
            (r'(\d{1,2}):(\d{2})\s*(AM|PM)', True),   # "8:30 AM" or "3:15 PM"
            (r'(\d{1,2}):(\d{2})', False),            # "08:30" or "15:15"
        ]

        for pattern, has_ampm in patterns:
            match = re.match(pattern, time_str)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))

                if has_ampm:
                    ampm = match.group(3)
                    if ampm == "PM" and hour != 12:
                        hour += 12
                    elif ampm == "AM" and hour == 12:
                        hour = 0

                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return f"{hour:02d}:{minute:02d}"

        return None

    def _extract_json_from_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from Ollama response, handling markdown code blocks."""
        text = text.strip()

        # Remove markdown code block wrappers
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'```\s*$', '', text)
            text = text.strip()

        # Try to find JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try parsing the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse JSON from response: {text[:200]}")
            return None

    def _load_extraction_rules(self) -> Optional[Dict[str, Any]]:
        """Load extraction rules from config file."""
        rules_path = Path(__file__).parent.parent.parent.parent / "data" / "config" / "extraction_rules.json"
        if rules_path.exists():
            try:
                with open(rules_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load extraction rules: {e}")
        return None

    def _validate_and_enhance_extraction(
        self,
        result: 'ExtractionResult',
        rules: Optional[Dict[str, Any]] = None
    ) -> 'ExtractionResult':
        """
        Apply validation rules and grade level inference to extraction result.

        Phase 9: Extraction Learning Loop
        - Layer 1: Skip times near negative patterns (already in prompt)
        - Layer 2: Improved SYSTEM_PROMPT (already updated)
        - Layer 3: This function - post-extraction validation

        Actions:
        1. Infer grade level from school name if "unknown"
        2. Flag suspicious times (validation warnings)
        3. Check for missing grade levels

        Args:
            result: ExtractionResult from Ollama
            rules: Optional extraction rules dict (loads from file if None)

        Returns:
            Enhanced ExtractionResult with inferred grades and validation warnings
        """
        if rules is None:
            rules = self._load_extraction_rules()

        if not rules:
            logger.info("No extraction rules loaded, skipping validation")
            return result

        # 1. Grade level inference for "unknown" schedules
        grade_inference = rules.get("grade_level_inference", {})
        for schedule in result.schedules:
            if schedule.grade_level == "unknown" and schedule.school_name:
                name_lower = schedule.school_name.lower()

                for level in ["elementary", "middle", "high"]:
                    patterns = grade_inference.get(level, [])
                    for pattern in patterns:
                        if re.search(pattern, name_lower, re.IGNORECASE):
                            schedule.grade_level = level
                            schedule.notes = (schedule.notes + " [Grade inferred from school name]").strip()
                            logger.info(f"Inferred grade level '{level}' from school name: {schedule.school_name}")
                            break
                    if schedule.grade_level != "unknown":
                        break

        # 2. Validate time ranges
        validation_rules = rules.get("validation_rules", {})
        max_minutes = validation_rules.get("max_school_day_minutes", 480)
        min_minutes = validation_rules.get("min_school_day_minutes", 300)

        for schedule in result.schedules:
            try:
                start_parts = schedule.start_time.split(":")
                end_parts = schedule.end_time.split(":")
                start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
                end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
                duration = end_minutes - start_minutes

                warnings = []
                start_hour = int(start_parts[0])

                if duration > max_minutes:
                    warnings.append(f"Duration {duration}min exceeds max {max_minutes}min")
                if duration < min_minutes:
                    warnings.append(f"Duration {duration}min below min {min_minutes}min")
                if start_hour < 7:
                    warnings.append(f"Start time {schedule.start_time} before 7:00")
                if start_hour > 10:
                    warnings.append(f"Start time {schedule.start_time} after 10:00")

                if warnings:
                    schedule.confidence = "low"
                    schedule.notes = (schedule.notes + f" [VALIDATION: {'; '.join(warnings)}]").strip()
                    logger.warning(f"Validation warnings for {schedule.grade_level}: {warnings}")

            except (ValueError, IndexError) as e:
                logger.warning(f"Could not validate times for schedule: {e}")

        # 3. Check for missing grade levels
        found_levels = {s.grade_level for s in result.schedules if s.grade_level != "unknown"}
        all_levels = {"elementary", "middle", "high"}
        missing = all_levels - found_levels

        if missing and len(result.schedules) > 0:
            # Only warn if we found some schedules but not all grade levels
            result.error = f"WARNING: Missing grade levels: {missing}. Document may have more data."
            logger.warning(f"Missing grade levels for {result.district_id}: {missing}")

        return result

    async def extract_times(
        self,
        pdf_text: str,
        district_id: str,
        district_name: str,
        state: str,
        source_file: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract bell schedule times from PDF text using Ollama.

        Args:
            pdf_text: Extracted text from PDF
            district_id: NCES district ID
            district_name: District name
            state: State code (e.g., "FL")
            source_file: Optional source filename for tracking

        Returns:
            ExtractionResult with extracted schedules
        """
        result = ExtractionResult(
            district_id=district_id,
            district_name=district_name,
            state=state,
            extraction_date=datetime.utcnow().isoformat(),
        )

        if not OLLAMA_AVAILABLE:
            result.success = False
            result.error = "Ollama not available"
            return result

        # Ensure Ollama is running (starts it at low priority if needed)
        if not ensure_ollama_running():
            result.success = False
            result.error = "Could not start Ollama server"
            return result

        # Truncate text if too long (preserve beginning and end)
        max_text_len = 6000
        if len(pdf_text) > max_text_len:
            # Keep first 4000 and last 2000 chars - schedule data often at end
            pdf_text = pdf_text[:4000] + "\n...[truncated]...\n" + pdf_text[-2000:]

        prompt = self.USER_PROMPT_TEMPLATE.format(
            district_name=district_name,
            state=state,
            pdf_text=pdf_text,
        )

        logger.info(f"Extracting times from PDF for {district_name} ({len(pdf_text)} chars)")

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": 0.1,
                    "num_predict": 1000,
                },
            )

            content = response.get("message", {}).get("content", "")
            result.raw_response = content

            data = self._extract_json_from_response(content)

            if not data:
                result.success = False
                result.error = "Could not parse JSON response"
                return result

            # Check for error in response
            if data.get("error"):
                result.success = False
                result.error = data["error"]
                return result

            # Parse schedules
            for item in data.get("schedules", []):
                # Normalize times
                start = self._normalize_time(item.get("start_time", ""))
                end = self._normalize_time(item.get("end_time", ""))

                if not start or not end:
                    logger.warning(f"Could not normalize times: {item}")
                    continue

                schedule = ExtractedSchedule(
                    grade_level=item.get("grade_level", "unknown"),
                    start_time=start,
                    end_time=end,
                    school_name=item.get("school_name"),
                    source_file=source_file,
                    confidence=item.get("confidence", "medium"),
                    raw_text_snippet=item.get("raw_text_snippet", ""),
                    notes=item.get("notes", ""),
                )
                result.schedules.append(schedule)

            if not result.schedules:
                result.success = False
                result.error = "No valid schedules extracted"
            else:
                # Apply Phase 9 validation and enhancement
                result = self._validate_and_enhance_extraction(result)

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            result.success = False
            result.error = str(e)

        return result

    def save_result(
        self,
        result: ExtractionResult,
        output_dir: Path,
        filename: str = "extraction_result.json",
    ) -> Path:
        """
        Save extraction result to JSON file.

        Args:
            result: ExtractionResult to save
            output_dir: Directory to save to
            filename: Output filename

        Returns:
            Path to saved file
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / filename

        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"Saved extraction result to {output_path}")
        return output_path


# Singleton instance for easy access
extraction_service = ExtractionService()
