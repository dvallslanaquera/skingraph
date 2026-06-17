# it contains two main scanners: flash one and the pro expert fallback for challenging pictures
import base64
import io
import logging
from typing import Dict, Any, Literal, Optional, cast
from uuid import uuid4
import numpy as np
from PIL import Image, ImageFilter, ImageStat
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from src.state import AgentState, ProductExtraction
from src.config import (FLASH_MODEL, PRO_MODEL, MIN_MEAN_LUMINANCE,
                       MAX_MEAN_LUMINANCE, MIN_LUMINANCE_STDDEV)


# TODO: probably better to keep prompts in different files
# TODO: fine-tune the prompt to Gemini requirements
SCANNER_SYSTEM_PROMPT = """
## ROLE
You are a Senior Dermatological Assistant and Expert OCR analyzer specializing in Japanese skincare product labels.
Your task is to extract and standardize skincare product information with high accuracy.

## INSTRUCTIONS
1. Identify and extract:
   - Brand name
   - Product name
   - Full list of ingredients (in order of concentration)
2. For each ingredient, provide:
   - Raw ingredient name as written on label
   - Standardized JCIA (Japan Cosmetic Industry Association) name if applicable
3. Classify the product category:
   - Check if labeled as "医薬部外品" (quasi-drug/medicated product)
   - Mark accordingly in is_quasi_drug field
4. Detect the label's PRIMARY language:
   - Base this on the dominant script/text of the label itself, NOT the brand's country of origin.
   - Report it as a 2-letter uppercase code in source_language: JP (Japanese), EN (English),
     KO (Korean), FR (French), ZH (Chinese), etc.
5. Assess extraction confidence (0.0 to 1.0):
   - 1.0: Clear, legible text with no ambiguity
   - 0.7: Minor issues (slight blur, small glare spots) - most content readable
   - 0.4: Significant challenges (curved text, heavy glare) - some guessing required
   - 0.0: Unreadable or missing critical information
6. Return ONLY valid JSON with this exact structure:
{
  "brand": "string (English brand name)",
  "product_name": "string (official English name — transliterate katakana if needed, e.g. モイスチャライジングクリーム → Moisturizing Cream)",
  "ingredients": [{"name_raw": "string", "name_standardized": "string"}],
  "is_quasi_drug": boolean,
  "source_language": "string (2-letter uppercase code: JP, EN, KO, FR, ZH, ...)",
  "extraction_confidence": float,
  "system_status": "SUCCESS | INCOMPLETE | RETAKE_REQUIRED"
}
"""


CLASSIFY_PROMPT = """
Look at this photo and report what it shows, then which side of the product it is.

1) content — what is actually in the frame:
   - "product": exactly ONE skincare product (bottle, tube, jar, pump, sachet,
     or its box) is the subject.
   - "not_a_product": there is NO skincare product to analyse — e.g. a person,
     a pet, scenery, food, a screenshot, a random object, or a blank/illegible
     frame.
   - "multiple_products": TWO OR MORE distinct skincare products are in frame.

2) side — only meaningful when content is "product" (give your best guess
   otherwise):
   - "front": the marketing/branding side — brand, product name, hero copy. The full
     ingredient list (全成分 / "Ingredients:") is NOT legibly visible.
   - "back": the information side where the full ingredient list is printed and
     readable (paragraph of ingredient names, often headed 全成分 or "Ingredients").
   Rule of thumb: if you can read an actual ingredient LIST, it's "back". If you
   only see branding and no readable ingredient list, it's "front".

Return:
- content: "product" | "not_a_product" | "multiple_products"
- side: "front" or "back"
- confidence: 0.0-1.0 — how certain you are overall.
""".strip()


class ImageSide(BaseModel):
    content: Literal["product", "not_a_product", "multiple_products"] = Field(
        default="product",
        description=(
            "What the photo shows: one analysable product, no product at all, "
            "or several distinct products sharing one frame."
        ),
    )
    side: Literal["front", "back"] = Field(
        description="Which side of the product the photo shows."
    )
    confidence: float = Field(
        description="0.0-1.0 overall confidence in the content + side classification."
    )


def build_vlm(model: str, schema, *, temperature: float = 0.0):
    """Configured Gemini client with structured output, shared by the VLM nodes."""
    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, timeout=120, max_retries=3
    ).with_structured_output(schema)


def image_message(text: str, image_path: str) -> HumanMessage:
    """A HumanMessage carrying a text prompt plus the preprocessed base64 image."""
    base64_image = encode_image(image_path)
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )


def classify_side_node(state: AgentState) -> Dict[str, Any]:
    """Classify the photo's content (Tier 2) and which side it shows.

    In one VLM call this both decides front vs back AND flags out-of-distribution
    frames — ``not_a_product`` / ``multiple_products`` — so the graph can reject
    them before the structured-output scanner is forced to fabricate a product.
    An explicitly passed ``image_type`` (CLI override) wins and skips the call;
    the Tier-1 pixel gate still guards that path.
    """
    override = state.get("image_type")
    if override in ("front", "back"):
        logging.info("Image side overridden by caller: %s", override)
        return {"image_type": override}

    logging.info("Classifying image content + side...")
    llm = build_vlm(FLASH_MODEL, ImageSide)
    result = cast(ImageSide, llm.invoke([image_message(CLASSIFY_PROMPT, state["image_path"])]))
    logging.info(
        "Image classified: content=%s side=%s (confidence %.2f)",
        result.content,
        result.side,
        result.confidence,
    )
    return {"image_type": result.side, "image_content": result.content}


# ---------------------------------------------------------------------------
# Image preprocessing helpers
# ---------------------------------------------------------------------------

def _apply_white_balance(img: Image.Image) -> Image.Image:
    """Gray-world white balance, capped at ±20% per channel to protect brand colors."""
    arr = np.array(img, dtype=np.float32)
    means = arr.mean(axis=(0, 1))          # (R_mean, G_mean, B_mean)
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
    gamma = float(np.clip(
        np.log(target_mean / 255.0) / np.log(max(mean, 1.0) / 255.0),
        0.5, 2.0,
    ))
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
    arr = np.array(img.resize((tw, th), Image.BILINEAR).convert("L"))
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
    return img.rotate(best_angle, resample=Image.BILINEAR, expand=False,
                      fillcolor=(255, 255, 255))


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
    fy = (ty - ty0)[:, np.newaxis]   # (h, 1)
    fx = (tx - tx0)[np.newaxis, :]   # (1, w)

    # Advanced indexing: shapes (h,1), (1,w), (h,w) broadcast to (h,w)
    v00 = luts[ty0[:, np.newaxis], tx0[np.newaxis, :], y_arr]
    v01 = luts[ty0[:, np.newaxis], tx1[np.newaxis, :], y_arr]
    v10 = luts[ty1[:, np.newaxis], tx0[np.newaxis, :], y_arr]
    v11 = luts[ty1[:, np.newaxis], tx1[np.newaxis, :], y_arr]

    y_enhanced = np.clip(
        v00 * (1 - fy) * (1 - fx) + v01 * (1 - fy) * fx +
        v10 * fy * (1 - fx) + v11 * fy * fx,
        0, 255,
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
    img = Image.open(io.BytesIO(image_bytes))
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


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        image_bytes = preprocess_image(img_file.read())
    return base64.b64encode(image_bytes).decode(encoding="utf-8")


def assess_image_quality(image_path: str) -> Optional[str]:
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
    logging.info(
        "Tier-1 pixel pre-check: mean luminance %.1f, stddev %.1f", mean, stddev
    )
    if mean < MIN_MEAN_LUMINANCE:
        return "too_dark"
    if mean > MAX_MEAN_LUMINANCE:
        return "too_bright"
    if stddev < MIN_LUMINANCE_STDDEV:
        return "blank"
    return None


# Both scanners share everything but the model, prompt, and the model tag they
# record — so they delegate to one core and only differ in those three inputs.
def _run_scanner(
    state: AgentState, *, model: str, prompt: str, model_tag: str
) -> Dict[str, Any]:
    llm = build_vlm(model, ProductExtraction)
    extracted = cast(
        ProductExtraction, llm.invoke([image_message(prompt, state["image_path"])])
    )
    logging.info(
        "%s scan completed with confidence %.2f",
        model_tag,
        extracted.extraction_confidence,
    )
    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": model_tag,
        "trace_id": str(uuid4()),
    }


# Lightweight scanner (Flash Gemini). On a correction retry, the deterministic
# feedback from the correction node is appended to the system prompt.
def flash_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting lightweight flash scan using %s...", FLASH_MODEL)
    prompt = SCANNER_SYSTEM_PROMPT
    if state.get("correction_attempts", 0) > 0:
        prompt += (
            f"\n\nPREVIOUS ATTEMPT FEEDBACK:\n{state['correction_feedback']}\n"
            "Correct specifically those issues. Do not repeat the same mistakes."
        )
    return _run_scanner(state, model=FLASH_MODEL, prompt=prompt, model_tag="flash")


# Heavyweight model (aka expert fallback) for visually difficult labels.
def pro_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting heavyweight pro scan using %s...", PRO_MODEL)
    prompt = (
        SCANNER_SYSTEM_PROMPT
        + "\nFOCUS: Pay extreme attention to warped text on the edges of the bottle."
    )
    return _run_scanner(state, model=PRO_MODEL, prompt=prompt, model_tag="pro")
