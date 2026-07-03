# Deterministic image preprocessing applied before any VLM call, plus the
# Tier-1 pixel quality gate. Pure Pillow/NumPy — no graph or LLM dependencies.
import base64
import io
import logging
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter, ImageStat

from src.config import MAX_MEAN_LUMINANCE, MIN_LUMINANCE_STDDEV, MIN_MEAN_LUMINANCE


def _apply_white_balance(img: Image.Image) -> Image.Image:
    """Gray-world white balance, capped at ±20% per channel to protect brand colors."""
    arr = np.array(img, dtype=np.float32)
    means = arr.mean(axis=(0, 1))  # (R_mean, G_mean, B_mean)
    overall = means.mean()
    scales = np.clip(overall / np.maximum(means, 1.0), 0.8, 1.2)
    return Image.fromarray(np.clip(arr * scales, 0, 255).astype(np.uint8))


def _reduce_glare(img: Image.Image, threshold: int = 245) -> Image.Image:
    """Clamp specular highlights: pixels where all channels >= threshold are clamped."""
    arr = np.array(img)
    mask = np.all(arr >= threshold, axis=2, keepdims=True)
    return Image.fromarray(np.where(mask, threshold, arr).astype(np.uint8))


def _apply_gamma(img: Image.Image, target_mean: float = 100.0) -> Image.Image:
    """Gamma correction for dark labels; no-op when mean luminance >= target_mean."""
    gray = np.array(img.convert("L"))
    mean = float(gray.mean())
    if mean >= target_mean:
        return img
    gamma = float(
        np.clip(
            np.log(target_mean / 255.0) / np.log(max(mean, 1.0) / 255.0),
            0.5,
            2.0,
        )
    )
    lut = (255.0 * (np.arange(256) / 255.0) ** gamma).astype(np.uint8)
    return Image.fromarray(lut[np.array(img)])


def _reduce_noise(img: Image.Image) -> Image.Image:
    """Mild median filter to suppress sensor grain before sharpening."""
    return img.filter(ImageFilter.MedianFilter(size=3))


def _deskew(img: Image.Image, max_angle: float = 10.0) -> Image.Image:
    """Correct label tilt via projection-profile variance on a small thumbnail.

    Works best for light-background labels (ingredient back-sides): binarises at
    the mean, then finds the rotation that maximises horizontal-projection variance
    (text lines become horizontal → sharp spikes in the projection histogram).
    """
    scale = 400.0 / max(img.width, img.height)
    tw, th = int(img.width * scale), int(img.height * scale)
    arr = np.array(img.resize((tw, th), Image.Resampling.BILINEAR).convert("L"))
    binary = Image.fromarray(((arr < arr.mean()) * 255).astype(np.uint8))

    best_angle, best_var = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 0.5, 0.5):
        rotated = np.array(binary.rotate(float(angle), fillcolor=0))
        var = float(rotated.sum(axis=1).var())
        if var > best_var:
            best_var = var
            best_angle = float(angle)

    if abs(best_angle) < 0.5:
        return img
    return img.rotate(
        best_angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=(255, 255, 255)
    )


def _apply_clahe(
    img: Image.Image,
    clip_limit: float = 2.0,
    grid_h: int = 8,
    grid_w: int = 8,
) -> Image.Image:
    """Contrast-Limited Adaptive Histogram Equalisation on the Y (luma) channel.

    Divides the luma plane into an 8×8 grid of tiles, computes a clipped
    histogram-equalisation LUT for each tile, then blends pixel values using
    bilinear interpolation between the four surrounding tile LUTs.  Cb/Cr are
    left untouched so brand colours are preserved.
    """
    ycbcr = img.convert("YCbCr")
    y, cb, cr = ycbcr.split()
    y_arr = np.array(y, dtype=np.uint8)
    h, w = y_arr.shape
    tile_h, tile_w = h / grid_h, w / grid_w

    # Step 1 — per-tile clipped histogram equalisation LUTs
    luts = np.zeros((grid_h, grid_w, 256), dtype=np.float32)
    for i in range(grid_h):
        for j in range(grid_w):
            r0, r1 = int(i * tile_h), min(int((i + 1) * tile_h), h)
            c0, c1 = int(j * tile_w), min(int((j + 1) * tile_w), w)
            tile = y_arr[r0:r1, c0:c1]
            n = tile.size
            hist = np.bincount(tile.ravel(), minlength=256).astype(np.float32)
            limit = max(1.0, clip_limit * n / 256.0)
            excess = np.maximum(hist - limit, 0.0).sum()
            hist = np.minimum(hist, limit)
            hist += excess / 256.0
            cdf = hist.cumsum()
            nonzero = cdf[cdf > 0]
            cdf_min = float(nonzero[0]) if len(nonzero) else 0.0
            denom = max(float(n) - cdf_min, 1.0)
            luts[i, j] = np.clip((cdf - cdf_min) / denom * 255.0, 0, 255)

    # Step 2 — vectorised bilinear interpolation across the full luma plane
    rows = np.arange(h)
    cols = np.arange(w)
    ty = np.clip((rows + 0.5) / tile_h - 0.5, 0, grid_h - 1)
    tx = np.clip((cols + 0.5) / tile_w - 0.5, 0, grid_w - 1)
    ty0 = np.floor(ty).astype(int)
    tx0 = np.floor(tx).astype(int)
    ty1 = np.minimum(ty0 + 1, grid_h - 1)
    tx1 = np.minimum(tx0 + 1, grid_w - 1)
    fy = (ty - ty0)[:, np.newaxis]  # (h, 1)
    fx = (tx - tx0)[np.newaxis, :]  # (1, w)

    # Advanced indexing: shapes (h,1), (1,w), (h,w) broadcast to (h,w)
    v00 = luts[ty0[:, np.newaxis], tx0[np.newaxis, :], y_arr]
    v01 = luts[ty0[:, np.newaxis], tx1[np.newaxis, :], y_arr]
    v10 = luts[ty1[:, np.newaxis], tx0[np.newaxis, :], y_arr]
    v11 = luts[ty1[:, np.newaxis], tx1[np.newaxis, :], y_arr]

    y_enhanced = np.clip(
        v00 * (1 - fy) * (1 - fx) + v01 * (1 - fy) * fx + v10 * fy * (1 - fx) + v11 * fy * fx,
        0,
        255,
    ).astype(np.uint8)

    return Image.merge("YCbCr", (Image.fromarray(y_enhanced), cb, cr)).convert("RGB")


def _sharpen(img: Image.Image) -> Image.Image:
    """Unsharp mask to make ingredient-list text edges crisp."""
    return img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))


# ---------------------------------------------------------------------------
# Main preprocessing entry point
# ---------------------------------------------------------------------------


def preprocess_image(image_bytes: bytes, max_dim: int = 2048) -> bytes:
    """Full preprocessing pipeline applied to every image before VLM inference.

    Steps (in order):
        1. Resize       — cap longest edge at 2048 px (LANCZOS)
        2. White balance — gray-world correction, ±20 % cap per channel
        3. Glare reduction — clamp specular highlights ≥ 245 luma
        4. Gamma correction — brighten dark labels (mean luma < 100)
        5. Noise reduction — 3×3 median filter to suppress sensor grain
        6. Deskewing    — projection-profile variance to correct tilt ≤ ±10°
        7. CLAHE        — 8×8 tile adaptive contrast on Y channel (YCbCr)
        8. Sharpening   — unsharp mask for crisp text edges
        9. JPEG encode  — quality 85 for payload efficiency
    """
    img: Image.Image = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    img = img.convert("RGB")

    img = _apply_white_balance(img)
    img = _reduce_glare(img)
    img = _apply_gamma(img)
    img = _reduce_noise(img)
    img = _deskew(img)
    img = _apply_clahe(img)
    img = _sharpen(img)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


# Cached: within one scan the same temp file is encoded for every VLM call
# (classify, each flash attempt, pro, verify), and the full pipeline — deskew
# loop + CLAHE included — costs ~1–3 s per run. Scan images are written once
# per upload, so a path never changes content mid-scan.
@lru_cache(maxsize=8)
def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        image_bytes = preprocess_image(img_file.read())
    return base64.b64encode(image_bytes).decode(encoding="utf-8")


def assess_image_quality(image_path: str) -> str | None:
    """Tier-1 deterministic pre-flight on raw pixels — costs no VLM call.

    Returns ``None`` when the frame is worth sending to Gemini, or a short reason
    code when it is degenerate and should be bounced straight back to the user:

      - ``"too_dark"``   near-black frame (lens cap, no light)
      - ``"too_bright"`` blown-out / washed-out frame
      - ``"blank"``      near-uniform frame (blank wall, severe defocus, no product)
      - ``"unreadable"`` the bytes could not be decoded as an image

    This is the cheapest out-of-distribution filter in the pipeline: it spends no
    Gemini call and, crucially, intercepts the inputs the structured-output
    scanner would otherwise be *forced* to hallucinate a product from (its
    ``brand`` / ``ingredients`` fields are required, so it cannot answer "nothing
    here"). Thresholds live in config and are tuned to fire only on truly
    degenerate frames, not on merely dark or low-contrast labels.
    """
    try:
        with Image.open(image_path) as img:
            stat = ImageStat.Stat(img.convert("L"))
    except Exception:
        logging.warning("Tier-1 pixel pre-check: could not open %s", image_path)
        return "unreadable"

    mean = stat.mean[0]
    stddev = stat.stddev[0]
    logging.info("Tier-1 pixel pre-check: mean luminance %.1f, stddev %.1f", mean, stddev)
    if mean < MIN_MEAN_LUMINANCE:
        return "too_dark"
    if mean > MAX_MEAN_LUMINANCE:
        return "too_bright"
    if stddev < MIN_LUMINANCE_STDDEV:
        return "blank"
    return None
