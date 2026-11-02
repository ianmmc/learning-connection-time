"""Read one zip member as a binary stream, whatever its compression: stored, deflate, or Deflate64
(#1036, #1022 T2).

NCES's compression varies by vintage. The 2024-25 `ccd_sch_052` (school membership, a 2.35 GB CSV) is
Deflate64 (zip method 9); the 2023-24 one is ordinary deflate (measured 2026-11-01). Python's
`zipfile` lists a Deflate64 member but refuses to open it. Deflate64 members stream through
`inflate64` here. Their size and CRC-32 are checked against the central directory when the stream
reaches EOF, and any mismatch, corrupt stream or truncation raises `zipfile.BadZipFile`, never a
short read. A reader that stops early gets no CRC check: verification needs the whole member.

Modelled on `public-ed-data-navigator/src/ednav/rawread.py` (`_Deflate64Member` / `open_member`).
"""
from __future__ import annotations

import io
import struct
import zipfile
import zlib
from contextlib import contextmanager

import inflate64

DEFLATE64 = 9          # zip compression method id; zipfile has no constant for it
CHUNK = 1 << 20


class _Deflate64Member(io.RawIOBase):
    """Stream one Deflate64 member; verify size and CRC-32 against the central directory at EOF."""

    def __init__(self, zip_path, info: zipfile.ZipInfo):
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
        self._buf, self._pos, self._crc, self._size, self._done = b"", 0, 0, 0, False

    def readable(self):
        return True

    def _fill(self):
        if not self._left:
            self._done = True
            if self._crc != self._info.CRC or self._size != self._info.file_size:
                raise zipfile.BadZipFile(f"{self._info.filename}: CRC or size mismatch after Deflate64 inflate")
            return
        chunk = self._f.read(min(CHUNK, self._left))
        if not chunk:
            raise zipfile.BadZipFile(f"{self._info.filename}: truncated")
        self._left -= len(chunk)
        try:
            self._buf, self._pos = self._inflater.inflate(chunk), 0
        except Exception as exc:  # inflate64 raises its own error types on corrupt streams
            raise zipfile.BadZipFile(f"{self._info.filename}: {exc}") from exc
        self._crc = zlib.crc32(self._buf, self._crc)
        self._size += len(self._buf)

    def readinto(self, b):
        while self._pos >= len(self._buf) and not self._done:
            self._fill()
        n = min(len(b), len(self._buf) - self._pos)
        b[:n] = memoryview(self._buf)[self._pos:self._pos + n]  # an offset, not a slice: no re-copying
        self._pos += n
        return n

    def close(self):
        self._f.close()
        super().close()


@contextmanager
def open_member(zip_path, member: str):
    """Binary stream of one zip member, whatever its compression (stored, deflate, Deflate64)."""
    with zipfile.ZipFile(zip_path) as z:
        info = z.getinfo(member)
        if info.compress_type == DEFLATE64:
            with io.BufferedReader(_Deflate64Member(zip_path, info), CHUNK) as f:
                yield f
        else:
            with z.open(member) as f:
                yield f
