"""Stage 7 image content resolution (REQ-117) — pure, no network. Builds tiny images in a tmp dir."""
import base64
import io

from infrastructure.acquisition.stage7_extract import content as C


def _png(path):
    from PIL import Image
    Image.new("RGB", (2, 2), (255, 0, 0)).save(path, format="PNG")


def test_png_data_url(tmp_path):
    p = tmp_path / "raster_p-1.png"
    _png(p)
    url = C.image_data_url(p)
    assert url.startswith("data:image/png;base64,")
    # decodes back to real bytes
    b64 = url.split(",", 1)[1]
    assert base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


def test_webp_converted_to_png(tmp_path):
    from PIL import Image
    p = tmp_path / "flier.webp"
    Image.new("RGB", (2, 2), (0, 128, 255)).save(p, format="WEBP")
    url = C.image_data_url(p)          # convert_webp_to_png=True by default
    assert url.startswith("data:image/png;base64,")


def test_webp_left_as_is_when_not_converting(tmp_path):
    from PIL import Image
    p = tmp_path / "flier.webp"
    Image.new("RGB", (2, 2), (0, 128, 255)).save(p, format="WEBP")
    url = C.image_data_url(p, convert_webp_to_png=False)
    assert url.startswith("data:image/webp;base64,")


def test_jpeg_passthrough(tmp_path):
    from PIL import Image
    p = tmp_path / "original.jpeg"
    Image.new("RGB", (2, 2), (10, 20, 30)).save(p, format="JPEG")
    url = C.image_data_url(p)
    assert url.startswith("data:image/jpeg;base64,")


def test_is_image_kind():
    assert C.is_image_kind("image") is True
    assert C.is_image_kind("text") is False
