from __future__ import annotations

import io
import warnings

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombWarning, DecompressionBombError

_ALLOWED_FORMATS = frozenset({"jpeg", "png", "webp", "gif"})


def process_image(
    data: bytes,
    max_px: int,
    max_size_bytes: int = 5_000_000,
    output_format: str = "WEBP",
) -> bytes:
    if len(data) > max_size_bytes:
        raise ValueError(f"Image exceeds {max_size_bytes} bytes")

    image_format = _detect_image_format(data)
    if image_format not in _ALLOWED_FORMATS:
        raise ValueError("Unsupported image type")

    output_format = output_format.upper()
    if output_format not in {"WEBP", "JPEG"}:
        raise ValueError("Unsupported output format")

    # set before any Image.open() call — module-level so it applies globally
    Image.MAX_IMAGE_PIXELS = 50_000_000

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            img.load()

            if img.mode != "RGB":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA", "PA"):
                    alpha = img.convert("RGBA").split()[3]
                    bg.paste(img.convert("RGB"), mask=alpha)
                else:
                    bg.paste(img.convert("RGB"))
                img = bg

            # new Image strips all EXIF, GPS, IPTC, XMP, and embedded metadata
            clean = Image.new("RGB", img.size)
            clean.paste(img)
            img = clean

            w, h = img.size
            if w > max_px or h > max_px:
                ratio = max_px / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

            out = io.BytesIO()
            if output_format == "WEBP":
                img.save(out, format="WEBP", quality=88, method=4)
            else:
                # method is a webp-only encoder arg so it is omitted for jpeg
                img.save(out, format="JPEG", quality=88, optimize=True)
            return out.getvalue()

    except (DecompressionBombWarning, DecompressionBombError):
        raise ValueError("Image exceeds maximum pixel limit")
    except (UnidentifiedImageError, Exception):
        raise ValueError("Invalid or corrupt image")


def _detect_image_format(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None
