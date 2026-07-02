"""#40: NCES file lookups in common/school_sampling.py -- the fast-path filename slice for
'YYYY_YY' years (was year[7:9] == '', so the glob fallback always ran) and a clear
FileNotFoundError (not a bare StopIteration) when neither the fast path nor the glob hits."""
import pytest

from infrastructure.acquisition.common import school_sampling as SS


@pytest.fixture
def nces(tmp_path, monkeypatch):
    monkeypatch.setattr(SS, "_NCES_DIR", tmp_path)
    return tmp_path


def test_sch_file_fast_path_uses_the_yyyy_yy_slice(nces):
    d = nces / "2024_25"
    d.mkdir()
    fast = d / "ccd_sch_029_2425_w_1a_073025.csv"   # year[2:4]+year[5:7] == '2425'
    fast.write_text("x")
    # what the old year[7:9]=='' slice would have looked for -- must NOT be preferred
    (d / "ccd_sch_029_24_w_1a_073025.csv").write_text("x")
    assert SS._sch_file("2024_25") == fast


def test_sch_file_glob_fallback_still_works(nces):
    d = nces / "2023_24"
    d.mkdir()
    only = d / "ccd_sch_029_2324_w_1a_073124.csv"   # different vintage suffix -> fast path misses
    only.write_text("x")
    assert SS._sch_file("2023_24") == only


def test_sch_file_missing_raises_clear_error_not_stopiteration(nces):
    (nces / "2023_24").mkdir()   # empty dir: fast path AND glob both miss
    with pytest.raises(FileNotFoundError, match=r"ccd_sch_029.*2023_24"):
        SS._sch_file("2023_24")


def test_virtual_file_same_slice_and_error(nces):
    d = nces / "2024_25"
    d.mkdir()
    fast = d / "ccd_sch_129_2425_w_1a_073025.csv"
    fast.write_text("x")
    assert SS._virtual_file("2024_25") == fast
    (nces / "2023_24").mkdir()
    with pytest.raises(FileNotFoundError, match="ccd_sch_129"):
        SS._virtual_file("2023_24")
