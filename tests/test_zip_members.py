"""#1036 (#1022 T2): Deflate64 zip members stream through inflate64, and every failure is loud.

The Deflate64 archives here are built by hand: compressed with `inflate64.Deflater`, then wrapped in
local header + central directory + EOCD records, because `zipfile` cannot write method 9. Acceptance
A2 (reader half): a CRC or size mismatch, a corrupt stream, or a truncated member raises
`zipfile.BadZipFile`, never a short read.
"""
import io
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
    with pytest.raises(zipfile.BadZipFile, match="truncated"):
        with io.BufferedReader(ZM._Deflate64Member(z, info)) as f:
            f.read()


def test_a_physically_truncated_archive_fails_through_open_member(tmp_path):
    """#1067: the end-to-end path. Cutting the file short loses the central directory, so zipfile
    itself refuses; whichever layer raises, the caller sees BadZipFile and never a short read."""
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    cut = tmp_path / "cut.zip"
    cut.write_bytes(z.read_bytes()[: z.stat().st_size // 2])
    with pytest.raises(zipfile.BadZipFile):
        _read_all(cut, "m.csv")


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


# ---------------------------------------------------------------- #1054: verification is not EOF-only

def _bad_crc_zip(tmp_path):
    return _build_zip(tmp_path / "bad.zip", "m.csv", PAYLOAD, crc=zlib.crc32(PAYLOAD) ^ 1)


def test_a_bounded_read_of_exactly_the_member_size_raises(tmp_path):
    """#1054: `read(file_size)` consumed every byte and returned them unverified; the deflate branch
    raises on the read that consumes the last byte. Deflate64 must match."""
    z = _bad_crc_zip(tmp_path)
    with pytest.raises(zipfile.BadZipFile, match="CRC or size mismatch"):
        with ZM.open_member(z, "m.csv") as f:
            f.read(len(PAYLOAD))


def test_a_readline_loop_over_exactly_the_members_lines_raises(tmp_path):
    z = _bad_crc_zip(tmp_path)
    n_lines = PAYLOAD.count(b"\n")
    with pytest.raises(zipfile.BadZipFile, match="CRC or size mismatch"):
        with ZM.open_member(z, "m.csv") as f:
            for _ in range(n_lines):
                f.readline()


def test_readinto_of_exactly_the_member_size_raises(tmp_path):
    z = _bad_crc_zip(tmp_path)
    with pytest.raises(zipfile.BadZipFile, match="CRC or size mismatch"):
        with ZM.open_member(z, "m.csv") as f:
            f.readinto(bytearray(len(PAYLOAD)))


def test_the_failure_is_latched_not_a_clean_eof_afterwards(tmp_path):
    """#1054: after the error was caught, every later read() returned b'' as a clean EOF."""
    z = _bad_crc_zip(tmp_path)
    with ZM.open_member(z, "m.csv") as f:
        with pytest.raises(zipfile.BadZipFile):
            f.read()
        with pytest.raises(zipfile.BadZipFile):
            f.read()
        with pytest.raises(zipfile.BadZipFile):
            f.read(1)


def test_deflate_and_deflate64_behave_the_same_on_a_bad_crc(tmp_path):
    """The vintage-dependence #1054 described: one consumer, both compressions, same outcome."""
    d64 = _bad_crc_zip(tmp_path)
    d8 = tmp_path / "d8.zip"
    with zipfile.ZipFile(d8, "w") as zf:
        zf.writestr("m.csv", PAYLOAD, compress_type=zipfile.ZIP_DEFLATED)
    raw = d8.read_bytes()
    good = zlib.crc32(PAYLOAD).to_bytes(4, "little")
    assert raw.count(good) == 2                       # local header + central directory
    d8.write_bytes(raw.replace(good, (zlib.crc32(PAYLOAD) ^ 1).to_bytes(4, "little")))

    def consume(path):
        with ZM.open_member(path, "m.csv") as f:
            return f.read(len(PAYLOAD))
    for path in (d64, d8):
        with pytest.raises(zipfile.BadZipFile):
            consume(path)


# ---------------------------------------------------------------- #1056: one file-object contract

def _both(tmp_path):
    d64 = _build_zip(tmp_path / "d64.zip", "m.csv", PAYLOAD)
    d8 = tmp_path / "d8.zip"
    with zipfile.ZipFile(d8, "w") as zf:
        zf.writestr("m.csv", PAYLOAD, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("s.csv", PAYLOAD, compress_type=zipfile.ZIP_STORED)
    return [(d64, "m.csv"), (d8, "m.csv"), (d8, "s.csv")]


def test_open_member_yields_the_same_type_and_capabilities_for_every_compression(tmp_path):
    seen = set()
    for path, member in _both(tmp_path):
        with ZM.open_member(path, member) as f:
            seen.add(type(f))
            assert f.readable() and not f.seekable()
            with pytest.raises(io.UnsupportedOperation):
                f.seek(0)
            with pytest.raises(io.UnsupportedOperation):
                f.tell()
            assert not hasattr(f, "name")
    assert len(seen) == 1, seen


def test_one_consumer_gets_identical_results_on_every_compression(tmp_path):
    def consume(path, member):
        with ZM.open_member(path, member) as f:
            header = f.readline()
            rest = f.read()
            return header, zlib.crc32(rest), len(rest)
    results = {consume(p, m) for p, m in _both(tmp_path)}
    assert len(results) == 1


# ---------------------------------------------------------------- #1057 / #1058: memory

def test_repeated_passes_do_not_retain_the_compressed_input(tmp_path):
    """#1058: inflate64 keeps a buffer export on every input object it is handed, past the Inflater's
    life. With fresh `bytes` chunks each pass retained the whole compressed member (+64 MB per pass
    on the real file). The reader's one reusable input buffer must hold growth near zero."""
    import gc
    import tracemalloc
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    comp = len(_deflate64(PAYLOAD))
    assert comp > 500_000                       # a leak of 5 passes would be well over the bound
    tracemalloc.start()
    try:
        _read_all(z, "m.csv")                   # warm up: the first pass allocates module/pool state
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(5):
            _read_all(z, "m.csv")
            gc.collect()
        growth = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()
    assert growth < comp, f"grew {growth:,} B over 5 passes of a {comp:,} B member (leak shape: {5 * comp:,})"


def test_a_memory_error_is_not_relabelled_as_corruption(tmp_path, monkeypatch):
    """#1057: `except Exception` wrapped MemoryError as BadZipFile, which reads as data corruption."""
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)

    class Boom:
        eof = False

        def inflate(self, data):
            raise MemoryError("simulated")
    monkeypatch.setattr(ZM.inflate64, "Inflater", Boom)
    with pytest.raises(MemoryError):
        _read_all(z, "m.csv")


def test_input_is_fed_in_bounded_slices(tmp_path, monkeypatch):
    """#1057: one inflate() call sees at most INPUT_SLICE compressed bytes, so its output is bounded
    on real data (the hostile-ratio residual is documented, not hidden)."""
    z = _build_zip(tmp_path / "a.zip", "m.csv", PAYLOAD)
    seen = []
    real = ZM.inflate64.Inflater

    class Spy:
        def __init__(self):
            self._i = real()

        @property
        def eof(self):
            return self._i.eof

        def inflate(self, data):
            seen.append(len(data))
            return self._i.inflate(data)
    monkeypatch.setattr(ZM.inflate64, "Inflater", Spy)
    assert _read_all(z, "m.csv") == PAYLOAD
    assert seen and max(seen) <= ZM.INPUT_SLICE and sum(seen) == len(_deflate64(PAYLOAD))


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
