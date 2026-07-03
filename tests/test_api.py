# Tests for the FastAPI layer (src/api).
#
# Fully offline like the rest of the suite: the graph is replaced with a stub so
# /scan needs no VLM call or API key, and the user store is pointed at a
# throwaway database so nothing touches data/users.db.
import json

import pytest
from fastapi.testclient import TestClient

from src import user_store
from src.api import service
from src.api.main import app
from src.state import CoachResponse, Ingredient, ProductExtraction, Recommendation, SafetyAudit


def _fake_final_state() -> dict:
    """A successful graph result, mirroring the keys run_scan reads."""
    return {
        "is_ready_for_logic": True,
        "trace_id": "trace-123",
        "model_used": "flash",
        "inference_confidence": 0.92,
        "registry_matched": True,
        "ingredient_source": "registry",
        "extracted_data": ProductExtraction(
            brand="Hada",
            product_name="Lotion",
            ingredients=[Ingredient(name_raw="水")],
            source_language="JP",
            extraction_confidence=0.92,
            system_status="SUCCESS",
        ),
        "standardized_ingredients": [
            {
                "name_raw": "水",
                "name_standardized": "Water",
                "is_active": False,
                "source_language": "JP",
            }
        ],
        "unmatched_ingredients": [],
        "safety_report": SafetyAudit(),
        "routine_fit": None,
        "coach_cards": CoachResponse(
            japanese=Recommendation(
                verdict="乾燥肌にうれしい保湿ローションです。",
                product="Hada — Lotion",
                purpose="うるおいを与える",
                timing="AM & PM",
                frequency="毎日",
                application_notes=["湿った肌になじませてください"],
            ),
            english=Recommendation(
                verdict="A gentle hydrating lotion for dry skin.",
                product="Hada — Lotion",
                purpose="Provides moisture",
                timing="AM & PM",
                frequency="Daily",
                application_notes=["Apply to slightly damp skin"],
            ),
        ),
        "web_sources": [],
    }


def _fake_stream():
    """Mimic graph_app.stream(stream_mode=["updates","values"]): yield
    (mode, chunk) tuples, ending with the full final state on a "values" frame."""
    yield ("updates", {"flash_scanner": {}})
    yield ("values", _fake_final_state())


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with an isolated DB and a stubbed graph."""
    monkeypatch.setattr(user_store, "USER_DB_PATH", str(tmp_path / "api_users.db"))
    # init_db() runs once per process; re-arm it for the fresh database.
    monkeypatch.setattr(user_store, "_initialized", False)
    monkeypatch.setattr(
        service.graph_app,
        "invoke",
        lambda inputs, config=None: _fake_final_state(),
    )
    # The streaming endpoint drives graph_app.stream(...) instead of .invoke.
    monkeypatch.setattr(
        service.graph_app,
        "stream",
        lambda inputs, config=None, stream_mode=None: _fake_stream(),
    )
    with TestClient(app) as c:  # triggers lifespan → init_db()
        yield c


# A minimal JPEG-ish payload; the graph is stubbed so the bytes are never read.
IMAGE = ("label.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")


def _make_user(client, name="Aiko", skin_type="dry") -> str:
    resp = client.post(
        "/users", json={"name": name, "profile": {"skin_type": skin_type, "goals": ["hydration"]}}
    )
    assert resp.status_code == 201
    return resp.json()["user_id"]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_user_crud_round_trip(client):
    uid = _make_user(client)

    assert any(u["user_id"] == uid for u in client.get("/users").json())
    assert client.get(f"/users/{uid}").json()["profile"]["skin_type"] == "dry"

    updated = client.put(
        f"/users/{uid}", json={"name": "Aiko M", "profile": {"skin_type": "oily", "goals": []}}
    )
    assert updated.status_code == 200
    assert updated.json()["profile"]["skin_type"] == "oily"

    assert client.delete(f"/users/{uid}").status_code == 204
    assert client.get(f"/users/{uid}").status_code == 404


def test_get_unknown_user_404(client):
    assert client.get("/users/does-not-exist").status_code == 404


def test_routine_add_list_remove(client):
    uid = _make_user(client)

    add = client.post(
        f"/users/{uid}/routine",
        json={"brand": "X", "product_name": "Serum", "ingredients": ["Niacinamide"]},
    )
    assert add.status_code == 201
    pid = add.json()["product_id"]

    listing = client.get(f"/users/{uid}/routine").json()
    assert listing[0]["product_name"] == "Serum"
    assert listing[0]["ingredients"] == ["Niacinamide"]

    assert client.delete(f"/routine/{pid}").status_code == 204
    assert client.delete(f"/routine/{pid}").status_code == 404


def test_routine_for_unknown_user_404(client):
    assert client.get("/users/nope/routine").status_code == 404
    assert (
        client.post("/users/nope/routine", json={"brand": "B", "product_name": "P"}).status_code
        == 404
    )


def test_scan_success_and_adds_to_routine(client):
    uid = _make_user(client)

    resp = client.post(
        "/scan", files={"image": IMAGE}, data={"user_id": uid, "add_to_routine": "true"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert body["product"]["brand"] == "Hada"
    assert body["standardized_ingredients"][0]["name_standardized"] == "Water"
    assert body["coach"]["english"]["verdict"].startswith("A gentle hydrating")
    assert body["coach"]["japanese"]["timing"] == "AM & PM"
    assert body["added_product_id"] is not None

    # The scanned product was actually persisted to the shelf, carrying the
    # coach card's timing and per-language application notes.
    saved = client.get(f"/users/{uid}/routine").json()[0]
    assert saved["product_name"] == "Lotion"
    assert saved["timing"] == "AM & PM"
    assert saved["application_notes"] == ["Apply to slightly damp skin"]


def test_scan_without_user_does_not_save(client):
    resp = client.post("/scan", files={"image": IMAGE})
    assert resp.status_code == 200
    assert resp.json()["added_product_id"] is None


def test_scan_validation_errors(client):
    assert (
        client.post("/scan", files={"image": IMAGE}, data={"image_type": "side"}).status_code == 422
    )
    assert (
        client.post("/scan", files={"image": IMAGE}, data={"add_to_routine": "true"}).status_code
        == 422
    )
    assert client.post("/scan", files={"image": IMAGE}, data={"user_id": "nope"}).status_code == 404
    assert client.post("/scan", files={"image": ("e.jpg", b"", "image/jpeg")}).status_code == 400


# --- /scan/stream (SSE) ------------------------------------------------------


def _sse_events(resp) -> list[dict]:
    """Parse the SSE body into a list of decoded event payloads."""
    events = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def test_scan_stream_emits_stages_then_complete(client):
    resp = client.post("/scan/stream", files={"image": IMAGE})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(resp)
    kinds = [e["event"] for e in events]
    assert "stage" in kinds  # real per-node progress
    assert kinds[-1] == "complete"  # final full ScanResponse last

    complete = events[-1]["data"]
    assert complete["status"] == "complete"
    assert complete["product"]["brand"] == "Hada"
    assert complete["coach"]["english"]["verdict"].startswith("A gentle hydrating")


def test_scan_stream_adds_to_routine(client):
    uid = _make_user(client)
    resp = client.post(
        "/scan/stream",
        files={"image": IMAGE},
        data={"user_id": uid, "add_to_routine": "true"},
    )
    assert resp.status_code == 200
    events = _sse_events(resp)
    complete = events[-1]["data"]
    assert complete["added_product_id"] is not None
    assert client.get(f"/users/{uid}/routine").json()[0]["product_name"] == "Lotion"


def test_scan_stream_without_user_does_not_save(client):
    resp = client.post("/scan/stream", files={"image": IMAGE})
    events = _sse_events(resp)
    assert events[-1]["data"]["added_product_id"] is None


def test_scan_stream_surfaces_failures_as_error_not_silent_eof(client, monkeypatch):
    # A failure in the graph must reach the client as an `error` frame, never a
    # silent stream end (which the UI reports as "Stream ended without a result").
    def _boom(inputs, config=None, stream_mode=None):
        raise RuntimeError("worker exploded")

    monkeypatch.setattr(service.graph_app, "stream", _boom)
    resp = client.post("/scan/stream", files={"image": IMAGE})
    assert resp.status_code == 200
    events = _sse_events(resp)
    kinds = [e["event"] for e in events]
    assert "error" in kinds
    assert "complete" not in kinds
    assert "worker exploded" in events[-1]["message"]


def test_scan_stream_validation_errors(client):
    assert (
        client.post("/scan/stream", files={"image": IMAGE}, data={"image_type": "side"}).status_code
        == 422
    )
    assert (
        client.post(
            "/scan/stream", files={"image": IMAGE}, data={"add_to_routine": "true"}
        ).status_code
        == 422
    )
    assert (
        client.post("/scan/stream", files={"image": ("e.jpg", b"", "image/jpeg")}).status_code
        == 400
    )


# --- /scan/followup -----------------------------------------------------------


def _followup_body(**overrides) -> dict:
    body = {
        "brand": "Hada",
        "product_name": "Lotion",
        "standardized_ingredients": [{"name_raw": "水", "name_standardized": "Water"}],
        "question": "Can I use this with vitamin C?",
        "lang": "en",
    }
    body.update(overrides)
    return body


def test_followup_returns_answer(client, monkeypatch):
    captured = {}

    def fake_answer(**kwargs):
        captured.update(kwargs)
        return "A grounded answer."

    monkeypatch.setattr(service, "answer_followup", fake_answer)
    resp = client.post("/scan/followup", json=_followup_body())

    assert resp.status_code == 200
    assert resp.json() == {"answer": "A grounded answer."}
    # The scan grounding travelled through to the answer builder.
    assert captured["brand"] == "Hada"
    assert captured["standardized_ingredients"][0]["name_standardized"] == "Water"
    assert captured["lang"] == "en"


def test_followup_loads_user_context(client, monkeypatch):
    uid = _make_user(client)
    captured = {}

    def fake_answer(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(service, "answer_followup", fake_answer)
    resp = client.post("/scan/followup", json=_followup_body(user_id=uid))

    assert resp.status_code == 200
    assert captured["profile"] is not None
    assert captured["profile"].skin_type == "dry"


def test_followup_unknown_user_is_404(client):
    resp = client.post("/scan/followup", json=_followup_body(user_id="nope"))
    assert resp.status_code == 404


def test_followup_blank_question_is_422(client):
    assert client.post("/scan/followup", json=_followup_body(question="   ")).status_code == 422
    assert client.post("/scan/followup", json=_followup_body(question="")).status_code == 422
