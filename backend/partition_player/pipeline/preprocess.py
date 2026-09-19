"""Turn an uploaded photo, scan or screenshot into a clean grayscale PNG for the engine.

Steps: honour EXIF orientation, drop the alpha channel and any embedded thumbnail by re-encoding,
downscale so the longest side is at most `max_side_px`, and even out lighting with CLAHE so a shadowed
phone photo binarises like a scan. Deskew is left to the engine (homr dewarps each staff itself).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


def preprocess(src: Path, dst: Path, max_side_px: int = 2500) -> dict:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("L")
        w, h = im.size
        scale = min(1.0, max_side_px / max(w, h))
        if scale < 1.0:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        gray = np.asarray(im)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), gray)
    return {"width": int(gray.shape[1]), "height": int(gray.shape[0]), "scale": round(scale, 4)}


def thumbnail(src: Path, dst: Path, max_side_px: int = 480) -> None:
    """Small colour JPEG of the upload for the score library list."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side_px, max_side_px), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "JPEG", quality=80, optimize=True)


def review_image(src: Path, dst: Path, budget: int = 300_000, max_side: int = 2400) -> dict:
    """A copy of the upload the user can check the sheet against (ADR 0005): WebP, colour, longest side
    `max_side`, quality stepped down until the file is under `budget` bytes, then the side reduced.
    Returns width, height and the scale from upload pixels (EXIF-oriented) to review pixels."""
    import io

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        for side in (max_side, 2000, 1600, 1200):
            scale = min(1.0, side / max(w, h))
            small = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS) if scale < 1.0 else im
            for quality in (78, 70, 62, 55, 48, 40):
                buf = io.BytesIO()
                small.save(buf, "WEBP", quality=quality, method=4)
                if buf.tell() <= budget or (side == 1200 and quality == 40):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(buf.getvalue())
                    return {"width": small.size[0], "height": small.size[1], "scale": round(scale, 6), "bytes": buf.tell(), "quality": quality}
    raise RuntimeError("unreachable")
