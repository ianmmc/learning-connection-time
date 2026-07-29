"""#567 — the district URL import derives its CCD file from NCES_PRIMARY_YEAR and resolves
columns by header name (the 2023-24 pin left website_url a vintage behind the sampler, and
positional indices would silently read the wrong field on a layout shift).

HERMETIC on purpose: data/raw/ is gitignored, so CI has no CCD file — every test here builds its
own vintage dir/CSV under tmp_path and repoints the module's `project_root`. (The first version of
this file opened the real corpus CSV and failed CI collection — the exact fragility it now avoids.)
"""
import pytest

from infrastructure.scripts import import_district_urls as IDU
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR


def _vintage(tmp_path, year_dir, filenames):
    d = tmp_path / "data/raw/federal/nces-ccd" / year_dir
    d.mkdir(parents=True)
    for fn in filenames:
        (d / fn).touch()
    return d


def test_ccd_file_follows_the_primary_vintage(tmp_path, monkeypatch):
    # the single vintage authority: bumping NCES_PRIMARY_YEAR re-points this import automatically
    vdir = _vintage(tmp_path, NCES_PRIMARY_YEAR.replace("-", "_"), ["ccd_lea_029_test_w_1a.csv"])
    monkeypatch.setattr(IDU, "project_root", tmp_path)
    assert IDU.nces_ccd_lea_file() == vdir / "ccd_lea_029_test_w_1a.csv"


def test_missing_or_ambiguous_vintage_fails_loudly_not_with_systemexit(tmp_path, monkeypatch):
    # FileNotFoundError, not SystemExit — the epic-#499 lesson (a SystemExit slips past
    # `except Exception` best-effort guards; same contract as common/school_sampling._lea_file).
    monkeypatch.setattr(IDU, "project_root", tmp_path)
    with pytest.raises(FileNotFoundError, match="ccd_lea_029"):
        IDU.nces_ccd_lea_file()                                   # vintage dir absent entirely
    _vintage(tmp_path, NCES_PRIMARY_YEAR.replace("-", "_"),
             ["ccd_lea_029_a.csv", "ccd_lea_029_b.csv"])
    with pytest.raises(FileNotFoundError, match="ccd_lea_029"):
        IDU.nces_ccd_lea_file()                                   # two candidates: refuse to guess


def test_normalize_url_blank_forms_are_none():
    # keep-last-known retention depends on blanks never entering the update dict
    for v in ("", "N", "NA", "n/a", "-", None):
        assert IDU.normalize_url(v) is None
    assert IDU.normalize_url("example.org/") == "https://example.org"


def test_load_urls_from_csv_resolves_by_header_name(tmp_path, monkeypatch):
    """Columns are found by HEADER NAME (csv.DictReader), not position — an inserted column must
    not shift what gets read, and a blank/placeholder WEBSITE must not enter the dict."""
    vdir = _vintage(tmp_path, NCES_PRIMARY_YEAR.replace("-", "_"), [])
    (vdir / "ccd_lea_029_fixture.csv").write_text(
        "SCHOOL_YEAR,LEAID,LEA_NAME,SURVYEAR,WEBSITE\n"          # WEBSITE deliberately NOT at the
        "2024-2025,100005,Alpha,2024,www.alpha.k12.us\n"          # legacy positional offset (24)
        "2024-2025,100006,Beta,2024,\n"                           # blank -> excluded
        "2024-2025,100007,Gamma,2024,N\n"                         # placeholder -> excluded
        "2024-2025,100008,Delta,2024,http://delta.k12.us/\n")
    monkeypatch.setattr(IDU, "project_root", tmp_path)
    assert IDU.load_urls_from_csv() == {
        "0100005": "https://www.alpha.k12.us",                    # LEAID zero-padded to 7 digits
        "0100008": "http://delta.k12.us",                         # protocol kept, trailing / dropped
    }
