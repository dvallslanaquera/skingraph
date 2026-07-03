# Tests for the post-scan follow-up Q&A (src/followup.py).
#
# The Gemini call is mocked (mirroring tests/test_coach.py); the focus is the
# grounding contract — the prompt must carry the scan context — and the
# deterministic safety findings that must reach the model verbatim.
from unittest.mock import MagicMock

import pytest

from src import followup
from src.state import SafetyAudit, UserProfile

from tests.helpers import std_ingredients


@pytest.fixture
def mock_followup_llm(monkeypatch):
    """Wire the follow-up's Gemini chain to return a fixed text answer."""

    def install(answer: str = "A grounded answer."):
        invoke = MagicMock(return_value=MagicMock(content=answer))
        chat = MagicMock()
        chat.invoke = invoke
        monkeypatch.setattr(
            followup, "ChatGoogleGenerativeAI", MagicMock(return_value=chat)
        )
        return invoke

    return install


def _human_prompt(invoke_mock) -> str:
    """The HumanMessage content passed to the mocked invoke."""
    messages = invoke_mock.call_args.args[0]
    return messages[1].content


def _system_prompt(invoke_mock) -> str:
    messages = invoke_mock.call_args.args[0]
    return messages[0].content


def _ask(question="Can I use this with vitamin C?", lang="en", **overrides):
    kwargs = dict(
        brand="Hada",
        product_name="Lotion",
        standardized_ingredients=std_ingredients(("水", "Water")),
        safety_report=SafetyAudit(safety_score=0.9),
        routine_fit=None,
        question=question,
        lang=lang,
        profile=None,
        user_name=None,
        routine_products=None,
    )
    kwargs.update(overrides)
    return followup.answer_followup(**kwargs)


def test_answer_returns_stripped_llm_text(mock_followup_llm):
    mock_followup_llm("  the answer \n")
    assert _ask() == "the answer"


def test_prompt_carries_the_scan_grounding(mock_followup_llm):
    invoke = mock_followup_llm()
    _ask(question="Is this OK for daily use?")

    human = _human_prompt(invoke)
    assert "Hada — Lotion" in human               # product identity
    assert "Water" in human                        # verified INCI list
    assert "Safety score: 0.90" in human           # audit findings
    assert "Is this OK for daily use?" in human    # the question itself
    assert "entirely in English" in human


def test_prompt_requests_japanese_for_ja(mock_followup_llm):
    invoke = mock_followup_llm()
    _ask(lang="ja")
    assert "entirely in Japanese" in _human_prompt(invoke)


def test_system_prompt_reuses_yakukiho_rules(mock_followup_llm):
    invoke = mock_followup_llm()
    _ask()
    system = _system_prompt(invoke)
    assert "薬機法 COMPLIANCE — MANDATORY" in system
    assert "Do NOT invent" in system


def test_deterministic_sun_finding_reaches_the_prompt(mock_followup_llm):
    # Retinol triggers the coach's deterministic sun-sensitivity caution; the
    # follow-up must hand that finding to the model as authoritative context.
    invoke = mock_followup_llm()
    _ask(standardized_ingredients=std_ingredients(("レチノール", "Retinol")))

    human = _human_prompt(invoke)
    assert "DETERMINISTIC SAFETY FINDINGS" in human
    assert "Sun-sensitivity caution" in human


def test_pregnancy_question_surfaces_flagged_ingredients(mock_followup_llm):
    # The profile does NOT state a pregnancy, but the QUESTION asks about it →
    # the deterministic pregnancy analysis must still be provided.
    invoke = mock_followup_llm()
    _ask(
        question="Is this safe while pregnant?",
        standardized_ingredients=std_ingredients(("レチノール", "Retinol")),
    )

    human = _human_prompt(invoke)
    assert "Retinol" in human
    assert "avoid during pregnancy" in human


def test_pregnancy_question_with_clean_product_says_none_flagged(mock_followup_llm):
    invoke = mock_followup_llm()
    _ask(
        question="妊娠中でも使えますか？",
        lang="ja",
        standardized_ingredients=std_ingredients(("水", "Water")),
    )

    human = _human_prompt(invoke)
    assert "妊娠中の使用が特に懸念されるもの" in human


def test_pregnant_profile_gets_deterministic_caution_without_asking(mock_followup_llm):
    invoke = mock_followup_llm()
    _ask(
        question="How often should I use it?",
        standardized_ingredients=std_ingredients(("レチノール", "Retinol")),
        profile=UserProfile(is_pregnant=True),
    )

    human = _human_prompt(invoke)
    assert "Pregnancy caution" in human
