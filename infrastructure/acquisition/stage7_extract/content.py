"""Representation content resolution for Stage 7 (REQ-117).

Text reps → the file's text (the council reads it inline). Image reps → a base64 `data:` URL for
the vision council's `image_url` message (`prompts.user_message(kind="image")`). Optional
`.webp`→`.png` normalization (Pillow) for consistency — vision models accept PNG/JPEG most
reliably, and batch_00000 carries at least one `.webp` flier (Cleveland). Pure; no network/DB.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp"}


def image_data_url(path, *, convert_webp_to_png: bool = True) -> str:
    """Read an image file into a `data:<mime>;base64,...` URL. `.webp` is transcoded to PNG by
    default (falling back to sending the webp bytes if Pillow can't load it)."""
    p = Path(path)
    ext = p.suffix.lower()
    data = p.read_bytes()
    mime = _MIME.get(ext, "application/octet-stream")
    if ext == ".webp" and convert_webp_to_png:
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            data, mime = buf.getvalue(), "image/png"
        except Exception:
            pass  # Pillow missing / undecodable → send the original webp bytes as-is
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def is_image_kind(kind: str) -> bool:
    return kind == "image"
