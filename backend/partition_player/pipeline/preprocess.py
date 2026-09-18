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
