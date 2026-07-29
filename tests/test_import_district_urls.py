"""#567 — the district URL import derives its CCD file from NCES_PRIMARY_YEAR and resolves
columns by header name (the 2023-24 pin left website_url a vintage behind the sampler, and
positional indices would silently read the wrong field on a layout shift)."""
import pytest

from infrastructure.scripts.import_district_urls import (
    NCES_CCD_FILE, nces_ccd_lea_file, normalize_url, resolve_columns)
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR


def test_ccd_file_follows_the_primary_vintage():
    # the single vintage authority: bumping NCES_PRIMARY_YEAR re-points this import automatically
    assert NCES_PRIMARY_YEAR.replace("-", "_") in str(NCES_CCD_FILE)
    assert NCES_CCD_FILE.name.startswith("ccd_lea_029_")
    assert NCES_CCD_FILE.exists()


def test_missing_vintage_dir_fails_loudly():
    with pytest.raises(SystemExit, match="expected exactly one"):
        nces_ccd_lea_file("1999-00")


def test_resolve_columns_by_header_name():
    cols = resolve_columns(["X", "leaid", "Website", "GSLO", "GSHI"])
    assert cols == {"LEAID": 1, "WEBSITE": 2, "GSLO": 3, "GSHI": 4}


def test_resolve_columns_refuses_a_changed_layout():
    with pytest.raises(SystemExit, match="missing"):
        resolve_columns(["LEAID", "WEB_SITE"])          # renamed column must not be guessed


def test_normalize_url_blank_forms_are_none():
    # keep-last-known retention depends on blanks never entering the update dict
    for v in ("", "N", "NA", "n/a", "-", None):
        assert normalize_url(v) is None
    assert normalize_url("example.org/") == "https://example.org"
