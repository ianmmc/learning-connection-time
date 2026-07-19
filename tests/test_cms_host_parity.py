"""Cross-language parity pin for the dot-boundary host-suffix matching RULE (#34/#416 review).

The predicate is implemented twice — Python's `_host_matches` (common/discover.py) and JS's
`hostMatches` (infrastructure/scraper/capture_discovery.mjs) — over the shared cms_hosts.json
data (REQ-089 unified the data, not the algorithm). This suite and its JS twin
(capture_fingerprint.test.mjs) both consume the same golden-vector fixture, so a future rule
change in one language fails the other's suite until both are updated — closing the drift
class that let #34's Python fix ship 16 days before #416's identical JS fix.
"""
import json

import pytest

from infrastructure.acquisition.common import discover as DISC
from infrastructure.acquisition.common import paths

FIXTURE = paths.REPO_ROOT / "infrastructure" / "acquisition" / "common" / "config" / "cms_host_match_cases.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[f"{c['host'] or '<empty>'}~{c['suffix']}" for c in CASES])
def test_host_matches_agrees_with_golden_vectors(case):
    assert DISC._host_matches(case["host"], case["suffix"]) is case["match"], case["why"]
