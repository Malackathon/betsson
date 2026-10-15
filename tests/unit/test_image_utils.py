"""Unit tests for src.vision.image_utils.

Uses synthetic fixture images — no real screenshots with personal data.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.vision.image_utils import (
    BBox,
    annotate_bbox,
    annotate_multiple,
    bgr_to_rgb,
    crop_reels_region,
    crop_region,
    frame_to_pil,
    image_to_base64,
    image_to_bytes,
    load_frame,
    load_image,
    mask_personal_data,
    mask_region,
    pil_to_frame,
    resize_for_api,
    rgb_to_bgr,
    save_image,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _make_rgb_image(w: int = 200, h: int = 100, color: tuple[int, int, int] = (128, 64, 32)) -> Image.Image:
    """Create a solid-colour RGB PIL Image."""
    return Image.new("RGB", (w, h), color)


def _make_gradient_image(w: int = 200, h: int = 100) -> Image.Image:
    """Create a horizontal-gradient image for testing crops & masks."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :, 0] = np.linspace(0, 255, w, dtype=np.uint8)  # R gradient
    arr[:, :, 1] = 100
    arr[:, :, 2] = 200
    return Image.fromarray(arr, "RGB")


# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------


class TestLoadImage:
    def test_load_from_bytes(self) -> None:
        img = _make_rgb_image()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        loaded = load_image(buf.getvalue())
        assert loaded.mode == "RGB"
        assert loaded.size == (200, 100)

    def test_load_from_path(self, tmp_path: Path) -> None:
        p = tmp_path / "test.png"
        _make_rgb_image().save(p)
        loaded = load_image(p)
        assert loaded.mode == "RGB"

    def test_load_converts_rgba(self) -> None:
        rgba = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        buf = io.BytesIO()
        rgba.save(buf, format="PNG")
        loaded = load_image(buf.getvalue())
        assert loaded.mode == "RGB"

    def test_load_nonexistent_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_image("/nonexistent/path.png")


class TestLoadFrame:
    def test_returns_numpy_array(self) -> None:
        img = _make_rgb_image(50, 30)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        frame = load_frame(buf.getvalue())
        assert frame.shape == (30, 50, 3)
        assert frame.dtype == np.uint8


class TestSaveImage:
    def test_save_png(self, tmp_path: Path) -> None:
        p = tmp_path / "out.png"
        result = save_image(_make_rgb_image(), p)
        assert result.exists()

    def test_save_jpeg(self, tmp_path: Path) -> None:
        p = tmp_path / "out.jpg"
        result = save_image(_make_rgb_image(), p, quality=80)
        assert result.exists()

    def test_creates_parents(self, tmp_path: Path) -> None:
        p = tmp_path / "a" / "b" / "img.png"
        save_image(_make_rgb_image(), p)
        assert p.exists()


# ---------------------------------------------------------------------------
# Colour-space
# ---------------------------------------------------------------------------


class TestColourConversion:
    def test_bgr_to_rgb_round_trip(self) -> None:
        rgb = np.array([[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8)
        bgr = rgb_to_bgr(rgb)
        assert bgr[0, 0, 0] == 0  # B channel
        assert bgr[0, 0, 2] == 255  # R channel moved
        back = bgr_to_rgb(bgr)
        np.testing.assert_array_equal(back, rgb)


# ---------------------------------------------------------------------------
# Cropping
# ---------------------------------------------------------------------------


class TestCropRegion:
    def test_basic_crop(self) -> None:
        img = _make_rgb_image(200, 100)
        cropped = crop_region(img, (10, 10, 50, 30))
        assert cropped.size == (50, 30)

    def test_negative_dims_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            crop_region(_make_rgb_image(), (0, 0, -1, 10))

    def test_out_of_bounds_raises(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            crop_region(_make_rgb_image(100, 100), (200, 200, 50, 50))

    def test_clamps_to_bounds(self) -> None:
        """A bbox partially outside is clamped, not rejected."""
        img = _make_rgb_image(100, 100)
        cropped = crop_region(img, (80, 80, 50, 50))
        assert cropped.size == (20, 20)


class TestCropReelsRegion:
    def test_default_crop(self) -> None:
        img = _make_rgb_image(1280, 720)
        cropped = crop_reels_region(img)
        assert cropped.size[0] > 0
        assert cropped.size[1] > 0

    def test_invalid_pct_raises(self) -> None:
        with pytest.raises(ValueError):
            crop_reels_region(_make_rgb_image(), top_pct=1.5)

    def test_inverted_range_raises(self) -> None:
        with pytest.raises(ValueError, match="top_pct"):
            crop_reels_region(_make_rgb_image(), top_pct=0.9, bottom_pct=0.1)


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


class TestAnnotate:
    def test_annotate_bbox_returns_copy(self) -> None:
        img = _make_rgb_image()
        result = annotate_bbox(img, (10, 10, 50, 30), "test")
        assert result is not img
        assert result.size == img.size

    def test_annotate_multiple(self) -> None:
        img = _make_rgb_image(300, 200)
        anns: list[tuple[BBox, str]] = [
            ((10, 10, 50, 30), "A"),
            ((100, 50, 60, 40), "B"),
        ]
        result = annotate_multiple(img, anns)
        assert result is not img


# ---------------------------------------------------------------------------
# Privacy masking (R15)
# ---------------------------------------------------------------------------


class TestMasking:
    def test_blur_mask(self) -> None:
        img = _make_gradient_image()
        result = mask_region(img, (20, 10, 60, 40), method="blur")
        assert result.size == img.size
        assert result is not img

    def test_pixelate_mask(self) -> None:
        img = _make_gradient_image()
        result = mask_region(img, (20, 10, 60, 40), method="pixelate")
        assert result.size == img.size

    def test_black_mask(self) -> None:
        img = _make_gradient_image(100, 100)
        result = mask_region(img, (10, 10, 30, 30), method="black")
        # The blacked-out area should be all zeros
        arr = np.array(result)
        region = arr[10:40, 10:40]
        assert np.all(region == 0)

    def test_invalid_method_raises(self) -> None:
        with pytest.raises(ValueError, match="method"):
            mask_region(_make_rgb_image(), (0, 0, 10, 10), method="invalid")

    def test_mask_personal_data_multiple(self) -> None:
        img = _make_gradient_image(200, 200)
        regions: list[BBox] = [(10, 10, 30, 30), (100, 100, 40, 40)]
        result = mask_personal_data(img, regions)
        assert result.size == img.size

    def test_mask_out_of_bounds_returns_unchanged(self) -> None:
        img = _make_rgb_image(50, 50)
        result = mask_region(img, (100, 100, 20, 20))
        # Should return a copy without changes
        np.testing.assert_array_equal(np.array(result), np.array(img))


# ---------------------------------------------------------------------------
# Serialisation / conversion
# ---------------------------------------------------------------------------


class TestConversion:
    def test_image_to_bytes_png(self) -> None:
        img = _make_rgb_image()
        data = image_to_bytes(img, fmt="PNG")
        assert len(data) > 0
        restored = Image.open(io.BytesIO(data))
        assert restored.size == img.size

    def test_image_to_base64(self) -> None:
        img = _make_rgb_image(10, 10)
        b64 = image_to_base64(img)
        assert len(b64) > 0

    def test_frame_pil_round_trip(self) -> None:
        img = _make_gradient_image(50, 30)
        frame = pil_to_frame(img)
        assert frame.shape == (30, 50, 3)
        restored = frame_to_pil(frame)
        assert restored.size == (50, 30)
        np.testing.assert_array_equal(np.array(restored), frame)


class TestResizeForApi:
    def test_no_resize_when_small(self) -> None:
        img = _make_rgb_image(500, 300)
        result = resize_for_api(img, max_side=1024)
        assert result is img  # same object, no copy

    def test_resize_large_image(self) -> None:
        img = _make_rgb_image(2000, 1000)
        result = resize_for_api(img, max_side=1024)
        assert max(result.size) <= 1024
        # Aspect ratio preserved
        ratio_orig = 2000 / 1000
        ratio_new = result.size[0] / result.size[1]
        assert abs(ratio_orig - ratio_new) < 0.05

    def test_resize_square(self) -> None:
        img = _make_rgb_image(2048, 2048)
        result = resize_for_api(img, max_side=512)
        assert result.size == (512, 512)

