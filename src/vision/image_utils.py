"""Image utilities for the vision inspection pipeline.

Provides loading, cropping, annotation, and privacy-masking helpers
used by the motion detector and Gemini inspector.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

BBox = tuple[int, int, int, int]  # (x, y, width, height)
RGBColor = tuple[int, int, int]
Frame = NDArray[np.uint8]  # H×W×3 array

# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------


def load_image(source: str | Path | bytes) -> Image.Image:
    """Load an image from a file path or raw bytes. Always returns RGB."""
    if isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        img = Image.open(path)
    return img.convert("RGB")


def load_frame(source: str | Path | bytes) -> Frame:
    """Load an image as a numpy array (H×W×3, RGB uint8)."""
    return pil_to_frame(load_image(source))


def save_image(image: Image.Image, path: Path, *, quality: int = 90) -> Path:
    """Save a PIL Image to disk (PNG or JPEG based on suffix). Creates parents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs: dict[str, object] = {}
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
        if image.mode != "RGB":
            image = image.convert("RGB")
    elif suffix == ".png":
        save_kwargs["optimize"] = True

    image.save(path, **save_kwargs)  # type: ignore[arg-type]
    return path.resolve()


# ---------------------------------------------------------------------------
# Colour-space helpers
# ---------------------------------------------------------------------------


def bgr_to_rgb(frame: Frame) -> Frame:
    """Convert a BGR numpy array to RGB by reversing the channel axis."""
    return np.ascontiguousarray(frame[:, :, ::-1])


def rgb_to_bgr(frame: Frame) -> Frame:
    """Convert an RGB numpy array to BGR by reversing the channel axis."""
    return np.ascontiguousarray(frame[:, :, ::-1])


# ---------------------------------------------------------------------------
# Cropping
# ---------------------------------------------------------------------------


def crop_region(image: Image.Image, bbox: BBox) -> Image.Image:
    """Crop a rectangular region. *bbox* is ``(x, y, width, height)``."""
    x, y, w, h = bbox
    if w <= 0 or h <= 0:
        raise ValueError(f"BBox must have positive dimensions, got w={w}, h={h}")

    img_w, img_h = image.size
    left = max(x, 0)
    upper = max(y, 0)
    right = min(x + w, img_w)
    lower = min(y + h, img_h)

    if left >= right or upper >= lower:
        raise ValueError(
            f"BBox ({x},{y},{w},{h}) is entirely outside "
            f"the image ({img_w}×{img_h})"
        )
    return image.crop((left, upper, right, lower))


def crop_reels_region(
    image: Image.Image,
    *,
    top_pct: float = 0.15,
    bottom_pct: float = 0.85,
    left_pct: float = 0.05,
    right_pct: float = 0.95,
) -> Image.Image:
    """Crop the estimated reels area using percentage-based coordinates.

    Default percentages target a typical 5-reel slot layout.
    """
    for name, val in [
        ("top_pct", top_pct), ("bottom_pct", bottom_pct),
        ("left_pct", left_pct), ("right_pct", right_pct),
    ]:
        if not 0.0 <= val <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {val}")
    if top_pct >= bottom_pct:
        raise ValueError(f"top_pct ({top_pct}) must be < bottom_pct ({bottom_pct})")
    if left_pct >= right_pct:
        raise ValueError(f"left_pct ({left_pct}) must be < right_pct ({right_pct})")

    img_w, img_h = image.size
    return image.crop((
        int(img_w * left_pct), int(img_h * top_pct),
        int(img_w * right_pct), int(img_h * bottom_pct),
    ))


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


def _get_default_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load DejaVuSans; fall back to the built-in bitmap font."""
    for candidate in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def annotate_bbox(
    image: Image.Image,
    bbox: BBox,
    label: str = "",
    *,
    color: RGBColor = (255, 0, 0),
    width: int = 3,
) -> Image.Image:
    """Draw a labeled bounding box on a **copy** of the image."""
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    x, y, w, h = bbox
    draw.rectangle((x, y, x + w, y + h), outline=color, width=width)

    if label:
        font = _get_default_font()
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = 4
        ly = max(y - th - pad * 2, 0)
        draw.rectangle((x, ly, x + tw + pad * 2, ly + th + pad * 2), fill=color)
        brightness = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        tc: RGBColor = (0, 0, 0) if brightness > 128 else (255, 255, 255)
        draw.text((x + pad, ly + pad), label, fill=tc, font=font)

    return annotated


def annotate_multiple(
    image: Image.Image,
    annotations: Sequence[tuple[BBox, str]],
    *,
    colors: Sequence[RGBColor] | None = None,
    width: int = 3,
) -> Image.Image:
    """Draw multiple labeled bounding boxes on a **copy** of the image."""
    palette: list[RGBColor] = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (255, 128, 0), (128, 0, 255),
    ]
    result = image.copy()
    for idx, (bbox, label) in enumerate(annotations):
        c = colors[idx] if colors and idx < len(colors) else palette[idx % len(palette)]
        result = annotate_bbox(result, bbox, label, color=c, width=width)
    return result


# ---------------------------------------------------------------------------
# Privacy masking (R15)
# ---------------------------------------------------------------------------


def mask_region(
    image: Image.Image,
    bbox: BBox,
    *,
    method: str = "blur",
    blur_radius: int = 20,
    pixel_size: int = 10,
) -> Image.Image:
    """Mask (blur/pixelate/black-out) a region for privacy."""
    if method not in {"blur", "pixelate", "black"}:
        raise ValueError(f"method must be blur|pixelate|black, got {method!r}")

    result = image.copy()
    x, y, w, h = bbox
    img_w, img_h = result.size
    left, upper = max(x, 0), max(y, 0)
    right, lower = min(x + w, img_w), min(y + h, img_h)
    if left >= right or upper >= lower:
        return result

    crop_box = (left, upper, right, lower)
    region = result.crop(crop_box)

    if method == "blur":
        masked = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    elif method == "pixelate":
        rw, rh = right - left, lower - upper
        small = region.resize((max(rw // pixel_size, 1), max(rh // pixel_size, 1)), Image.Resampling.NEAREST)
        masked = small.resize((rw, rh), Image.Resampling.NEAREST)
    else:
        masked = Image.new("RGB", (right - left, lower - upper), (0, 0, 0))

    result.paste(masked, crop_box)
    return result


def mask_personal_data(
    image: Image.Image,
    regions: Sequence[BBox],
    *,
    method: str = "blur",
) -> Image.Image:
    """Apply privacy masking to multiple regions containing personal data (R15)."""
    result = image.copy()
    for bbox in regions:
        result = mask_region(result, bbox, method=method)
    return result


# ---------------------------------------------------------------------------
# Serialisation / conversion
# ---------------------------------------------------------------------------


def image_to_bytes(image: Image.Image, *, fmt: str = "PNG") -> bytes:
    """Convert a PIL Image to bytes in the specified format."""
    buf = io.BytesIO()
    save_kwargs: dict[str, object] = {}
    if fmt.upper() in {"JPEG", "JPG"}:
        if image.mode != "RGB":
            image = image.convert("RGB")
        save_kwargs["quality"] = 90
    image.save(buf, format=fmt, **save_kwargs)  # type: ignore[arg-type]
    return buf.getvalue()


def image_to_base64(image: Image.Image, *, fmt: str = "PNG") -> str:
    """Convert a PIL Image to a base64-encoded string (no data-URI prefix)."""
    return base64.b64encode(image_to_bytes(image, fmt=fmt)).decode("ascii")


def frame_to_pil(frame: Frame) -> Image.Image:
    """Convert a numpy RGB frame to a PIL Image."""
    return Image.fromarray(frame, mode="RGB")


def pil_to_frame(image: Image.Image) -> Frame:
    """Convert a PIL Image to a numpy RGB frame (H×W×3, uint8)."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    return np.ascontiguousarray(np.array(image, dtype=np.uint8))


def resize_for_api(image: Image.Image, *, max_side: int = 1024) -> Image.Image:
    """Resize so the longest side ≤ *max_side*. Preserves aspect ratio."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return image.resize(
        (int(width * scale), int(height * scale)), Image.Resampling.LANCZOS,
    )
