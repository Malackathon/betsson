from pathlib import Path

from PIL import Image

from src.vision.screen_change import screen_change


def _png(path: Path, color: tuple[int, int, int], size=(200, 100), patch=None) -> Path:
    im = Image.new("RGB", size, color)
    if patch:
        im.paste(Image.new("RGB", (60, 40), patch), (20, 20))
    im.save(path)
    return path


def test_identical_screens_have_no_change(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10))
    b = _png(tmp_path / "b.png", (10, 10, 10))
    assert screen_change(a, b) == 0.0


def test_changed_reels_register_as_change(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10))
    b = _png(tmp_path / "b.png", (10, 10, 10), patch=(240, 200, 30))
    assert screen_change(a, b) > 0.01


def test_different_sizes_are_still_comparable(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10), size=(200, 100))
    b = _png(tmp_path / "b.png", (10, 10, 10), size=(210, 104))
    assert screen_change(a, b) < 0.01


def test_missing_file_gives_none(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10))
    assert screen_change(a, tmp_path / "nope.png") is None
