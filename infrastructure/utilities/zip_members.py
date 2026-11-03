"""Read one zip member as a binary stream, whatever its compression: stored, deflate, or Deflate64
(#1036, #1022 T2).

NCES's compression varies by vintage. The 2024-25 `ccd_sch_052` (school membership, a 2.35 GB CSV) is
Deflate64 (zip method 9); the 2023-24 one is ordinary deflate (measured 2026-11-01). Python's
`zipfile` lists a Deflate64 member but refuses to open it. Deflate64 members stream through
`inflate64` here.

The contract, the same for every compression (#1056): `open_member` yields an `io.BufferedReader`
that is readable and NOT seekable (no `seek`/`tell`, no `.name`). A second pass reopens the member.

Verification (#1054): a Deflate64 member's size and CRC-32 are checked against the central directory
on the read that consumes its LAST compressed byte, the same moment `zipfile` checks a deflate
member, so a bounded `read(file_size)`, a `readline()` loop over exactly the member's lines and a
`readinto` of exactly its size all raise `zipfile.BadZipFile`. A failure is latched: every later read
re-raises it rather than reporting a clean EOF. A reader that stops early gets no check; verification
needs the whole member.

Memory (#1057, #1058): inflate64 1.0.4 keeps a buffer export on every input object it is handed, for
longer than the Inflater lives (measured: +64 MB per pass over the real 2024-25 member with fresh
`bytes` chunks; a resize of an input bytearray raises BufferError even after the Inflater is
collected). So the reader owns ONE fixed 64 KiB input buffer, refills it with `readinto` and passes a
`memoryview` slice (measured: +0.01 MB over 20 passes). That buffer is leaked once per reader, and
must never be resized. Input slices are small so that one `inflate()` call's output stays small on
real data (~2.4 MB per 64 KiB at the real member's ~37:1). inflate64 has no `max_length`, so a
hostile member can still expand one 64 KiB slice to ~1.7 GB; a MemoryError is passed through, never
relabelled as corruption.

Modelled on `public-ed-data-navigator/src/ednav/rawread.py` (`_Deflate64Member` / `open_member`).
"""
from __future__ import annotations

import io
import os
import struct
import zipfile
import zlib
from contextlib import contextmanager

import inflate64

DEFLATE64 = 9          # zip compression method id; zipfile has no constant for it
INPUT_SLICE = 1 << 16  # compressed bytes per inflate() call (the reusable input buffer's size)
BUFFER = 1 << 20       # io.BufferedReader buffer


class _Deflate64Member(io.RawIOBase):
    """Stream one Deflate64 member; verify size and CRC-32 on the slice that consumes the last byte."""

    def __init__(self, zip_path, info: zipfile.ZipInfo):
        self._f = None                        # a failed open must leave close() (the finalizer) safe (#1087)
        self._f = open(zip_path, "rb")
        try:
            self._f.seek(info.header_offset)
            local = self._f.read(30)
            if local[:4] != b"PK\x03\x04":
                raise zipfile.BadZipFile(f"{info.filename}: bad local header")
            name_len, extra_len = struct.unpack("<HH", local[26:30])
            self._f.seek(info.header_offset + 30 + name_len + extra_len)
        except BaseException:
            self._f.close()
            raise
        self._info, self._left = info, info.compress_size
        self._inflater = inflate64.Inflater()
        self._in = bytearray(INPUT_SLICE)      # the one input buffer (see the module docstring)
        self._in_view = memoryview(self._in)
        self._buf, self._pos, self._crc, self._size = b"", 0, 0, 0
        self._done, self._error = False, None

    def readable(self):
        return True

    def _fail(self, message: str, cause: BaseException | None = None):
        self._error = zipfile.BadZipFile(f"{self._info.filename}: {message}")
        self._buf, self._pos = b"", 0
        raise self._error from cause

    def _fill(self):
        if not self._left:                    # a zero-length member: verify on the first call
            self._verify()
            return
        n = self._f.readinto(self._in_view[:min(INPUT_SLICE, self._left)])
        if not n:
            self._fail("truncated")
        self._left -= n
        self._buf = b""                       # release the previous output before inflating more
        try:
            self._buf, self._pos = self._inflater.inflate(self._in_view[:n]), 0
        except MemoryError:
            raise
        except Exception as exc:              # inflate64 raises its own error types on corrupt streams
            self._fail(str(exc), exc)
        self._crc = zlib.crc32(self._buf, self._crc)
        self._size += len(self._buf)
        if not self._left:
            self._verify()

    def _verify(self):
        """Called once the last compressed byte is consumed: the whole member must be present and
        match the central directory's CRC-32 and size (acceptance A2)."""
        if not self._inflater.eof:
            self._fail("compressed stream ended before the Deflate64 end-of-block")
        if self._crc != self._info.CRC or self._size != self._info.file_size:
            self._fail("CRC or size mismatch after Deflate64 inflate")
        self._done = True

    def readinto(self, b):
        if self._error is not None:
            raise self._error
        while self._pos >= len(self._buf) and not self._done:
            self._fill()
        n = min(len(b), len(self._buf) - self._pos)
        b[:n] = memoryview(self._buf)[self._pos:self._pos + n]  # an offset, not a slice: no re-copying
        self._pos += n
        return n

    def close(self):
        if self._f is not None:
            self._f.close()
        super().close()


class _ZipExtRaw(io.RawIOBase):
    """A stored/deflate member as a non-seekable raw stream, so every compression yields the same
    file-object contract (#1056). zipfile does the CRC check on the read that consumes the last byte;
    a corrupt deflate stream, though, surfaces from zipfile as zlib's own `zlib.error` BEFORE that
    check — relabelled here as `BadZipFile` and latched, so the contract holds for every compression
    (#1087: 3 of 30 single-byte flips of a real deflate member raised zlib.error)."""

    def __init__(self, ext: zipfile.ZipExtFile):
        self._ext, self._error = ext, None

    def readable(self):
        return True

    def readinto(self, b):
        if self._error is not None:
            raise self._error
        try:
            data = self._ext.read(len(b))
        except zlib.error as exc:
            self._error = zipfile.BadZipFile(f"{self._ext.name}: corrupt deflate stream ({exc})")
            raise self._error from exc
        n = len(data)
        b[:n] = data
        return n

    def close(self):
        self._ext.close()
        super().close()


@contextmanager
def open_member(zip_path, member: str):
    """Binary stream of one zip member, whatever its compression: an `io.BufferedReader`, readable
    and not seekable. Raises `zipfile.BadZipFile` on a corrupt, mismatched or truncated member.
    `zip_path` is a filesystem path, never a file object: a Deflate64 member is re-opened by path,
    so anything else is refused here, before any file is opened (#1087)."""
    if not isinstance(zip_path, (str, bytes, os.PathLike)):
        raise TypeError(f"open_member needs a filesystem path, got {type(zip_path).__name__} "
                        f"(a Deflate64 member is re-opened by path)")
    with zipfile.ZipFile(zip_path) as z:
        info = z.getinfo(member)
        if info.compress_type == DEFLATE64:
            raw = _Deflate64Member(zip_path, info)
        else:
            raw = _ZipExtRaw(z.open(member))
        with io.BufferedReader(raw, BUFFER) as f:
            yield f
