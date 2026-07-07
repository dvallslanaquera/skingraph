# Tests for the eval scorecard (eval/scorecard.py): markdown rendering, badge
# colour bands, badge/history files, and the $GITHUB_STEP_SUMMARY sink.
import json

from eval import scorecard


def _res(id_, f1, conf=0.9):
    return {
        "id": id_,
        "confidence": conf,
        "system_status": "SUCCESS",
        "brand_score": 100.0,
        "product_score": 95.0,
        "quasi_drug_correct": True,
        "ingredients": {
            "precision": f1,
            "recall": f1,
            "f1": f1,
            "missed": [],
            "hallucinated": [],
        },
    }


def test_color_bands():
    assert scorecard._color(0.95, 0.9, 0.8) == "brightgreen"
    assert scorecard._color(0.85, 0.9, 0.8) == "green"
    assert scorecard._color(0.75, 0.9, 0.8) == "yellow"
    assert scorecard._color(0.50, 0.9, 0.8) == "red"


def test_render_markdown_has_aggregate_and_rows():
    md = scorecard.render_markdown([_res("prod_001", 0.95), _res("prod_002", 0.90)], "flash", 0.90)
    assert "Aggregate F1" in md
    assert "gate **PASS**" in md
    assert "`prod_001`" in md


def test_render_markdown_gate_fail():
    md = scorecard.render_markdown([_res("prod_001", 0.5)], "flash", 0.90)
    assert "gate **FAIL**" in md


def test_write_badges(tmp_path):
    scorecard.write_badges([_res("a", 0.925)], str(tmp_path))
    body = json.loads((tmp_path / "ingredient_f1.json").read_text(encoding="utf-8"))
    assert body["schemaVersion"] == 1
    assert body["message"] == "0.925"
    assert body["color"] == "brightgreen"


def test_append_history(tmp_path):
    path = tmp_path / "history.jsonl"
    scorecard.append_history([_res("a", 0.9)], "flash", str(path), "abc123")
    scorecard.append_history([_res("a", 0.95)], "flash", str(path), "def456")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["commit"] == "abc123"
    assert rows[1]["ingredient_f1"] == 0.95


def test_write_summary_appends_to_github_step_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    scorecard.write_summary("### hello scorecard")
    assert "hello scorecard" in summary.read_text(encoding="utf-8")


def test_write_summary_prints_without_ci(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    scorecard.write_summary("### local scorecard")
    assert "local scorecard" in capsys.readouterr().out
