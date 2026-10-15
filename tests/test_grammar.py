import asyncio

import pytest

import grammar
from errors import PracticeError, ServiceError


@pytest.mark.parametrize(
    "proposal",
    [
        None,
        "text",
        {},
        {"corrected_text": 4},
        {"corrected_text": "x" * 1201},
        {"corrected_text": "x", "extra": True},
    ],
)
def test_invalid_model_output(monkeypatch, proposal):
    async def generate(*args, **kwargs):
        return proposal

    monkeypatch.setattr(grammar.local, "correct", generate)
    assert asyncio.run(grammar.full_check("He work."))["state"] == "unavailable"


def test_full_check_includes_descriptive_errant_edits(monkeypatch):
    from unittest.mock import AsyncMock

    async def generate(*args, **kwargs):
        return {"corrected_text": "He works every day."}

    monkeypatch.setattr(grammar.local, "correct", generate)
    for name in ("generate", "request"):
        monkeypatch.setattr(
            grammar.local,
            name,
            AsyncMock(side_effect=AssertionError("Unexpected service")),
        )
    result = asyncio.run(grammar.full_check("He work every day."))
    assert result["state"] == "offered"
    assert result["rule_id"] is None
    assert "do not verify" in result["explanation"]
    assert result["proposal_provenance"] == "AI-generated"
    assert result["edits"] == [
        {
            "operation": "replacement",
            "before": "work",
            "after": "works",
            "category": "R:VERB:SVA",
            "explanation": grammar.explanation_for_category("R:VERB:SVA")[
                "explanation"
            ],
            "provenance": "generic local",
            "original_span": {"start": 3, "end": 7},
            "corrected_span": {"start": 3, "end": 8},
        }
    ]


@pytest.mark.parametrize(
    "category,phrase",
    [
        ("R:VERB:TENSE", "verb-tense"),
        ("R:VERB:SVA", "subject–verb agreement"),
        ("M:DET", "determiner change"),
        ("R:NOUN:NUM", "noun-number"),
        ("R:VERB:FORM", "verb-form"),
        ("R:SPELL", "spelling change"),
        ("R:PREP", "preposition change"),
    ],
)
def test_errant_category_explanation_lookup(category, phrase):
    result = grammar.explanation_for_category(category)
    assert phrase in result["explanation"]
    assert result["provenance"] == "generic local"


def test_errant_unknown_category_has_neutral_fallback():
    result = grammar.explanation_for_category("R:UNRECOGNIZED")
    assert result["explanation"] == grammar._UNKNOWN_CATEGORY_EXPLANATION
    assert result["provenance"] == "generic local"


def test_errant_edit_adapter_maps_token_spans_to_source_offsets():
    from types import SimpleNamespace

    original = "I go home."
    corrected = "I went home."
    orig_doc = [
        SimpleNamespace(text="I", idx=0),
        SimpleNamespace(text="go", idx=2),
        SimpleNamespace(text="home", idx=5),
        SimpleNamespace(text=".", idx=9),
    ]
    cor_doc = [
        SimpleNamespace(text="I", idx=0),
        SimpleNamespace(text="went", idx=2),
        SimpleNamespace(text="home", idx=7),
        SimpleNamespace(text=".", idx=11),
    ]
    edit = SimpleNamespace(
        o_start=1,
        o_end=2,
        o_str="go",
        c_start=1,
        c_end=2,
        c_str="went",
        type="R:VERB:TENSE",
    )
    result = grammar._edit_result(edit, original, corrected, orig_doc, cor_doc)
    assert result == {
        "operation": "replacement",
        "before": "go",
        "after": "went",
        "category": "R:VERB:TENSE",
        "explanation": grammar.explanation_for_category("R:VERB:TENSE")["explanation"],
        "provenance": "generic local",
        "original_span": {"start": 2, "end": 4},
        "corrected_span": {"start": 2, "end": 6},
    }


@pytest.mark.parametrize(
    "original,corrected,operation,category,before,after",
    [
        (
            "I go to school yesterday.",
            "I went to school yesterday.",
            "replacement",
            "R:VERB:TENSE",
            "go",
            "went",
        ),
        (
            "She work every day.",
            "She works every day.",
            "replacement",
            "R:VERB:SVA",
            "work",
            "works",
        ),
        (
            "I like the blue book.",
            "I like book.",
            "deletion",
            "U:OTHER",
            "the blue",
            "",
        ),
        (
            "I eat apple.",
            "I eat an apple.",
            "insertion",
            "M:DET",
            "",
            "an",
        ),
        (
            "I bought three apple yesterday.",
            "I bought three apples yesterday.",
            "replacement",
            "R:NOUN:NUM",
            "apple",
            "apples",
        ),
        (
            "I like swim every morning.",
            "I like swimming every morning.",
            "replacement",
            "R:VERB:FORM",
            "swim",
            "swimming",
        ),
        (
            "I recieve letters.",
            "I receive letters.",
            "replacement",
            "R:SPELL",
            "recieve",
            "receive",
        ),
    ],
)
def test_full_check_errant_edit_categories(
    monkeypatch, original, corrected, operation, category, before, after
):
    async def generate(*args, **kwargs):
        return {"corrected_text": corrected}

    monkeypatch.setattr(grammar.local, "correct", generate)
    result = asyncio.run(grammar.full_check(original))
    assert result["state"] == "offered"
    assert len(result["edits"]) == 1
    edit = result["edits"][0]
    assert (edit["operation"], edit["category"], edit["before"], edit["after"]) == (
        operation,
        category,
        before,
        after,
    )
    original_span = edit["original_span"]
    corrected_span = edit["corrected_span"]
    assert original[original_span["start"] : original_span["end"]] == before
    assert corrected[corrected_span["start"] : corrected_span["end"]] == after


def test_full_check_errant_multiple_edits(monkeypatch):
    original = "I go and I play soccer."
    corrected = "I went and I played soccer."

    async def generate(*args, **kwargs):
        return {"corrected_text": corrected}

    monkeypatch.setattr(grammar.local, "correct", generate)
    result = asyncio.run(grammar.full_check(original))
    assert result["state"] == "offered"
    assert len(result["edits"]) == 2
    assert [edit["before"] for edit in result["edits"]] == ["go", "play"]
    assert [edit["after"] for edit in result["edits"]] == ["went", "played"]
    for edit in result["edits"]:
        original_span = edit["original_span"]
        corrected_span = edit["corrected_span"]
        assert original[original_span["start"] : original_span["end"]] == edit["before"]
        assert (
            corrected[corrected_span["start"] : corrected_span["end"]] == edit["after"]
        )


@pytest.mark.parametrize(
    "original,corrected,before,after,category",
    [
        (
            "I packed seven bottle.",
            "I packed seven bottles.",
            "bottle",
            "bottles",
            "R:NOUN:NUM",
        ),
        ("I  go yesterday.", "I  went yesterday.", "go", "went", "R:VERB:TENSE"),
        (
            "😀  I\tgo yesterday.",
            "😀  I\twent yesterday.",
            "go",
            "went",
            "R:VERB:TENSE",
        ),
        ("She don't work.", "She doesn't work.", "do", "does", "R:VERB:SVA"),
    ],
)
def test_errant_raw_text_keeps_exact_spans_and_separate_punctuation(
    original, corrected, before, after, category
):
    edits = grammar._annotate_edits(original, corrected)
    assert len(edits) == 1
    edit = edits[0]
    assert (edit["before"], edit["after"], edit["category"]) == (
        before,
        after,
        category,
    )
    assert edit["original_span"] == {
        "start": original.index(before),
        "end": original.index(before) + len(before),
    }
    assert edit["corrected_span"] == {
        "start": corrected.index(after),
        "end": corrected.index(after) + len(after),
    }


def test_full_check_unchanged_sentence_has_no_edits(monkeypatch):
    async def generate(*args, **kwargs):
        return {"corrected_text": "I go to school."}

    monkeypatch.setattr(grammar.local, "correct", generate)
    result = asyncio.run(grammar.full_check("I go to school."))
    assert result["state"] == "withheld"
    assert "does not mean" in result["message"]
    assert "edits" not in result


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001])
@pytest.mark.parametrize("check", [grammar.quick_check, grammar.full_check])
def test_grammar_rejects_empty_or_oversize_before_inference(monkeypatch, text, check):
    async def unexpected(*args, **kwargs):
        raise AssertionError("invalid input started inference")

    monkeypatch.setattr(grammar.local, "correct", unexpected)
    with pytest.raises(PracticeError):
        asyncio.run(check(text))


def test_no_proposal_is_not_correctness(monkeypatch):
    async def generate(*args, **kwargs):
        return {"corrected_text": "He work."}

    monkeypatch.setattr(grammar.local, "correct", generate)
    result = asyncio.run(grammar.full_check("He work."))
    assert "does not mean" in result["message"]


def test_unavailable_quick_and_cancellation(monkeypatch):
    async def unexpected_check(*args, **kwargs):
        raise AssertionError("quick feedback must not invoke inference or services")

    for name in ("correct", "generate", "request"):
        monkeypatch.setattr(grammar.local, name, unexpected_check)
    result = asyncio.run(grammar.quick_check("Hello"))
    assert result["state"] == "no_issues"
    assert "limited quick checks" in result["message"]

    def cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(grammar, "common_feedback", cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(grammar.quick_check("Hello"))


def test_quick_check_returns_deterministic_phrase_without_service(monkeypatch):
    async def unexpected_check(*args, **kwargs):
        raise AssertionError("quick feedback must not invoke inference or services")

    for name in ("correct", "generate", "request"):
        monkeypatch.setattr(grammar.local, name, unexpected_check)
    result = asyncio.run(grammar.quick_check("I enjoy to swim."))
    assert result["state"] == "offered"
    assert result["corrected_text"] == "I enjoy swimming."
    assert result["rule_id"] == "ENJOY_ACTIVITY"


def test_quick_check_timeout_is_unavailable(monkeypatch):
    async def timeout(_):
        raise TimeoutError

    monkeypatch.setattr(grammar.asyncio, "sleep", timeout)
    result = asyncio.run(grammar.quick_check("Hello"))
    assert result["state"] == "unavailable"
    assert "No change was made" in result["message"]


@pytest.mark.parametrize(
    "stage,expected",
    [("model", "T5"), ("errant", "ERRANT")],
)
def test_full_feedback_identifies_failed_stage(monkeypatch, stage, expected):
    from unittest.mock import AsyncMock

    generate = AsyncMock(return_value={"corrected_text": "I bought three apples."})
    generate.side_effect = ServiceError() if stage == "model" else None
    monkeypatch.setattr(grammar.local, "correct", generate)
    if stage == "errant":

        def unavailable(*args):
            raise ServiceError()

        monkeypatch.setattr(grammar, "_annotate_edits", unavailable)
    result = asyncio.run(grammar.full_check("I bought three apple."))
    assert result["state"] == "unavailable"
    assert expected in result["message"]


def test_full_feedback_inference_exception_is_unavailable(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("private model failure")

    monkeypatch.setattr(grammar.local, "correct", fail)
    result = asyncio.run(grammar.full_check("I like swimming."))
    assert result["state"] == "unavailable"
    assert "T5" in result["message"]
    assert "private model failure" not in result["message"]


def test_quick_check_keeps_optional_arguments_without_service_calls(monkeypatch):
    async def unexpected_check(*args, **kwargs):
        raise AssertionError("quick feedback must not invoke inference or services")

    for name in ("correct", "generate", "request"):
        monkeypatch.setattr(grammar.local, name, unexpected_check)
    result = asyncio.run(
        grammar.quick_check("Hello", history=(), spelling=False, names={"Hello"})
    )
    assert result["state"] == "no_issues"


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "I am Lovejit and I like Basketballing.",
            "I am Lovejit and I like playing basketball.",
        ),
        ("She does not enjoy basketballing.", "She does not enjoy playing basketball."),
        ("They prefer basketballing!", "They prefer playing basketball!"),
        ("I am teacher.", "I am a teacher."),
        ("She is engineer.", "She is an engineer."),
        ("You are student", "You are a student"),
        (
            "I am interested on learning English.",
            "I am interested in learning English.",
        ),
        ("It depended of the weather.", "It depended on the weather."),
        ("We are listening music.", "We are listening to music."),
        ("He enjoys to swim.", "He enjoys swimming."),
        ("I enjoyed to run.", "I enjoyed running."),
        ("I enjoy to read.", "I enjoy reading."),
        ("😀 I like basketballing.", "😀 I like playing basketball."),
    ],
)
def test_common_phrase_coverage(text, expected):
    result = asyncio.run(grammar.quick_check(text))
    assert result["state"] == "offered"
    assert result["corrected_text"] == expected
    assert result["explanation"]


@pytest.mark.parametrize(
    "text",
    [
        "I like playing basketball.",
        "I play with a basketball.",
        "My name is Basketballing.",
        "I like a game called Basketballing.",
        'She said "I like basketballing".',
        "I am Teacher Smith.",
        "I am doctor of philosophy.",
        "I am a teacher.",
        "I enjoy swimming.",
        "I am interested in music.",
        "I listen to music.",
        "The music depends on the weather.",
        "I am on the basketball team.",
        "I enjoy to play and I listen music.",
    ],
)
def test_common_phrase_preserves_supported_and_ambiguous_wording(text):
    assert grammar.common_feedback(text) is None


def test_common_phrase_respects_confirmed_name():
    assert (
        grammar.common_feedback("I like Basketballing.", names={"basketballing"})
        is None
    )


def test_full_check_describes_phrase_proposal(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        grammar.local,
        "correct",
        AsyncMock(return_value={"corrected_text": "I like playing basketball."}),
    )
    result = asyncio.run(grammar.full_check("I like basketballing."))
    assert result["state"] == "offered"
    assert result["edits"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I look forward to meet you.", "I look forward to meeting you."),
        (
            "She is looking forward to see her family.",
            "She is looking forward to seeing her family.",
        ),
        (
            "We looked forward to visit the museum.",
            "We looked forward to visiting the museum.",
        ),
        ("She is married with him.", "She is married to him."),
        ("He was not married with her.", "He was not married to her."),
        ("I went to home.", "I went home."),
        ("We are going to home!", "We are going home!"),
        ("They did not come to home.", "They did not come home."),
    ],
)
def test_small_coverage_expansion(text, expected):
    result = asyncio.run(grammar.quick_check(text))
    assert result["corrected_text"] == expected
    assert result["explanation"]


@pytest.mark.parametrize(
    "text",
    [
        "I look forward to meeting you.",
        "I look forward to the visit.",
        "She is married with children.",
        "She is married with her family's blessing.",
        "She is married with her parents present.",
        "I went to Home Depot.",
        "I go to home games.",
        "We are going to home school our children.",
        "They went home.",
        'He said "I went to home."',
        "I went to home. She is married with him.",
    ],
)
def test_small_coverage_expansion_preserves_valid_or_ambiguous_text(text):
    assert grammar.common_feedback(text) is None
