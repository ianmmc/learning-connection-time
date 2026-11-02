"""#1036 (#1022 T2): Deflate64 zip members stream through inflate64, and every failure is loud.

The Deflate64 archives here are built by hand: compressed with `inflate64.Deflater`, then wrapped in
local header + central directory + EOCD records, because `zipfile` cannot write method 9. Acceptance
A2 (reader half): a CRC or size mismatch, a corrupt stream, or a truncated member raises
`zipfile.BadZipFile`, never a short read.
"""
import struct
import zipfile
import zlib
from pathlib import Path

import inflate64
import pytest

from infrastructure.utilities import zip_members as ZM

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = b"".join(b"NCESSCH,%06d,Grade %d,%d\n" % (i, i % 13, i * 7 % 997) for i in range(60_000))


def _deflate64(data: bytes) -> bytes:
    d = inflate64.Deflater()
    return d.deflate(data) + d.flush()


def _build_zip(path: Path, name: str, data: bytes, *, crc=None, size=None, mutate=None) -> Path:
    comp = _deflate64(data)
    if mutate:
        comp = mutate(comp)
    crc = zlib.crc32(data) if crc is None else crc
    size = len(data) if size is None else size
    n = name.encode()
    local = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 21, 0, ZM.DEFLATE64, 0, 0x21,
                        crc, len(comp), size, len(n), 0) + n
    central = struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 21, 21, 0, ZM.DEFLATE64, 0, 0x21,
                          crc, len(comp), size, len(n), 0, 0, 0, 0, 0, 0) + n
    cd_offset = len(local) + len(comp)
    eocd = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 1, 1, len(central), cd_offset, 0)
    path.write_bytes(local + comp + central + eocd)
    return path


def _read_all(path, name):
    with ZM.open_member(path, name) as f:
        return f.read()


def test_zipfile_itself_refuses_deflate64(tmp_path):
    """The premise: without this module the member cannot be read at all."""
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    with zipfile.ZipFile(z) as zf:
        assert zf.getinfo("m.csv").compress_type == ZM.DEFLATE64
        with pytest.raises(NotImplementedError):
            zf.open("m.csv")


def test_deflate64_member_round_trips(tmp_path):
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    assert len(_deflate64(PAYLOAD)) < len(PAYLOAD)          # it really is compressed
    assert _read_all(z, "m.csv") == PAYLOAD


def test_streams_line_by_line(tmp_path):
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    with ZM.open_member(z, "m.csv") as f:
        lines = list(f)
    assert len(lines) == 60_000 and lines[1] == b"NCESSCH,000001,Grade 1,7\n"


def test_wrong_crc_fails_at_eof(tmp_path):
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD, crc=zlib.crc32(PAYLOAD) ^ 1)
    with pytest.raises(zipfile.BadZipFile, match="CRC or size mismatch"):
        _read_all(z, "m.csv")


def test_wrong_size_fails_at_eof(tmp_path):
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD, size=len(PAYLOAD) + 1)
    with pytest.raises(zipfile.BadZipFile, match="CRC or size mismatch"):
        _read_all(z, "m.csv")


def test_a_corrupted_byte_fails(tmp_path):
    def flip(comp):
        mid = len(comp) // 2
        return comp[:mid] + bytes([comp[mid] ^ 0xFF]) + comp[mid + 1:]
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD, mutate=flip)
    with pytest.raises(zipfile.BadZipFile):
        _read_all(z, "m.csv")


def test_a_truncated_member_fails(tmp_path):
    """The central directory promises more compressed bytes than the file holds."""
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    with zipfile.ZipFile(z) as zf:
        info = zf.getinfo("m.csv")
    info.compress_size += 10 * z.stat().st_size
    with pytest.raises(zipfile.BadZipFile, match="truncated|CRC|invalid|corrupt|error"):
        with __import__("io").BufferedReader(ZM._Deflate64Member(z, info)) as f:
            f.read()


def test_stored_and_deflated_members_pass_through_zipfile(tmp_path):
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("stored.csv", PAYLOAD, compress_type=zipfile.ZIP_STORED)
        zf.writestr("deflated.csv", PAYLOAD, compress_type=zipfile.ZIP_DEFLATED)
    assert _read_all(z, "stored.csv") == PAYLOAD
    assert _read_all(z, "deflated.csv") == PAYLOAD


def test_unknown_member_raises_key_error(tmp_path):
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    with pytest.raises(KeyError):
        _read_all(z, "nope.csv")


_CCD = REPO / "data/raw/federal/nces-ccd"
_REAL = {  # measured 2026-11-01: NCES's compression varies by vintage
    ZM.DEFLATE64: _CCD / "2024_25/ccd_sch_052_2425_l_1a_073025.zip",
    zipfile.ZIP_DEFLATED: _CCD / "2023_24/ccd_sch_052_2324_l_1a_073124.zip",
}


@pytest.mark.parametrize("method", sorted(_REAL), ids=["deflate", "deflate64"])
def test_real_ccd_school_membership_header(method):
    """Smoke on the real files: the header line reads from both vintages, Deflate64 and deflate.
    A partial read skips the CRC; the full-member check runs in the importer (#1039)."""
    path = _REAL[method]
    if not path.exists():
        pytest.skip(f"{path.name} not on disk")
    with zipfile.ZipFile(path) as zf:
        member = next(n for n in zf.namelist() if n.endswith(".csv"))
        assert zf.getinfo(member).compress_type == method
    with ZM.open_member(path, member) as f:
        header = f.readline().decode("latin-1")
    assert header.startswith("SCHOOL_YEAR,") and "NCESSCH" in header and "STUDENT_COUNT" in header
