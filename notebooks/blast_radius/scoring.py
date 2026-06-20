"""Score model answers against the oracle, at file and line granularity.

We report two levels:

* **File level** — did the model name the right *set of files*? This is the headline
  metric: it captures "if I change X, which files do I open?", which is the question a
  refactoring engineer actually asks, and it is robust to off-by-one line drift.
* **Line level** — did it pin the exact ``(file, line)``? Stricter; rewards a model
  that can read precise locations out of a huge context (the dump hands it line
  numbers, so this is a fair ask, not a counting puzzle).

For each we compute precision (did it avoid hallucinating references?), recall (did it
find them all?), and F1.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .oracle import SymbolOracle


def normalize_path(path: str) -> str:
    """Canonicalize a model-supplied path: backslashes→slashes, strip ./ and quotes."""
    p = path.strip().strip("`'\"").replace("\\", "/")
    p = re.sub(r"^\./+", "", p)
    return p.lstrip("/")


@dataclass(frozen=True)
class Score:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    n_pred: int
    n_truth: int

    def as_dict(self) -> dict:
        return asdict(self)


def _prf(pred: set, truth: set) -> Score:
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    # No predictions ⇒ no false positives ⇒ precision is vacuously 1.0 (recall carries
    # the penalty). No truth ⇒ recall is vacuously 1.0.
    precision = tp / len(pred) if pred else 1.0
    recall = tp / len(truth) if truth else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return Score(precision, recall, f1, tp, fp, fn, len(pred), len(truth))


def score_symbol(
    predictions: list[dict], oracle: SymbolOracle
) -> dict[str, Score]:
    """Score one symbol's predictions. ``predictions`` is a list of {file, line}."""
    pred_files: set[str] = set()
    pred_lines: set[tuple[str, int]] = set()
    for ref in predictions:
        f = normalize_path(str(ref.get("file", "")))
        if not f:
            continue
        pred_files.add(f)
        line = ref.get("line")
        if isinstance(line, int) or (isinstance(line, str) and str(line).isdigit()):
            pred_lines.add((f, int(line)))

    return {
        "file": _prf(pred_files, oracle.files),
        "line": _prf(pred_lines, oracle.line_keys),
    }


def macro_average(scores: list[Score]) -> Score:
    """Unweighted mean across symbols (each symbol counts equally)."""
    if not scores:
        return Score(0, 0, 0, 0, 0, 0, 0, 0)
    n = len(scores)
    return Score(
        precision=sum(s.precision for s in scores) / n,
        recall=sum(s.recall for s in scores) / n,
        f1=sum(s.f1 for s in scores) / n,
        tp=sum(s.tp for s in scores),
        fp=sum(s.fp for s in scores),
        fn=sum(s.fn for s in scores),
        n_pred=sum(s.n_pred for s in scores),
        n_truth=sum(s.n_truth for s in scores),
    )


def micro_average(pred_truth_pairs: list[tuple[set, set]]) -> Score:
    """Pool every (pred, truth) set across symbols, then compute one P/R/F1.

    Micro-averaging weights symbols by how many references they have, so a wide-blast
    symbol like ``UserProfile`` counts more than a 3-line constant. Each symbol's
    elements are namespaced with its index so identical references across different
    symbols don't collide when pooled.
    """
    pooled_pred: set = set()
    pooled_truth: set = set()
    for idx, (pred, truth) in enumerate(pred_truth_pairs):
        pooled_pred |= {(idx, elem) for elem in pred}
        pooled_truth |= {(idx, elem) for elem in truth}
    return _prf(pooled_pred, pooled_truth)
