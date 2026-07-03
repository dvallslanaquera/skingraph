# Tests for the eval replay gate (eval/evaluate.py) — the cassette staleness
# guard and the F1 floor. Fully offline: cassettes are synthesised into a tmp
# dir; the VLM is never touched (replay skips it by design).
import argparse
import json

import pytest

from eval import evaluate
from src.state import Ingredient, ProductExtraction


def _extraction(**overrides) -> ProductExtraction:
    fields = {
        "brand": "Hada",
        "product_name": "Lotion",
        "ingredients": [Ingredient(name_raw="水", name_standardized="Water")],
        "is_quasi_drug": False,
        "source_language": "JP",
        "extraction_confidence": 0.95,
        "system_status": "SUCCESS",
    }
    fields.update(overrides)
    return ProductExtraction(**fields)


def _entry(id_="prod_x", file_name="prod_x.jpg") -> dict:
    return {
        "id": id_,
        "metadata": {"file_name": file_name, "difficulty_score": 1},
        "ground_truth": {
            "brand_name": "Hada",
            "product_name": "Lotion",
            "is_medicated_quasi_drug": False,
            "full_ingredient_list": ["水"],
            "ingredient_inci": ["Water"],
        },
    }


@pytest.fixture
def cassette_dir(tmp_path, monkeypatch):
    """Point the harness at a throwaway cassette dir."""
    d = tmp_path / "cassettes"
    d.mkdir()
    monkeypatch.setattr(evaluate, "CASSETTE_DIR", str(d))
    monkeypatch.setattr(evaluate, "MANIFEST_PATH", str(d / "manifest.json"))
    return d


def _write_cassette_file(cassette_dir, entry, *, prompt_sha=None, model_id=None):
    payload = {
        "id": entry["id"],
        "image_sha256": "irrelevant-image-absent",
        "model_id": model_id or evaluate.MODEL_IDS["flash"],
        "prompt_sha256": prompt_sha or evaluate._prompt_sha256(),
        "recorded_at": "2026-07-03T00:00:00+00:00",
        "extraction": _extraction().model_dump(),
    }
    stem = entry["metadata"]["file_name"].rsplit(".", 1)[0]
    path = cassette_dir / f"{stem}.flash.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_manifest(cassette_dir, ids):
    manifest = {
        "prompt_sha256": evaluate._prompt_sha256(),
        "threshold": 85,
        "models": {"flash": {"model_id": evaluate.MODEL_IDS["flash"], "ids": ids}},
    }
    (cassette_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _args(**overrides) -> argparse.Namespace:
    ns = argparse.Namespace(model="flash", threshold=85, ids=None, min_f1=None)
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_replay_scores_fresh_cassette(cassette_dir):
    entry = _entry()
    _write_cassette_file(cassette_dir, entry)
    _write_manifest(cassette_dir, [entry["id"]])

    results = evaluate.run_replay({entry["id"]: entry}, _args())

    assert len(results) == 1
    assert results[0]["ingredients"]["f1"] == 1.0


def test_replay_fails_on_stale_prompt_hash(cassette_dir):
    entry = _entry()
    _write_cassette_file(cassette_dir, entry, prompt_sha="0" * 64)
    _write_manifest(cassette_dir, [entry["id"]])

    with pytest.raises(SystemExit, match="STALE CASSETTE"):
        evaluate.run_replay({entry["id"]: entry}, _args())


def test_replay_fails_on_model_change(cassette_dir):
    entry = _entry()
    _write_cassette_file(cassette_dir, entry, model_id="gemini-some-older-model")
    _write_manifest(cassette_dir, [entry["id"]])

    with pytest.raises(SystemExit, match="STALE CASSETTE"):
        evaluate.run_replay({entry["id"]: entry}, _args())


def test_replay_fails_on_ground_truth_drift(cassette_dir):
    entry = _entry()
    _write_cassette_file(cassette_dir, entry)
    _write_manifest(cassette_dir, [entry["id"]])

    with pytest.raises(SystemExit, match="ground_truth"):
        evaluate.run_replay({}, _args())  # id no longer annotated


def test_replay_fails_on_missing_cassette(cassette_dir):
    entry = _entry()
    _write_manifest(cassette_dir, [entry["id"]])

    with pytest.raises(SystemExit, match="Cassette missing"):
        evaluate.run_replay({entry["id"]: entry}, _args())


def test_gate_passes_at_or_above_floor(capsys):
    results = [
        {
            "ingredients": {"f1": 0.95, "recall": 0.9},
            "brand_score": 100.0,
            "product_score": 100.0,
            "quasi_drug_correct": True,
        }
    ]
    evaluate.apply_gate(results, 0.90)
    assert "EVAL GATE PASSED" in capsys.readouterr().out


def test_gate_fails_below_floor():
    results = [
        {
            "ingredients": {"f1": 0.5, "recall": 0.5},
            "brand_score": 100.0,
            "product_score": 100.0,
            "quasi_drug_correct": True,
        }
    ]
    with pytest.raises(SystemExit, match="EVAL GATE FAILED"):
        evaluate.apply_gate(results, 0.90)


def test_gate_fails_on_empty_results():
    with pytest.raises(SystemExit, match="no cassettes"):
        evaluate.apply_gate([], 0.90)
