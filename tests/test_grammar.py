import asyncio

import pytest

import grammar
from errors import ServiceError


def evidence(text, old=None, choices=(), rule="DID_PAST"):
    matches = []
    if old is not None:
        offset = len(text[: text.index(old)].encode("utf-16-le")) // 2
        length = len(old.encode("utf-16-le")) // 2
        matches.append(
            {
                "offset": offset,
                "length": length,
                "context": {"text": text, "offset": offset, "length": length},
                "rule": {"id": rule},
                "replacements": [{"value": value} for value in choices],
            }
        )
    return {
        "software": {"version": "6.6"},
        "warnings": {"incompleteResults": False},
        "matches": matches,
    }


def test_quick_exact_evidence():
    text = "Did you visited the castle?"
    result = grammar._select(text, evidence(text, "visited", ["visit"]))
    assert result["state"] == "offered"
    assert result["corrected_text"] == "Did you visit the castle?"
    assert "already marks the past" in result["explanation"]


def test_agreement_filters_past():
    text = "She go to work."
    result = grammar._select(
        text, evidence(text, "go", ["goes", "went"], "HE_VERB_AGR")
    )
    assert result["corrected_text"] == "She goes to work."


@pytest.mark.parametrize(
    "text,old,new,rule",
    [
        ("She go yesterday.", "go", ["goes"], "HE_VERB_AGR"),
        ("They go to work.", "go", ["goes"], "HE_VERB_AGR"),
        ("She go and return.", "go", ["goes"], "HE_VERB_AGR"),
        ("Did you visited?", "visited", ["visit", "see"], "DID_PAST"),
        ("I visited.", "visited", ["visit"], "DID_PAST"),
        ("He work.", "work", ["works"], "UNKNOWN"),
    ],
)
def test_unsupported_quick_withheld(text, old, new, rule):
    assert (
        grammar._select(text, evidence(text, old, new, rule))["state"]
        == "no_supported_correction"
    )


def test_unicode_offsets_and_bad_context():
    text = "😀 Did you visited?"
    raw = evidence(text, "visited", ["visit"])
    decision = grammar.evidence(text, "😀 Did you visit?", raw)
    assert decision["state"] == "provisional"
    raw["matches"][0]["context"]["text"] = "Different text"
    with pytest.raises(ValueError):
        grammar.evidence(text, "😀 Did you visit?", raw)
    with pytest.raises((ValueError, UnicodeError)):
        grammar.utf16_span(text, 1, 1)


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

    monkeypatch.setattr(grammar.local, "generate", generate)
    assert asyncio.run(grammar.full_check("He work."))["state"] == "unavailable"


def test_full_check_requires_exact_agreement(monkeypatch):
    async def generate(*args, **kwargs):
        return {"corrected_text": "He works."}

    async def check(*args, **kwargs):
        return evidence("He work.", "work", ["works"], "HE_VERB_AGR")

    monkeypatch.setattr(grammar.local, "generate", generate)
    monkeypatch.setattr(grammar.local, "check", check)
    assert asyncio.run(grammar.full_check("He work."))["state"] == "offered"

    async def unsupported(*args, **kwargs):
        return {"corrected_text": "He worked yesterday."}

    async def count(*args):
        return {"matches": []}

    monkeypatch.setattr(grammar.local, "generate", unsupported)
    monkeypatch.setattr(grammar, "count_evidence", count)
    assert asyncio.run(grammar.full_check("He work."))["state"] == "withheld"


def test_no_proposal_is_not_correctness(monkeypatch):
    async def generate(*args, **kwargs):
        return {"corrected_text": "He work."}

    monkeypatch.setattr(grammar.local, "generate", generate)
    result = asyncio.run(grammar.full_check("He work."))
    assert "does not mean" in result["message"]


def test_unavailable_quick_and_cancellation(monkeypatch):
    async def check(*args, **kwargs):
        raise ServiceError()

    monkeypatch.setattr(grammar.local, "check", check)
    assert asyncio.run(grammar.quick_check("Hello"))["state"] == "unavailable"

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(grammar.local, "check", cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(grammar.quick_check("Hello"))
