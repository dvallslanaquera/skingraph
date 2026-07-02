# Tests for the coach node.
#
# The Gemini call is mocked; the focus is the deterministic, safety-critical
# logic the coach computes itself (pregnancy / dehydration / sun-sensitivity
# cautions, warning ordering, and anonymous score suppression) rather than the
# model's free text.
from unittest.mock import MagicMock

import pytest

from src.nodes import coach
from src.state import (CoachResponse, CrossConflict, Recommendation,
                       RoutineFit, RoutineFitCard, RoutineProduct, SafetyAudit,
                       UserProfile)

from tests.helpers import make_extraction, std_ingredients


# --------------------------------------------------------------------------- #
# _dehydration_sun_flags
# --------------------------------------------------------------------------- #
def test_no_flags_for_clean_ingredients():
    state = {"standardized_ingredients": std_ingredients(("水", "Water"))}
    ja, en = coach._dehydration_sun_flags(state)
    assert ja == [] and en == []


def test_drying_ingredient_raises_dehydration_caution():
    state = {"standardized_ingredients": std_ingredients(("変性アルコール", "Alcohol Denat."))}
    ja, en = coach._dehydration_sun_flags(state)
    assert any("Dehydration caution" in line and "Alcohol Denat." in line for line in en)
    assert any("乾燥に注意" in line for line in ja)


def test_photosensitising_ingredient_raises_sun_caution():
    state = {"standardized_ingredients": std_ingredients(("レチノール", "Retinol"))}
    ja, en = coach._dehydration_sun_flags(state)
    assert any("Sun-sensitivity caution" in line and "Retinol" in line for line in en)
    assert any("紫外線に注意" in line for line in ja)


# --------------------------------------------------------------------------- #
# _introduction_pacing_flags
# --------------------------------------------------------------------------- #
def test_pacing_flag_fires_for_sensitive_skin_with_strong_active():
    # Retinol is a Retinoids marker; sensitive skin triggers the one-at-a-time
    # patch-test caution even with an empty shelf.
    state = {"standardized_ingredients": std_ingredients(("レチノール", "Retinol"))}
    ja, en = coach._introduction_pacing_flags(state, UserProfile(skin_type="sensitive"))
    assert any("patch-test" in line.lower() for line in en)
    assert any("パッチテスト" in line for line in ja)


def test_pacing_flag_fires_when_shelf_already_has_strong_active():
    state = {
        "standardized_ingredients": std_ingredients(("レチノール", "Retinol")),
        "routine_products": [
            RoutineProduct(
                product_id="p1", brand="B", product_name="Peel",
                ingredients=["Salicylic Acid"],  # a BHA already on the shelf
            )
        ],
    }
    ja, en = coach._introduction_pacing_flags(state, UserProfile(skin_type="dry"))
    assert ja and en


def test_no_pacing_flag_without_shelf_strong_active_or_sensitivity():
    state = {"standardized_ingredients": std_ingredients(("レチノール", "Retinol"))}
    ja, en = coach._introduction_pacing_flags(state, UserProfile(skin_type="dry"))
    assert ja == [] and en == []


def test_no_pacing_flag_when_product_has_no_strong_active():
    state = {"standardized_ingredients": std_ingredients(("水", "Water"))}
    ja, en = coach._introduction_pacing_flags(
        state, UserProfile(skin_type="sensitive")
    )
    assert ja == [] and en == []


# --------------------------------------------------------------------------- #
# _pregnancy_cautions
# --------------------------------------------------------------------------- #
def test_no_pregnancy_caution_without_profile():
    assert coach._pregnancy_cautions({}, None) == ([], [])


def test_no_pregnancy_caution_when_not_pregnant():
    profile = UserProfile(is_pregnant=False)
    assert coach._pregnancy_cautions({}, profile) == ([], [])


def test_pregnancy_generic_caution_when_no_flagged_ingredient():
    state = {"standardized_ingredients": std_ingredients(("水", "Water"))}
    ja, en = coach._pregnancy_cautions(state, UserProfile(is_pregnant=True))
    assert len(ja) == 1 and len(en) == 1
    assert "医師にご相談" in ja[0]
    assert "consult a doctor" in en[0].lower()


def test_pregnancy_names_flagged_ingredient():
    state = {"standardized_ingredients": std_ingredients(("レチノール", "Retinol"))}
    ja, en = coach._pregnancy_cautions(state, UserProfile(is_pregnant=True))
    assert "Retinol" in en[0]
    assert "Retinol" in ja[0]


# --------------------------------------------------------------------------- #
# coach_node
# --------------------------------------------------------------------------- #
def test_coach_node_placeholder_without_safety_report():
    result = coach.coach_node({"safety_report": None})
    assert "unable to generate" in result["notice"].en.lower()
    assert result["notice"].ja  # bilingual: the Japanese side is filled too
    assert result["coach_cards"] is None


@pytest.fixture
def mock_coach_llm(monkeypatch):
    """Wire coach's Gemini chain to return a fixed bilingual CoachResponse."""

    def install(response: CoachResponse):
        invoke = MagicMock(return_value=response)
        structured = MagicMock()
        structured.invoke = invoke
        chat = MagicMock()
        chat.with_structured_output.return_value = structured
        monkeypatch.setattr(coach, "ChatGoogleGenerativeAI", MagicMock(return_value=chat))

    return install


def _response(score=3) -> CoachResponse:
    return CoachResponse(
        recommendation_score=score,
        japanese=Recommendation(
            verdict="乾燥肌の方にうれしい保湿アイテムです。",
            product="Brand — Product", purpose="うるおいを与える",
            warnings=[], timing="PM", frequency="週2〜3回",
            recommendation_rationale="保湿の目標に合っています。",
        ),
        english=Recommendation(
            verdict="A nice hydrating pick for your dry skin.",
            product="Brand — Product", purpose="Provides moisture",
            warnings=[], timing="PM", frequency="2–3 times per week",
            recommendation_rationale="Fits your hydration goal.",
        ),
    )


def test_coach_node_returns_structured_cards(mock_coach_llm):
    mock_coach_llm(_response())
    state = {
        "safety_report": SafetyAudit(safety_score=0.85),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(skin_type="dry"),
        "user_name": "Aiko",
    }
    result = coach.coach_node(state)

    cards = result["coach_cards"]
    assert cards is not None
    assert cards.english.verdict.startswith("A nice hydrating pick")
    assert cards.japanese.timing == "PM"
    assert cards.recommendation_score == 3
    # Complete scans no longer emit a rendered text blob; that's the CLI's job.
    assert "notice" not in result


def test_coach_node_prepends_deterministic_warnings(mock_coach_llm):
    response = _response()
    response.japanese.warnings = ["モデルからの注意。"]
    response.english.warnings = ["A model-written caution."]
    mock_coach_llm(response)

    state = {
        "safety_report": SafetyAudit(safety_score=0.7),
        # Retinol is both pregnancy-flagged and photosensitising.
        "standardized_ingredients": std_ingredients(("レチノール", "Retinol")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(is_pregnant=True, skin_type="dry"),
    }
    cards = coach.coach_node(state)["coach_cards"]

    # Deterministic (system-computed) cautions come first, model text last.
    assert "Pregnancy caution" in cards.english.warnings[0]
    assert any("Sun-sensitivity caution" in w for w in cards.english.warnings[:-1])
    assert cards.english.warnings[-1] == "A model-written caution."
    assert "妊娠中の注意" in cards.japanese.warnings[0]
    assert cards.japanese.warnings[-1] == "モデルからの注意。"


def test_coach_node_suppresses_score_for_anonymous_scans(mock_coach_llm):
    mock_coach_llm(_response(score=4))
    state = {
        "safety_report": SafetyAudit(safety_score=0.9),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        # No user_profile → anonymous scan.
    }
    cards = coach.coach_node(state)["coach_cards"]
    assert cards.recommendation_score is None
    assert cards.japanese.recommendation_rationale == ""
    assert cards.english.recommendation_rationale == ""


def test_coach_node_defaults_missing_score_to_zero_for_users(mock_coach_llm):
    mock_coach_llm(_response(score=None))
    state = {
        "safety_report": SafetyAudit(safety_score=0.9),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(skin_type="dry"),
    }
    cards = coach.coach_node(state)["coach_cards"]
    assert cards.recommendation_score == 0


def test_coach_node_passes_routine_cards_through(mock_coach_llm):
    response = _response()
    response.routine_japanese = RoutineFitCard(
        risks=["Acme — Peelとの併用に注意が必要です。"],
        value_add=["ブライトニングの目標に役立つ可能性があります。"],
    )
    response.routine_english = RoutineFitCard(
        risks=["Caution is advised when used with Acme — Peel."],
        value_add=["May support your brightening goal."],
    )
    mock_coach_llm(response)

    state = {
        "safety_report": SafetyAudit(safety_score=0.7),
        "standardized_ingredients": std_ingredients(("レチノール", "Retinol")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(goals=["brightening"]),
        "routine_fit": RoutineFit(
            conflicts=[
                CrossConflict(
                    with_product="Acme — Peel",
                    severity="high",
                    groups=("Retinoids", "AHA"),
                    reason="over-exfoliation",
                )
            ],
            value_add=["Introduces Niacinamide, targeting your 'brightening' goal."],
            existing_products=["Acme — Peel"],
        ),
    }
    cards = coach.coach_node(state)["coach_cards"]
    assert "Acme — Peel" in cards.routine_english.risks[0]
    assert cards.routine_japanese.value_add
