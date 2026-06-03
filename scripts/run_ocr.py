"""Standalone Japanese OCR ingest path (Phase 0 — NOT wired into the graph).

Runs YomiToku's DocumentAnalyzer over the annotated golden images and writes
the raw extracted text to data/ocr_out/<id>.txt, printing each to stdout.

DocumentAnalyzer (rather than bare OCR) is used on purpose: it runs a layout
model and reconstructs reading order, so the dense 全成分 ingredient block
comes out as ordered text instead of scrambled detection-order words.

Usage:
    poetry run python scripts/run_ocr.py                  # prod_001, prod_002
    poetry run python scripts/run_ocr.py --id prod_001    # one image
    poetry run python scripts/run_ocr.py --device cuda     # if a GPU exists

First run downloads model weights (hundreds of MB, slow once, then cached).
"""
import argparse
import sys
from pathlib import Path

from yomitoku import DocumentAnalyzer
from yomitoku.data.functions import load_image

GOLDEN_DIR = Path("data/golden_set")
OUT_DIR = Path("data/ocr_out")
DEFAULT_IDS = ["prod_001", "prod_002"]


def extract_text(results) -> str:
    """Join paragraphs in reading order; fall back to raw words if empty."""
    paragraphs = [p for p in results.paragraphs if p.contents]
    if paragraphs:
        paragraphs.sort(key=lambda p: p.order if p.order is not None else 1 << 30)
        return "\n".join(p.contents for p in paragraphs)
    # Layout model found no paragraphs — emit raw OCR words so nothing is lost.
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
    return parser.parse_args()


def main() -> None:
    # Windows consoles default to a legacy code page; force UTF-8 so Japanese
    # text prints instead of mojibake.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    ids = args.ids or DEFAULT_IDS
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading YomiToku DocumentAnalyzer on device={args.device} "
          "(first run downloads weights)...", flush=True)
    analyzer = DocumentAnalyzer(visualize=False, device=args.device)

    for stem in ids:
        img_path = GOLDEN_DIR / f"{stem}.jpg"
        if not img_path.exists():
            print(f"!! Skipping {stem}: image not found at {img_path}", flush=True)
            continue

        # load_image returns a list of page-images (PDF-style); a JPEG is one page.
        pages = load_image(str(img_path))
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

        out_path = OUT_DIR / f"{stem}.txt"
        out_path.write_text(text, encoding="utf-8")

        print("\n" + "=" * 70)
        print(f"  {stem}  ->  {out_path}")
        print(f"  words detected: {total_words}  |  "
              f"mean rec confidence: {mean_conf:.3f}")
        print("=" * 70)
        print(text)


if __name__ == "__main__":
    main()
