"""REQ-088 / REQ-089 — the config-as-data layer, with CMS_HOSTS as the first knob and the
single source of truth shared by discover.py and capture_discovery.mjs (no more hand-syncing)."""
import sys
from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "infrastructure" / "acquisition" / "common"
sys.path.insert(0, str(COMMON))

import config_loader  # noqa: E402
import paths  # noqa: E402

# The exact list (and order) that was hardcoded in BOTH files before the migration — the
# behavior-preserving baseline for "resolves identically."
ORIGINAL_CMS_HOSTS = [
    "finalsite.net", "echalksites.com", "sites.google.com", "drive.google.com",
    "docs.google.com", "schoolwires.net", "schoolwires.com", "blackboard.com",
    "sharpschool.com", "apptegy.net", "thrillshare.com", "educationalnetworks.net",
]


def test_loader_values_match_the_original_hardcoded_list():
    assert config_loader.values("cms_hosts") == ORIGINAL_CMS_HOSTS


def test_discover_cms_hosts_unchanged_after_migration():
    import discover
    assert list(discover.CMS_HOSTS) == ORIGINAL_CMS_HOSTS


def test_every_entry_carries_full_provenance():
    doc = config_loader.load("cms_hosts")
    for e in doc["entries"]:
        for field in config_loader.PROVENANCE_FIELDS:
            assert field in e, f"{e.get('value')!r} missing provenance field {field!r}"
    assert "governance" in doc and "description" in doc


def test_config_lives_under_config_dir_near_code_not_under_data_root():
    kp = config_loader.knob_path("cms_hosts")
    assert kp.exists()
    assert str(kp).startswith(str(paths.CONFIG_DIR))
    assert not str(paths.CONFIG_DIR).startswith(str(paths.DATA_ROOT))
