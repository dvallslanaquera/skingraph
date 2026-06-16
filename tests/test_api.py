# Tests for the FastAPI layer (src/api).
#
# Fully offline like the rest of the suite: the graph is replaced with a stub so
# /scan needs no VLM call or API key, and the user store is pointed at a
# throwaway database so nothing touches data/users.db.
import pytest
from fastapi.testclient import TestClient

from src import user_store
from src.api import service
from src.api.main import app
from src.state import Ingredient, ProductExtraction, SafetyAudit


def _fake_final_state() -> dict:
    """A successful graph result, mirroring the keys run_scan reads."""
    return {
        "is_ready_for_logic": True,
        "trace_id": "trace-123",
        "model_used": "flash",
        "inference_confidence": 0.92,
        "registry_matched": True,
        "ingredient_source": "registry",
        "detected_language": "JP",
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
        "coach_advice": "【日本語】...\n【English】...",
        "routine_recommendations": ["[PRODUCT] Hada — Lotion"],
        "web_sources": [],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with an isolated DB and a stubbed graph."""
    monkeypatch.setattr(user_store, "USER_DB_PATH", str(tmp_path / "api_users.db"))
    monkeypatch.setattr(
        service.graph_app,
        "invoke",
        lambda inputs, config=None: _fake_final_state(),
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
    assert body["added_product_id"] is not None

    # The scanned product was actually persisted to the shelf.
    assert client.get(f"/users/{uid}/routine").json()[0]["product_name"] == "Lotion"


def test_scan_without_user_does_not_save(client):
    resp = client.post("/scan", files={"image": IMAGE})
    assert resp.status_code == 200
    assert resp.json()["added_product_id"] is None


def test_scan_validation_errors(client):
    assert (
        client.post("/scan", files={"image": IMAGE}, data={"image_type": "side"}).status_code
        == 422
    )
    assert (
        client.post("/scan", files={"image": IMAGE}, data={"add_to_routine": "true"}).status_code
        == 422
    )
    assert (
        client.post("/scan", files={"image": IMAGE}, data={"user_id": "nope"}).status_code == 404
    )
    assert (
        client.post("/scan", files={"image": ("e.jpg", b"", "image/jpeg")}).status_code == 400
    )
