# Tests for the deterministic image-preprocessing pipeline: EXIF orientation,
# the light/ocr profile split, the focus (blur) measure, and the optional
# barcode decode. Pure Pillow/NumPy — nothing to mock.
import io

import numpy as np
import pytest
from PIL import Image

from src import preprocess
from src.preprocess import (
    _focus_variance,
    decode_jan,
    encode_image,
    frame_stats,
    preprocess_image,
)


def _jpeg_bytes(img: Image.Image, **save_kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", **save_kwargs)
    return buf.getvalue()


def _detailed(w: int, h: int) -> Image.Image:
    """A checkerboard — sharp detail so nothing else in the pipeline rejects it."""
    tile = (np.indices((h, w)).sum(axis=0) % 2 * 255).astype("uint8")
    return Image.fromarray(tile).convert("RGB")


# --------------------------------------------------------------------------- #
# EXIF orientation (S14)
# --------------------------------------------------------------------------- #
def test_preprocess_honours_exif_orientation():
    # Orientation 6 = rotate 90° CW to display: a 100×40 sensor image becomes
    # 40×100 on screen. Without exif_transpose the VLM sees it sideways.
    img = _detailed(100, 40)
    exif = Image.Exif()
    exif[274] = 6  # Orientation tag
    raw = _jpeg_bytes(img, exif=exif)

    out = Image.open(io.BytesIO(preprocess_image(raw, profile="light")))
    assert out.size == (40, 100)


def test_preprocess_without_exif_keeps_dimensions():
    raw = _jpeg_bytes(_detailed(100, 40))
    out = Image.open(io.BytesIO(preprocess_image(raw, profile="light")))
    assert out.size == (100, 40)


# --------------------------------------------------------------------------- #
# profiles (S15)
# --------------------------------------------------------------------------- #
def test_profiles_produce_different_output():
    raw = _jpeg_bytes(_detailed(200, 200))
    assert preprocess_image(raw, profile="light") != preprocess_image(raw, profile="ocr")


def test_encode_image_caches_per_profile(tmp_path):
    path = tmp_path / "img.jpg"
    path.write_bytes(_jpeg_bytes(_detailed(64, 64)))
    encode_image.cache_clear()
    light = encode_image(str(path), "light")
    ocr = encode_image(str(path), "ocr")
    assert light != ocr
    # Same (path, profile) is served from cache, not re-encoded.
    assert encode_image(str(path), "light") is light


def test_resize_caps_longest_edge():
    raw = _jpeg_bytes(_detailed(4096, 2048))
    out = Image.open(io.BytesIO(preprocess_image(raw, max_dim=2048, profile="light")))
    assert max(out.size) == 2048


# --------------------------------------------------------------------------- #
# focus measure (S2)
# --------------------------------------------------------------------------- #
def test_focus_variance_separates_sharp_from_smooth():
    sharp = np.asarray(_detailed(200, 200).convert("L"))
    smooth = np.asarray(Image.linear_gradient("L"))
    assert _focus_variance(sharp) > 100 * _focus_variance(smooth)


def test_frame_stats_returns_all_three_signals(tmp_path):
    path = tmp_path / "img.png"
    _detailed(64, 64).save(path)
    stats = frame_stats(str(path))
    assert set(stats) == {"mean", "stddev", "focus"}


def test_frame_stats_none_for_unreadable(tmp_path):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not an image")
    assert frame_stats(str(path)) is None


# --------------------------------------------------------------------------- #
# barcode decode (S7) — pyzbar is optional; both outcomes are valid
# --------------------------------------------------------------------------- #
def test_decode_jan_none_on_barcode_free_image(tmp_path):
    path = tmp_path / "img.png"
    _detailed(64, 64).save(path)
    # No barcode in frame (and pyzbar may be absent) → None either way.
    assert decode_jan(str(path)) is None


def test_decode_jan_none_when_pyzbar_missing(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("pyzbar"):
            raise ImportError("pyzbar not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    path = tmp_path / "img.png"
    _detailed(32, 32).save(path)
    assert decode_jan(str(path)) is None


# --------------------------------------------------------------------------- #
# gate wiring sanity: blur fires only after the cheaper reasons
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "color, expected",
    [((2, 2, 2), "too_dark"), ((255, 255, 255), "too_bright"), ((128, 128, 128), "blank")],
)
def test_uniform_frames_hit_luminance_gates_not_blur(tmp_path, color, expected):
    path = tmp_path / "img.png"
    Image.new("RGB", (64, 64), color).save(path)
    assert preprocess.assess_image_quality(str(path)) == expected
