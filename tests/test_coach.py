# Tests for the coach node.
#
# The Gemini call is mocked; the focus is the deterministic, safety-critical
# logic the coach computes itself (pregnancy / dehydration / sun-sensitivity
# cautions and card rendering) rather than the model's free text.
from unittest.mock import MagicMock

import pytest

from src.nodes import coach
from src.nodes.coach import CoachResponse, Recommendation, RoutineFitCard
from src.state import CrossConflict, RoutineFit, SafetyAudit, UserProfile

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
# _render_recommendation
# --------------------------------------------------------------------------- #
def test_render_prepends_extra_warnings_then_card_warnings():
    card = Recommendation(
        product="B — P", purpose="hydration",
        warnings=["card warning"], timing="PM", frequency="Daily",
    )
    rendered = coach._render_recommendation(card, "en", ["extra warning"])
    # Extra (deterministic) warnings come before the model's own warnings.
    assert rendered.index("extra warning") < rendered.index("card warning")
    assert "Best timing: PM" in rendered
    assert "Frequency: Daily" in rendered


def test_render_shows_none_when_no_warnings():
    card = Recommendation(product="B — P", purpose="x", timing="AM", frequency="Daily")
    assert "Warnings: None" in coach._render_recommendation(card, "en", [])
    assert "注意事項: 特になし" in coach._render_recommendation(card, "ja", [])


# --------------------------------------------------------------------------- #
# coach_node
# --------------------------------------------------------------------------- #
def test_coach_node_placeholder_without_safety_report():
    result = coach.coach_node({"safety_report": None})
    assert "unable to generate" in result["coach_advice"].lower()
    assert result["routine_recommendations"] == []


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


def _response() -> CoachResponse:
    return CoachResponse(
        japanese=Recommendation(
            product="Brand — Product", purpose="うるおいを与える",
            warnings=[], timing="PM", frequency="週2〜3回",
        ),
        english=Recommendation(
            product="Brand — Product", purpose="Provides moisture",
            warnings=[], timing="PM", frequency="2–3 times per week",
        ),
    )


def test_coach_node_renders_bilingual_card_and_machine_fields(mock_coach_llm):
    mock_coach_llm(_response())
    state = {
        "safety_report": SafetyAudit(safety_score=0.85),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(skin_type="dry"),
        "user_name": "Aiko",
    }
    result = coach.coach_node(state)

    advice = result["coach_advice"]
    assert "【日本語】" in advice and "【English】" in advice

    recs = result["routine_recommendations"]
    assert "[PRODUCT] Brand — Product" in recs
    assert "[TIMING] PM" in recs
    assert any(r.startswith("[FREQUENCY]") for r in recs)


def test_coach_node_omits_routine_fit_without_routine(mock_coach_llm):
    mock_coach_llm(_response())
    state = {
        "safety_report": SafetyAudit(safety_score=0.9),
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        # No routine_fit in state → no Routine Fit section.
    }
    result = coach.coach_node(state)
    assert "Routine Fit" not in result["coach_advice"]
    assert not any(r.startswith("[ROUTINE-") for r in result["routine_recommendations"])


def test_coach_node_renders_routine_fit_section_and_machine_lines(mock_coach_llm):
    response = _response()
    response.routine_japanese = RoutineFitCard(
        risks=["Acme — Peelとの併用に注意が必要です。"],
        redundancy=[],
        value_add=["ブライトニングの目標に役立つ可能性があります。"],
    )
    response.routine_english = RoutineFitCard(
        risks=["Caution is advised when used with Acme — Peel."],
        redundancy=[],
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
    result = coach.coach_node(state)

    advice = result["coach_advice"]
    assert "Routine Fit" in advice and "ルーティン適合" in advice
    assert "Caution is advised when used with Acme — Peel." in advice

    # Deterministic machine-readable findings are always emitted.
    recs = result["routine_recommendations"]
    assert any(r.startswith("[ROUTINE-RISK]") and "Acme — Peel" in r for r in recs)
    assert any(r.startswith("[ROUTINE-VALUE]") for r in recs)


def test_coach_node_injects_deterministic_pregnancy_and_sun_warnings(mock_coach_llm):
    mock_coach_llm(_response())
    state = {
        "safety_report": SafetyAudit(safety_score=0.7),
        # Retinol is both pregnancy-flagged and photosensitising.
        "standardized_ingredients": std_ingredients(("レチノール", "Retinol")),
        "extracted_data": make_extraction(brand="Brand", product_name="Product"),
        "user_profile": UserProfile(is_pregnant=True, skin_type="dry"),
    }
    result = coach.coach_node(state)

    warnings = [r for r in result["routine_recommendations"] if r.startswith("[WARNING]")]
    assert any("Pregnancy caution" in w and "Retinol" in w for w in warnings)
    assert any("Sun-sensitivity caution" in w for w in warnings)
