# Tests for the SQLite routine store (the per-user "shelf").
#
# Each test runs against a throwaway database file so nothing touches the real
# data/users.db.
import pytest

from src import user_store
from src.state import CoachResponse, Recommendation
from tests.helpers import make_extraction, std_ingredients


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the store at an isolated temp database for the duration of a test."""
    db = tmp_path / "test_users.db"
    monkeypatch.setattr(user_store, "USER_DB_PATH", str(db))
    # init_db() runs once per process; re-arm it for the fresh database.
    monkeypatch.setattr(user_store, "_initialized", False)
    return str(db)


def test_add_and_get_routine_round_trip(temp_db):
    pid = user_store.add_routine_product(
        "user-1", "Acme", "Peel", ["Glycolic Acid", "Water"], is_quasi_drug=False
    )
    routine = user_store.get_routine("user-1")

    assert len(routine) == 1
    prod = routine[0]
    assert prod.product_id == pid
    assert prod.brand == "Acme"
    assert prod.product_name == "Peel"
    assert prod.ingredients == ["Glycolic Acid", "Water"]
    assert prod.is_quasi_drug is False


def test_add_routine_dedupes_same_product_and_refreshes(temp_db):
    pid1 = user_store.add_routine_product("user-1", "Acme", "Peel", ["Glycolic Acid"])
    pid2 = user_store.add_routine_product("user-1", "  acme ", "PEEL", ["Lactic Acid", "Water"])

    routine = user_store.get_routine("user-1")
    assert len(routine) == 1  # deduped on case/space-insensitive identity
    assert pid1 == pid2  # same row reused
    assert routine[0].ingredients == ["Lactic Acid", "Water"]  # ingredients refreshed


def test_remove_routine_product(temp_db):
    pid = user_store.add_routine_product("user-1", "Acme", "Peel", ["Glycolic Acid"])
    assert user_store.remove_routine_product(pid) is True
    assert user_store.get_routine("user-1") == []
    # Removing again is a no-op.
    assert user_store.remove_routine_product(pid) is False


def test_get_routine_empty_for_unknown_user(temp_db):
    assert user_store.get_routine("nobody") == []


def test_routine_is_scoped_per_user(temp_db):
    user_store.add_routine_product("user-1", "Acme", "Peel", ["Glycolic Acid"])
    user_store.add_routine_product("user-2", "Bright", "Serum", ["Ascorbic Acid"])

    r1 = user_store.get_routine("user-1")
    r2 = user_store.get_routine("user-2")
    assert [p.product_name for p in r1] == ["Peel"]
    assert [p.product_name for p in r2] == ["Serum"]


def test_is_quasi_drug_none_round_trips(temp_db):
    user_store.add_routine_product("user-1", "Acme", "Toner", ["Water"])
    assert user_store.get_routine("user-1")[0].is_quasi_drug is None


def test_save_scanned_product_carries_coach_card_onto_shelf(temp_db, monkeypatch):
    monkeypatch.setattr(user_store, "_lookup_price_safe", lambda *a: None)
    final_state = {
        "is_ready_for_logic": True,
        "extracted_data": make_extraction(brand="Hada", product_name="Lotion"),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "coach_cards": CoachResponse(
            japanese=Recommendation(timing="PM", application_notes=["夜に使用"]),
            english=Recommendation(timing="PM", application_notes=["Use at night"]),
        ),
    }
    pid = user_store.save_scanned_product("user-1", final_state)

    saved = user_store.get_routine("user-1")[0]
    assert saved.product_id == pid
    assert saved.timing == "PM"
    assert saved.application_notes == ["Use at night"]
    assert saved.application_notes_ja == ["夜に使用"]


def test_save_scanned_product_skips_unready_scans(temp_db):
    final_state = {"is_ready_for_logic": False, "extracted_data": None}
    assert user_store.save_scanned_product("user-1", final_state) is None
    assert user_store.get_routine("user-1") == []
