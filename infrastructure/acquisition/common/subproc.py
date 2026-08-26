"""Shared subprocess-output helpers (one home, REQ-182).

Born in #916/#924 (Stage 3) and promoted here when #927 found the same trap one layer over in
Stage 2: `subprocess.run` populates `TimeoutExpired.stdout` as **bytes even under `text=True`** —
the decoding happens in the normal return path, which a timeout never reaches — and as None when
nothing was captured (`stderr` is None on POSIX). Handing bytes to a str parser silently never
matches, so output that IS there reads as absent: the #916 failure shape reproduced inside its own
salvage path.
"""


def stream_to_text(stream) -> str:
    """Normalize a subprocess output stream (str | bytes | None) to str."""
    if stream is None:
        return ""
    return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else stream
