"""Standalone Japanese OCR ingest path (Phase 0 — NOT wired into the graph).

Runs YomiToku's DocumentAnalyzer over the annotated golden images and writes
the raw extracted text to data/ocr_out/<id>.txt, printing each to stdout.

Pre-processing pipeline (on by default, disable with --no-preprocess):
  1. Cylindrical dewarping — corrects the horizontal curvature of bottle labels
     using a perspective-to-cylindrical inverse projection (cv2.remap).
  2. CLAHE — boosts contrast in the L channel of LAB colorspace without
     blowing out highlights; recovers the dense ingredient text under glare.

DocumentAnalyzer (rather than bare OCR) reconstructs reading order via a
layout model, so the dense 全成分 block comes out ordered, not scrambled.

Usage:
    poetry run python scripts/run_ocr.py                   # prod_001, prod_002
    poetry run python scripts/run_ocr.py --id prod_001     # one image
    poetry run python scripts/run_ocr.py --no-preprocess   # raw baseline
    poetry run python scripts/run_ocr.py --device cuda     # if a GPU exists

First run downloads model weights (hundreds of MB, slow once, then cached).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from yomitoku import DocumentAnalyzer
from yomitoku.data.functions import load_image

GOLDEN_DIR = Path("data/golden_set")
OUT_DIR = Path("data/ocr_out")
DEFAULT_IDS = ["prod_001", "prod_002"]


def dewarp_cylinder(img: np.ndarray, focal_ratio: float = 1.0) -> np.ndarray:
    """Unwrap cylindrical label distortion using inverse perspective projection.

    Maps each output pixel back to its source using:
        x_src = f * tan((x_dst - cx) / f) + cx
    where f = focal_ratio * image_width.  Larger focal_ratio = subtler correction.
    """
    h, w = img.shape[:2]
    cx = w / 2.0
    f = focal_ratio * w

    x_out = np.arange(w, dtype=np.float32)
    theta = (x_out - cx) / f
    x_src = (f * np.tan(theta) + cx).astype(np.float32)

    map_x = np.tile(x_src, (h, 1))
    map_y = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, w))

    return cv2.remap(img, map_x, map_y,
                     interpolation=cv2.INTER_CUBIC,
                     borderMode=cv2.BORDER_REPLICATE)


def apply_clahe(img: np.ndarray,
                clip_limit: float = 2.0,
                tile_size: int = 8) -> np.ndarray:
    """Enhance contrast in the L channel of LAB colorspace.

    Operates only on luminance so hue and saturation are preserved.
    clip_limit caps amplification to prevent noise in uniform regions.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit,
                             tileGridSize=(tile_size, tile_size))
    l_ch = clahe.apply(l_ch)
    return cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)


def preprocess(img: np.ndarray) -> np.ndarray:
    """Full pre-processing chain: dewarping → CLAHE."""
    img = dewarp_cylinder(img)
    img = apply_clahe(img)
    return img


def extract_text(results) -> str:
    """Join paragraphs in reading order; fall back to raw words if empty."""
    paragraphs = [p for p in results.paragraphs if p.contents]
    if paragraphs:
        paragraphs.sort(key=lambda p: p.order if p.order is not None else 1 << 30)
        return "\n".join(p.contents for p in paragraphs)
    return "\n".join(w.content for w in results.words if w.content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YomiToku OCR on golden images.")
    parser.add_argument(
        "--id", action="append", dest="ids",
        help="Golden-set id(s) to process (default: prod_001, prod_002). Repeatable.",
    )
    parser.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"],
        help="Inference device (default: cpu).",
    )
    parser.add_argument(
        "--no-preprocess", action="store_true",
        help="Skip CLAHE + dewarping (raw baseline for comparison).",
    )
    return parser.parse_args()


def main() -> None:
    # Windows consoles default to a legacy code page; force UTF-8 so Japanese
    # text prints instead of mojibake.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    ids = args.ids or DEFAULT_IDS
    do_preprocess = not args.no_preprocess
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"Loading YomiToku DocumentAnalyzer on device={args.device} "
        "(first run downloads weights)...", flush=True
    )
    analyzer = DocumentAnalyzer(visualize=False, device=args.device)

    for stem in ids:
        img_path = GOLDEN_DIR / f"{stem}.jpg"
        if not img_path.exists():
            print(f"!! Skipping {stem}: image not found at {img_path}", flush=True)
            continue

        # load_image returns a list of page-images (PDF-style); a JPEG is one page.
        pages = load_image(str(img_path))
        if do_preprocess:
            pages = [preprocess(p) for p in pages]

        page_texts = []
        total_words = 0
        conf_sum, conf_n = 0.0, 0
        for page in pages:
            results, *_ = analyzer(page)
            page_texts.append(extract_text(results))
            total_words += len(results.words)
            for w in results.words:
                if w.rec_score is not None:
                    conf_sum += w.rec_score
                    conf_n += 1

        text = "\n".join(page_texts)
        mean_conf = conf_sum / conf_n if conf_n else 0.0
        preprocess_tag = "preprocessed" if do_preprocess else "raw"

        out_path = OUT_DIR / f"{stem}.txt"
        out_path.write_text(text, encoding="utf-8")

        print("\n" + "=" * 70)
        print(f"  {stem}  [{preprocess_tag}]  ->  {out_path}")
        print(f"  words detected: {total_words}  |  "
              f"mean rec confidence: {mean_conf:.3f}")
        print("=" * 70)
        print(text)


if __name__ == "__main__":
    main()
