"""#567 — the district URL import derives its CCD file from NCES_PRIMARY_YEAR and resolves
columns by header name (the 2023-24 pin left website_url a vintage behind the sampler, and
positional indices would silently read the wrong field on a layout shift)."""
import pytest

from infrastructure.scripts.import_district_urls import (
    nces_ccd_lea_file, normalize_url, load_urls_from_csv)
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR


def test_ccd_file_follows_the_primary_vintage():
    # the single vintage authority: bumping NCES_PRIMARY_YEAR re-points this import automatically
    f = nces_ccd_lea_file()
    assert NCES_PRIMARY_YEAR.replace("-", "_") in str(f)
    assert f.name.startswith("ccd_lea_029_")
    assert f.exists()


def test_missing_vintage_dir_fails_loudly_not_with_systemexit():
    # FileNotFoundError, not SystemExit — the epic-#499 lesson (a SystemExit slips past
    # `except Exception` best-effort guards); reused from common/school_sampling._lea_file.
    with pytest.raises(FileNotFoundError, match="ccd_lea_029"):
        nces_ccd_lea_file("1999-00")


def test_normalize_url_blank_forms_are_none():
    # keep-last-known retention depends on blanks never entering the update dict
    for v in ("", "N", "NA", "n/a", "-", None):
        assert normalize_url(v) is None
    assert normalize_url("example.org/") == "https://example.org"


def test_load_urls_from_csv_resolves_by_header_name():
    # real file, real header — the DictReader path reads LEAID/WEBSITE by name, not position
    urls = load_urls_from_csv()
    assert len(urls) > 1000                 # sanity: a real corpus-sized result, not a coding slip
    assert all(u.startswith(("http://", "https://")) for u in urls.values())
