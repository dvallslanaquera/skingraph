# Tests for the router threshold sweep's pure logic (eval/sweep.py): the
# per-threshold cascade decision, the Pareto frontier, and the pick helper.
# Cassette I/O is not exercised here (that needs recorded flash+pro pairs).
from eval import sweep
from src.state import Ingredient, ProductExtraction


def _ext(conf: float, names: list[str]) -> ProductExtraction:
    return ProductExtraction(
        brand="B",
        product_name="P",
        ingredients=[Ingredient(name_raw=n, name_standardized=n) for n in names],
        source_language="JP",
        extraction_confidence=conf,
        system_status="SUCCESS",
    )


def _entry(id_="p1", truth=None) -> dict:
    truth = truth or ["Water", "Glycerin"]
    return {
        "id": id_,
        "metadata": {"file_name": f"{id_}.jpg", "difficulty_score": 1},
        "ground_truth": {
            "brand_name": "B",
            "product_name": "P",
            "is_medicated_quasi_drug": False,
            "full_ingredient_list": truth,
            "ingredient_inci": truth,
        },
    }


def _pair(id_, flash_conf, flash_names, pro_names, flash_cost=0.004, pro_cost=0.03):
    entry = _entry(id_)
    return {
        "id": id_,
        "entry": entry,
        "flash": {
            "extraction": _ext(flash_conf, flash_names),
            "confidence": flash_conf,
            "cost_usd": flash_cost,
        },
        "pro": {"extraction": _ext(0.95, pro_names), "confidence": 0.95, "cost_usd": pro_cost},
    }


def test_low_threshold_never_escalates():
    # Flash confidence 0.6; at tau=0.5 the cascade keeps Flash (no escalation).
    pairs = [_pair("p1", 0.6, ["Water"], ["Water", "Glycerin"])]
    point = sweep.score_at_threshold(pairs, 0.5, 85, 0.004, 0.03)
    assert point["escalation_rate"] == 0.0
    assert point["cost_per_scan"] == 0.004  # flash only


def test_high_threshold_escalates_and_pays_both():
    # tau above flash confidence → escalate; the cascade pays flash + pro.
    pairs = [_pair("p1", 0.6, ["Water"], ["Water", "Glycerin"])]
    point = sweep.score_at_threshold(pairs, 0.9, 85, 0.004, 0.03)
    assert point["escalation_rate"] == 1.0
    assert abs(point["cost_per_scan"] - (0.004 + 0.03)) < 1e-9
    # Pro read the full list, so escalating lifts F1 to 1.0.
    assert point["f1"] == 1.0


def test_missing_recorded_cost_uses_defaults():
    pair = _pair("p1", 0.6, ["Water"], ["Water"], flash_cost=None, pro_cost=None)
    point = sweep.score_at_threshold([pair], 0.5, 85, 0.007, 0.05)
    assert point["cost_per_scan"] == 0.007


def test_pareto_front_drops_dominated_points():
    points = [
        {"tau": 0.1, "f1": 0.80, "cost_per_scan": 0.010, "escalation_rate": 0.0},
        {
            "tau": 0.5,
            "f1": 0.90,
            "cost_per_scan": 0.010,
            "escalation_rate": 0.2,
        },  # dominates the first
        {"tau": 0.9, "f1": 0.92, "cost_per_scan": 0.030, "escalation_rate": 1.0},
    ]
    front = sweep.pareto_front(points)
    taus = {p["tau"] for p in front}
    assert 0.1 not in taus  # dominated: same cost, lower F1
    assert 0.5 in taus and 0.9 in taus


def test_cheapest_meeting_bar_picks_lowest_cost_qualifier():
    points = [
        {"tau": 0.5, "f1": 0.90, "cost_per_scan": 0.010, "escalation_rate": 0.2},
        {"tau": 0.9, "f1": 0.92, "cost_per_scan": 0.030, "escalation_rate": 1.0},
    ]
    pick = sweep.cheapest_meeting_bar(points, 0.90)
    assert pick["tau"] == 0.5


def test_cheapest_meeting_bar_none_when_unreachable():
    points = [{"tau": 0.5, "f1": 0.80, "cost_per_scan": 0.01, "escalation_rate": 0.0}]
    assert sweep.cheapest_meeting_bar(points, 0.95) is None
