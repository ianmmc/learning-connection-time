#!/usr/bin/env python3
"""
regex_extract_times.py - Extract bell schedule times using regex

PURPOSE:
    Fallback extraction when Ollama is unavailable. Uses regex patterns
    to find time ranges in PDF text and infer grade levels from context.
    Less accurate than LLM extraction but sufficient for pipeline testing.

USAGE:
    python infrastructure/scripts/enrich/regex_extract_times.py --district 1302280
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

PDF_BASE_DIR = project_root / "data" / "raw" / "bell_schedule_pdfs"

# Time patterns - capture groups for hour, minute, am/pm separately
TIME_PATTERN = r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m\.|p\.m\.)?'

# Grade level indicators
GRADE_PATTERNS = {
    'elementary': [r'elementary', r'primary', r'grades?\s*k', r'\bES\b', r'elem\.?'],
    'middle': [r'middle', r'junior\s*high', r'grades?\s*[6-8]', r'\bMS\b', r'\bJH\b', r'intermediate'],
    'high': [r'high\s*school', r'grades?\s*(9|10|11|12)', r'\bHS\b', r'secondary', r'senior'],
}


def normalize_time(time_str: str) -> str:
    """Convert time string to HH:MM 24-hour format."""
    time_str = time_str.strip()

    # Match hour:minute with optional AM/PM
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m\.|p\.m\.)?', time_str)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = (match.group(3) or '').upper().replace('.', '')

    if ampm:
        if 'PM' in ampm and hour != 12:
            hour += 12
        elif 'AM' in ampm and hour == 12:
            hour = 0
    elif hour < 7:  # Assume afternoon for small hours without AM/PM
        hour += 12

    return f"{hour:02d}:{minute:02d}"


def extract_time_range(text: str) -> list:
    """Extract time ranges from text."""
    ranges = []

    # Pattern for time ranges like "8:00 AM - 3:30 PM" or "8:00AM-3:30PM"
    time_range_pattern = r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)\s*[-–—to]+\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)'

    for match in re.finditer(time_range_pattern, text, re.IGNORECASE):
        start_str = match.group(1)
        end_str = match.group(2)

        start_time = normalize_time(start_str)
        end_time = normalize_time(end_str)

        if not start_time or not end_time:
            continue

        # Get context (100 chars before and after)
        start_pos = max(0, match.start() - 100)
        end_pos = min(len(text), match.end() + 100)
        context = text[start_pos:end_pos]

        ranges.append({
            'start_time': start_time,
            'end_time': end_time,
            'context': context,
            'raw_match': match.group(0),
        })

    # Also look for table format: |School|__7:40___|___2:20___|
    table_pattern = r'\|[^|]+\|[_\s]*(\d{1,2}:\d{2})[_\s]*\|[_\s]*(\d{1,2}:\d{2})[_\s]*\|'

    for match in re.finditer(table_pattern, text):
        start_str = match.group(1)
        end_str = match.group(2)

        # For table format, we need to guess AM/PM based on the hours
        start_hour = int(start_str.split(':')[0])
        end_hour = int(end_str.split(':')[0])

        # Morning start times (5-12) are AM, afternoon end times (1-6) need +12
        if start_hour >= 5 and start_hour <= 11:
            start_time = f"{start_hour:02d}:{start_str.split(':')[1]}"
        else:
            start_time = normalize_time(start_str)

        if end_hour >= 1 and end_hour <= 6:
            end_time = f"{end_hour + 12:02d}:{end_str.split(':')[1]}"
        else:
            end_time = normalize_time(end_str)

        if not start_time or not end_time:
            continue

        # Get context
        start_pos = max(0, match.start() - 50)
        end_pos = min(len(text), match.end() + 50)
        context = text[start_pos:end_pos]

        ranges.append({
            'start_time': start_time,
            'end_time': end_time,
            'context': context,
            'raw_match': match.group(0),
        })

    return ranges


def infer_grade_level(context: str, filename: str) -> str:
    """Infer grade level from context text and filename."""
    combined = (context + ' ' + filename).lower()

    # Count matches for each grade level
    scores = {}
    for grade, patterns in GRADE_PATTERNS.items():
        scores[grade] = sum(1 for p in patterns if re.search(p, combined, re.IGNORECASE))

    # Return highest scoring grade, or unknown
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return 'unknown'


def find_district_dir(district_id: str) -> Path:
    """Find district directory by ID."""
    for state_dir in PDF_BASE_DIR.iterdir():
        if not state_dir.is_dir():
            continue
        for d in state_dir.iterdir():
            if d.is_dir() and d.name.startswith(district_id):
                return d
    return None


def extract_district(district_id: str, district_name: str = None, state: str = None) -> dict:
    """Extract times from all PDF text files for a district."""
    district_dir = find_district_dir(district_id)
    if not district_dir:
        return {'error': f'District directory not found: {district_id}'}

    # Get metadata if not provided
    if not district_name or not state:
        metadata_file = district_dir / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file) as f:
                meta = json.load(f)
                district_name = district_name or meta.get('district_name', 'Unknown')
                state = state or meta.get('state', 'XX')
        else:
            # Parse from directory name
            parts = district_dir.name.split('_', 1)
            district_name = district_name or (parts[1].replace('_', ' ') if len(parts) > 1 else 'Unknown')
            state = state or district_dir.parent.name

    # Find all text files
    txt_files = list(district_dir.glob('active/**/*.txt')) + list(district_dir.glob('active/*.txt'))

    if not txt_files:
        return {'error': 'No text files found'}

    all_schedules = []
    seen_times = set()  # Deduplicate

    for txt_file in txt_files:
        with open(txt_file, 'r', errors='ignore') as f:
            text = f.read()

        time_ranges = extract_time_range(text)

        for tr in time_ranges:
            # Skip duplicates
            time_key = (tr['start_time'], tr['end_time'])
            if time_key in seen_times:
                continue

            # Skip unreasonable times (school day < 4 hours or > 10 hours)
            start_h, start_m = map(int, tr['start_time'].split(':'))
            end_h, end_m = map(int, tr['end_time'].split(':'))
            duration_mins = (end_h * 60 + end_m) - (start_h * 60 + start_m)

            if duration_mins < 240 or duration_mins > 600:
                continue

            grade = infer_grade_level(tr['context'], txt_file.name)

            all_schedules.append({
                'grade_level': grade,
                'start_time': tr['start_time'],
                'end_time': tr['end_time'],
                'school_name': None,
                'source_file': txt_file.name,
                'confidence': 'medium',
                'raw_text_snippet': tr['raw_match'],
                'notes': f'Regex extraction from {txt_file.name}',
            })
            seen_times.add(time_key)

    # If we have multiple schedules with unknown grade, try to assign reasonably
    unknowns = [s for s in all_schedules if s['grade_level'] == 'unknown']
    if len(unknowns) == len(all_schedules) and len(all_schedules) >= 1:
        # Just pick the first one and call it elementary (most common)
        all_schedules = all_schedules[:1]
        all_schedules[0]['grade_level'] = 'elementary'
        all_schedules[0]['notes'] += ' (grade level assumed)'

    # Deduplicate by grade level - keep first (most common) schedule per grade
    # This is needed because the database has a unique constraint on (district_id, year, grade_level)
    seen_grades = set()
    deduped_schedules = []
    for s in all_schedules:
        if s['grade_level'] not in seen_grades and s['grade_level'] != 'unknown':
            deduped_schedules.append(s)
            seen_grades.add(s['grade_level'])

    # If we only have unknowns, skip them (will be filtered out in import anyway)
    all_schedules = deduped_schedules if deduped_schedules else []

    result = {
        'district_id': district_id,
        'district_name': district_name,
        'state': state,
        'extraction_date': datetime.utcnow().isoformat(),
        'extractor': 'regex',
        'schedules': all_schedules,
        'success': len(all_schedules) > 0,
        'error': None if all_schedules else 'No time ranges found',
        'raw_response': None,
    }

    # Save to file
    output_file = district_dir / 'extraction_result.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"Extracted {len(all_schedules)} schedule(s) for {district_name}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--district', required=True, help='District ID to extract')
    parser.add_argument('--name', help='District name')
    parser.add_argument('--state', help='State code')
    args = parser.parse_args()

    result = extract_district(args.district, args.name, args.state)

    if result.get('error'):
        print(f"Error: {result['error']}")
        return 1

    print(f"Saved to extraction_result.json")
    for s in result['schedules']:
        print(f"  {s['grade_level']}: {s['start_time']} - {s['end_time']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
