"""Limited quick rules and local ERRANT descriptions for model proposals."""

import asyncio
import json
import re
from functools import lru_cache
from pathlib import Path

import local
from conversation import validate_text
from errors import PracticeError, ServiceError

_UNKNOWN_CATEGORY_EXPLANATION = (
    "ERRANT assigned a category to this edit, but no explanation is available for it."
)


def explanation_for_category(category):
    """Return a local, descriptive explanation for an ERRANT category."""
    category_type = (
        category.split(":", 1)[1]
        if isinstance(category, str) and ":" in category
        else category
    )
    explanations = _grammar_explanations()
    explanation = (
        explanations.get(category_type) if isinstance(category_type, str) else None
    )
    if explanation is None:
        return {
            "explanation": _UNKNOWN_CATEGORY_EXPLANATION,
            "provenance": "generic local",
        }
    return {"explanation": explanation, "provenance": "generic local"}


@lru_cache(maxsize=1)
def _grammar_explanations():
    return json.loads(
        (Path(__file__).parent / "rules" / "grammar_explanations.json").read_text(
            encoding="utf-8"
        )
    )


# Narrow phrase rules: preserve surrounding words, person, tense and negation.
# Avoid broad guesses such as replacing every "in" with "at".
COMMON_PHRASES = (
    (
        "PLAY_BASKETBALL",
        r"\b(?P<verb>like|likes|love|loves|enjoy|enjoys|prefer|prefers)\s+(?P<edit>basketballing)\b",
        "playing basketball",
        "Say ‘playing basketball’ for the activity. For example: ‘I like playing basketball.’",
    ),
    (
        "INTERESTED_IN",
        r"\binterested\s+(?P<edit>on)\s+(?:learning|playing|reading|cooking|music|sports|basketball)\b",
        "in",
        "Say ‘interested in’ when talking about something you want to learn about or do.",
    ),
    (
        "DEPEND_ON_PHRASE",
        r"\b(?:depend|depends|depended|depending)\s+(?P<edit>of)\s+(?:me|you|him|her|us|them|the weather)\b",
        "on",
        "Say ‘depend on’ when you need someone or something, or when it affects what happens.",
    ),
    (
        "LISTEN_TO_MUSIC",
        r"\b(?:listen|listens|listened|listening)\s+(?P<edit>music)\b",
        "to music",
        "Put ‘to’ after ‘listen’: ‘listen to music’.",
    ),
    (
        "ENJOY_ACTIVITY",
        r"\b(?:enjoy|enjoys|enjoyed)\s+(?P<edit>to (?P<activity>play|read|cook|swim|run))\b",
        None,
        "After ‘enjoy’, use an ‘-ing’ word: ‘enjoy playing’, for example.",
    ),
    (
        "LOOK_FORWARD_ACTIVITY",
        r"\b(?:look|looks|looked|looking)\s+forward\s+to\s+(?P<edit>meet|see|visit)\s+(?:you|him|her|them|us|my|our|the)\b",
        None,
        "After ‘look forward to’, use an ‘-ing’ word, such as ‘meeting’.",
    ),
    (
        "MARRIED_TO",
        r"\b(?:am|is|are|was|were)\s+(?:not\s+)?married\s+(?P<edit>with)\s+(?:me|you|him|her|them)\s*(?=[.!?]|$)",
        "to",
        "Use ‘married to’ before the person: ‘She is married to him.’",
    ),
    (
        "GO_HOME",
        r"\b(?:go|goes|going|went|come|comes|coming|came)\s+(?P<edit>to home)\s*(?=[.!?,]|$)",
        "home",
        "Say ‘go home’ or ‘come home’. You do not need ‘to’ before ‘home’ here.",
    ),
    (
        "JOB_ARTICLE",
        r"\b(?:I am|he is|she is|you are)\s+(?P<edit>teacher|doctor|nurse|engineer|student|accountant)\s*(?=[.!?]|$)",
        None,
        "When saying what someone's job is, put ‘a’ or ‘an’ before the job: ‘a teacher’ or ‘an engineer’. Use ‘a student’ in the same way.",
    ),
)


def common_feedback(text, names=()):
    """Offer one unambiguous phrase edit; never rewrite quoted wording or names."""
    if re.search(r"[\"‘’“”\n\r]", text) or "'" in text:
        return None
    candidates = []
    for rule, pattern, replacement, message in COMMON_PHRASES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start, end = match.span("edit")
            old = text[start:end]
            if old.casefold() in {name.casefold() for name in names}:
                continue
            # Exclude wording introduced as a name, title or explicit quotation.
            if re.search(
                r"\b(?:named|called|name is|title is|word is)\b",
                text[:start],
                re.IGNORECASE,
            ):
                continue
            if rule == "ENJOY_ACTIVITY":
                activity = match["activity"].lower()
                new = {"swim": "swimming", "run": "running"}.get(
                    activity, activity + "ing"
                )
                message = f"After ‘enjoy’, say ‘{new}’, not ‘to {activity}’."
            elif rule == "LOOK_FORWARD_ACTIVITY":
                new = old.lower() + "ing"
                message = f"After ‘look forward to’, say ‘{new}’, not ‘{old.lower()}’. For example: ‘I look forward to meeting you.’"
            elif rule == "JOB_ARTICLE":
                article = "an" if old.lower() in {"engineer", "accountant"} else "a"
                new = article + " " + old.lower()
                message = f"Say ‘{new}’ when describing one person's role. Put ‘{article}’ before ‘{old.lower()}’."
            else:
                new = replacement
            candidates.append(
                {
                    "state": "offered",
                    "corrected_text": text[:start] + new + text[end:],
                    "original": old,
                    "replacement": new,
                    "explanation": message,
                    "rule_id": rule,
                }
            )
    return candidates[0] if len(candidates) == 1 else None


NO_CORRECTION = {
    "state": "withheld",
    "message": "No supported correction found. This does not mean the message is error-free.",
}
UNAVAILABLE = {
    "state": "unavailable",
    "message": "Full grammar feedback could not finish. Check the local T5 and ERRANT models.",
}


@lru_cache(maxsize=1)
def _errant_annotator():
    import errant

    return errant.load("en")


def _character_span(doc, start, end, text):
    """Convert ERRANT's token offsets to character offsets in the source text."""
    if start == end:
        position = doc[start].idx if start < len(doc) else len(text)
        return {"start": position, "end": position}
    return {
        "start": doc[start].idx,
        "end": doc[end - 1].idx + len(doc[end - 1].text),
    }


def _edit_result(edit, original, corrected, orig_doc, cor_doc):
    if edit.o_start == edit.o_end:
        operation = "insertion"
    elif edit.c_start == edit.c_end:
        operation = "deletion"
    else:
        operation = "replacement"
    original_span = _character_span(orig_doc, edit.o_start, edit.o_end, original)
    corrected_span = _character_span(cor_doc, edit.c_start, edit.c_end, corrected)
    category = edit.type
    return {
        "operation": operation,
        "before": original[original_span["start"] : original_span["end"]],
        "after": corrected[corrected_span["start"] : corrected_span["end"]],
        "category": category,
        **explanation_for_category(category),
        "original_span": original_span,
        "corrected_span": corrected_span,
    }


def _annotate_edits(original, corrected):
    """Return ERRANT descriptions; categories do not verify proposed edits."""
    annotator = _errant_annotator()
    # Input is raw learner/model text, not ERRANT's default space-tokenized format.
    orig_doc = annotator.parse(original, tokenise=True)
    cor_doc = annotator.parse(corrected, tokenise=True)
    return [
        _edit_result(edit, original, corrected, orig_doc, cor_doc)
        for edit in annotator.annotate(orig_doc, cor_doc)
    ]


async def quick_check(text, *, history=(), spelling=True, names=()):
    """Offer narrow authored phrase feedback without calling local services."""
    validate_text(text)
    try:
        async with asyncio.timeout(0.3):
            await asyncio.sleep(0)
            return common_feedback(text, names) or {
                "state": "no_issues",
                "message": "No issue detected by limited quick checks. This does not mean the message is error-free.",
            }
    except (TimeoutError, ServiceError, ValueError, TypeError, KeyError):
        return {
            "state": "unavailable",
            "message": "Limited quick feedback could not finish. No change was made; please try again or use the separate full check.",
        }


async def full_check(text):
    """T5 proposes; ERRANT and local explanations describe each proposed edit."""
    validate_text(text)
    if "\n" in text or "\r" in text:
        return {
            "state": "unsupported",
            "message": "Full grammar checks support single-line messages.",
        }
    stage = "model"
    try:
        async with asyncio.timeout(55):
            proposal = await local.correct(text)
            if not isinstance(proposal, dict) or set(proposal) != {"corrected_text"}:
                raise ServiceError()
            corrected = proposal["corrected_text"]
            if (
                not isinstance(corrected, str)
                or not corrected.strip()
                or len(corrected) > 1200
            ):
                raise ServiceError()
            if corrected == text:
                return dict(NO_CORRECTION)
            stage = "errant"
            edits = await asyncio.to_thread(_annotate_edits, text, corrected)
            if not edits:
                return dict(NO_CORRECTION)
            return {
                "state": "offered",
                "corrected_text": corrected,
                "explanation": "This is a local model suggestion. ERRANT labels describe the edits; they do not verify that the correction is valid or preserves your intended meaning.",
                "proposal_provenance": "AI-generated",
                "rule_id": None,
                "edits": edits,
            }
    except (
        PracticeError,
        TimeoutError,
        OSError,
        ImportError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ):
        messages = {
            "model": "Full feedback could not get a complete local T5 suggestion in time. Check the grammar model installation (uv run python tools/setup.py grammar), or try a shorter message.",
            "errant": "Full feedback could not classify the local model suggestion. Check that ERRANT and its spaCy English model are installed.",
        }
        return {"state": "unavailable", "message": messages[stage]}
