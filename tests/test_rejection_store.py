# Tests for the opt-in rejection flywheel: disabled by default, bounded when on.
import json

from src import config, rejection_store
from src.nodes.normalizer import ledger_match


def _enable(monkeypatch, tmp_path, max_captures=200):
    monkeypatch.setattr(config, "REJECTION_STORE_ENABLED", True)
    monkeypatch.setattr(config, "REJECTION_STORE_PATH", str(tmp_path / "rejections"))
    monkeypatch.setattr(config, "REJECTION_STORE_MAX", max_captures)


def _fake_image(tmp_path, name="frame.jpg"):
    path = tmp_path / name
    path.write_bytes(b"fake image bytes")
    return str(path)


def test_disabled_store_is_a_noop(tmp_path):
    # Default config: disabled → returns None and creates nothing.
    assert not config.REJECTION_STORE_ENABLED
    assert rejection_store.record_rejection(_fake_image(tmp_path), "too_dark") is None
    assert not (tmp_path / "rejections").exists()


def test_capture_writes_image_and_sidecar(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    capture_id = rejection_store.record_rejection(
        _fake_image(tmp_path), "blurry", {"trace_id": "t-9", "classify_confidence": 0.4}
    )
    assert capture_id is not None

    store = tmp_path / "rejections"
    image = store / f"{capture_id}.jpg"
    sidecar = store / f"{capture_id}.json"
    assert image.read_bytes() == b"fake image bytes"
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["reason"] == "blurry"
    assert meta["trace_id"] == "t-9"


def test_store_prunes_oldest_beyond_cap(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path, max_captures=2)
    ids = [
        rejection_store.record_rejection(_fake_image(tmp_path, f"f{i}.jpg"), "blank")
        for i in range(4)
    ]
    remaining = {p.stem for p in (tmp_path / "rejections").iterdir()}
    # Only the newest two captures (image + sidecar each) survive.
    assert remaining == set(ids[-2:])


def test_capture_failure_is_swallowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    # Nonexistent source file → copy fails → logged, not raised.
    assert rejection_store.record_rejection(str(tmp_path / "missing.jpg"), "x") is None


# --------------------------------------------------------------------------- #
# ledger_match (the grounded signal the scanners record)
# --------------------------------------------------------------------------- #
def test_ledger_match_rates_known_names():
    import pytest

    rate, unmatched = ledger_match(["水", "グリセリン", "ZZ_NOT_REAL"])
    assert rate == pytest.approx(2 / 3)
    assert unmatched == ["ZZ_NOT_REAL"]


def test_ledger_match_empty_is_no_signal():
    assert ledger_match([]) == (None, [])
