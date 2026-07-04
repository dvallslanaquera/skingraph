# Tests for the opt-in OCR cross-check. The heavy OCR engine (yomitoku) is
# never imported here — `_ocr_text` is patched, and the unavailable-engine
# path is exercised by resetting the module's lazy-init globals.
from src import ocr_check


def test_agreement_counts_names_found_in_ocr_text(monkeypatch):
    monkeypatch.setattr(ocr_check, "_ocr_text", lambda path: "水 グリセリン ワセリン")
    agreement = ocr_check.ocr_agreement("x.jpg", ["水", "グリセリン", "存在しない成分XYZ"])
    assert agreement == 2 / 3


def test_agreement_is_fuzzy_not_exact(monkeypatch):
    # partial_ratio absorbs small spelling drift between the two readers.
    monkeypatch.setattr(ocr_check, "_ocr_text", lambda path: "...glycerin, water...")
    assert ocr_check.ocr_agreement("x.jpg", ["Glycerin"]) == 1.0


def test_agreement_none_without_names(monkeypatch):
    monkeypatch.setattr(ocr_check, "_ocr_text", lambda path: "text")
    assert ocr_check.ocr_agreement("x.jpg", []) is None


def test_agreement_none_when_ocr_unavailable(monkeypatch):
    monkeypatch.setattr(ocr_check, "_ocr_text", lambda path: None)
    assert ocr_check.ocr_agreement("x.jpg", ["Water"]) is None


def test_get_analyzer_degrades_gracefully_without_yomitoku(monkeypatch):
    # Fresh lazy-init state; the import inside will fail (yomitoku not a dep).
    monkeypatch.setattr(ocr_check, "_ANALYZER", None)
    monkeypatch.setattr(ocr_check, "_ANALYZER_FAILED", False)
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("yomitoku"):
            raise ImportError("yomitoku not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert ocr_check._get_analyzer() is None
    assert ocr_check._ANALYZER_FAILED is True
    # And the public API stays quiet about it.
    ocr_check._ocr_text.cache_clear()
    assert ocr_check.ocr_agreement("x.jpg", ["Water"]) is None
