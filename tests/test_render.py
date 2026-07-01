# Tests for the CLI text renderers over the coach's structured cards.
from src.render import (render_coach_cards, render_recommendation,
                        render_routine_fit)
from src.state import CoachResponse, Recommendation, RoutineFitCard


def _card(**overrides) -> Recommendation:
    fields = dict(
        verdict="A nice hydrating pick for dry skin.",
        product="B — P",
        purpose="hydration",
        warnings=["first warning", "second warning"],
        timing="PM",
        frequency="Daily",
    )
    fields.update(overrides)
    return Recommendation(**fields)


def test_render_leads_with_verdict_and_keeps_warning_order():
    rendered = render_recommendation(_card(), "en")
    assert rendered.startswith("A nice hydrating pick")
    assert rendered.index("first warning") < rendered.index("second warning")
    assert "Best timing: PM" in rendered
    assert "Frequency: Daily" in rendered


def test_render_shows_none_when_no_warnings():
    card = _card(warnings=[])
    assert "Warnings: None" in render_recommendation(card, "en")
    assert "注意事項: 特になし" in render_recommendation(card, "ja")


def test_render_includes_application_notes_when_present():
    card = _card(application_notes=["apply to dry skin"])
    rendered = render_recommendation(card, "en")
    assert "How to apply:" in rendered
    assert "apply to dry skin" in rendered


def test_render_routine_fit_lists_findings_per_section():
    fit = RoutineFitCard(risks=["clashes with Acme — Peel"], redundancy=[])
    rendered = render_routine_fit(fit, "en")
    assert "Risks:" in rendered and "clashes with Acme — Peel" in rendered
    assert "Redundancy: None" in rendered


def test_render_coach_cards_is_bilingual_with_fit_only_when_present():
    cards = CoachResponse(japanese=_card(), english=_card())
    combined = render_coach_cards(cards)
    assert "【日本語】" in combined and "【English】" in combined
    assert "Routine Fit" not in combined

    cards.routine_english = RoutineFitCard(risks=["clashes with Acme — Peel"])
    assert "Routine Fit" in render_coach_cards(cards)
