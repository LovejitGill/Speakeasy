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
    assert "already tells us this happened in the past" in result["explanation"]


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


@pytest.mark.parametrize(
    "text,old,new,rule,expected",
    [
        (
            "She teach English every Monday.",
            "teach",
            "teaches",
            "HE_VERB_AGR",
            "offered",
        ),
        ("Did they brought their tickets?", "brought", "bring", "DID_PAST", "offered"),
        (
            "She work yesterday.",
            "work",
            "works",
            "HE_VERB_AGR",
            "no_supported_correction",
        ),
        (
            'He said, "She go home."',
            "go",
            "goes",
            "HE_VERB_AGR",
            "no_supported_correction",
        ),
        (
            "She go to school and he work at home.",
            "go",
            "goes",
            "HE_VERB_AGR",
            "no_supported_correction",
        ),
    ],
)
def test_review_new_quick_examples(text, old, new, rule, expected):
    result = grammar._select(text, evidence(text, old, [new], rule))
    assert result["state"] == expected
    if expected == "offered":
        assert result["corrected_text"] == text.replace(old, new, 1)


@pytest.mark.parametrize(
    "proposal,expected",
    [("He did not go home.", "offered"), ("He did go home.", "withheld")],
)
def test_review_full_correction_preserves_negation(monkeypatch, proposal, expected):
    text = "He did not went home."

    async def generate(*a, **kw):
        return {"corrected_text": proposal}

    async def check(*a, **kw):
        return evidence(text, "went", ["go"], "DID_PAST")

    async def count(*a):
        return {"matches": []}

    monkeypatch.setattr(grammar.local, "generate", generate)
    monkeypatch.setattr(grammar.local, "check", check)
    monkeypatch.setattr(grammar, "count_evidence", count)
    assert asyncio.run(grammar.full_check(text))["state"] == expected


@pytest.mark.parametrize(
    "text,old,new,rule",
    [
        ("She can sings well.", "sings", "sing", "MD_BASEFORM"),
        ("Does he has a ticket?", "has", "have", "DOES_X_HAS"),
        ("They should waits outside.", "waits", "wait", "NON3PRS_VERB"),
        (
            "He did not went home.",
            "went",
            "go",
            "AUXILIARY_DO_WITH_INCORRECT_VERB_FORM",
        ),
    ],
)
def test_new_quick_rules_require_exact_evidence(text, old, new, rule):
    result = grammar._select(text, evidence(text, old, [new], rule))
    assert result["state"] == "offered"
    assert result["corrected_text"] == text.replace(old, new, 1)
    assert result["explanation"]


@pytest.mark.parametrize(
    "text",
    ['She said, "She can sings."', "My sister can sings.", "She can sings and dances."],
)
def test_new_modal_rule_rejects_unsupported_context(text):
    assert (
        grammar._select(text, evidence(text, "sings", ["sing"], "MD_BASEFORM"))["state"]
        == "no_supported_correction"
    )


@pytest.mark.parametrize(
    "text,proposal,count_expected",
    [
        ("She work yesterday.", "She worked yesterday.", False),
        ('He said, "She go home."', 'He said, "She goes home."', False),
        ("I bought three apple.", "I bought three apples.", True),
    ],
)
def test_supplemental_checker_only_for_count_candidates(
    monkeypatch, text, proposal, count_expected
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        grammar.local, "generate", AsyncMock(return_value={"corrected_text": proposal})
    )
    monkeypatch.setattr(grammar.local, "check", AsyncMock(return_value=evidence(text)))
    counter = AsyncMock(return_value={"matches": []})
    monkeypatch.setattr(grammar, "count_evidence", counter)
    assert asyncio.run(grammar.full_check(text))["state"] == "withheld"
    assert counter.await_count == int(count_expected)


@pytest.mark.parametrize(
    "text,old,new,rule,phrase",
    [
        (
            "She can sings well.",
            "sings",
            "sing",
            "MD_BASEFORM",
            "When saying ‘She can …’, use ‘sing’, not ‘sings’. Say ‘She can sing’.",
        ),
        (
            "They should waits outside.",
            "waits",
            "wait",
            "NON3PRS_VERB",
            "Say ‘They should wait’.",
        ),
        ("Does he has a ticket?", "has", "have", "DOES_X_HAS", "Say ‘Does he have’."),
        (
            "He did not went home.",
            "went",
            "go",
            "AUXILIARY_DO_WITH_INCORRECT_VERB_FORM",
            "Say ‘He did not go’, not ‘He did not went’.",
        ),
    ],
)
def test_plain_language_verb_explanations(text, old, new, rule, phrase):
    result = grammar._select(text, evidence(text, old, [new], rule))
    assert result["state"] == "offered"
    assert phrase in result["explanation"]
    assert all(
        term not in result["explanation"] for term in ("basic form", "subject", "tense")
    )


@pytest.mark.parametrize(
    "text,old,new",
    [
        ("I met a elephant.", "a", "an"),
        ("She has an dog.", "an", "a"),
        ("It takes a hour.", "a", "an"),
    ],
)
def test_article_feedback_uses_checker_evidence(text, old, new):
    raw = evidence(text, old, [new], "EN_A_VS_AN")
    offset = text.index(f" {old} ") + 1
    raw["matches"][0]["offset"] = offset
    raw["matches"][0]["context"]["offset"] = offset
    result = grammar._select(text, raw)
    assert result["state"] == "offered"
    assert result["corrected_text"] == text[:offset] + new + text[offset + len(old) :]


@pytest.mark.parametrize(
    "text", ['He wrote "a elephant."', "I met a elephant and a owl."]
)
def test_article_feedback_withholds_quoted_or_compound_text(text):
    assert (
        grammar._select(text, evidence(text, "a", ["an"], "EN_A_VS_AN"))["state"]
        == "no_supported_correction"
    )


@pytest.mark.parametrize(
    "stage,expected",
    [("model", "Ollama"), ("checker", "LanguageTool 6.6"), ("count", "SPEAKWELL_JAVA")],
)
def test_full_feedback_identifies_failed_stage(monkeypatch, stage, expected):
    from unittest.mock import AsyncMock

    text = "I bought three apple."
    generate = AsyncMock(return_value={"corrected_text": "I bought three apples."})
    check = AsyncMock(return_value=evidence(text))
    count = AsyncMock(return_value={"matches": []})
    {"model": generate, "checker": check, "count": count}[
        stage
    ].side_effect = ServiceError()
    monkeypatch.setattr(grammar.local, "generate", generate)
    monkeypatch.setattr(grammar.local, "check", check)
    monkeypatch.setattr(grammar, "count_evidence", count)
    result = asyncio.run(grammar.full_check(text))
    assert result["state"] == "unavailable"
    assert expected in result["message"]
    assert text not in result["message"]


def test_quick_failure_does_not_blame_model(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(grammar.local, "check", AsyncMock(side_effect=ServiceError()))
    result = asyncio.run(grammar.quick_check("Hello."))
    assert result["state"] == "unavailable"
    assert "LanguageTool" in result["message"]
    assert "Ollama" not in result["message"]


def test_article_rule_rejects_letter_inside_word():
    text = "I saw a elephant."
    assert (
        grammar._select(text, evidence(text, "a", ["an"], "EN_A_VS_AN"))["state"]
        == "no_supported_correction"
    )


def spelling_evidence(text, entries):
    raw = evidence(text)
    for word, alternatives in entries:
        raw["matches"].extend(
            evidence(text, word, alternatives, "MORFOLOGIK_RULE_EN_US")["matches"]
        )
    return raw


def test_spelling_alternatives_preserve_message_and_introduced_name(monkeypatch):
    from unittest.mock import AsyncMock

    text = "I am Lovejit and I realy like baskteball."
    raw = spelling_evidence(
        text,
        [
            ("Lovejit", ["Lovejoy"]),
            ("realy", ["real", "ready", "really"]),
            ("baskteball", ["basketball"]),
        ],
    )
    monkeypatch.setattr(grammar.local, "check", AsyncMock(return_value=raw))
    result = asyncio.run(grammar.quick_check(text))
    assert result["state"] == "spelling"
    assert [s["word"] for s in result["spelling"]] == ["realy", "baskteball"]
    assert result["spelling"][1]["alternatives"] == ["basketball"]
    assert "corrected_text" not in result


def test_spelling_protects_name_from_recent_history():
    text = "lovejit likes drawing."
    raw = spelling_evidence(text, [("lovejit", ["lovejoy"])])
    assert (
        grammar.spelling_suggestions(
            text, raw, [{"learner_text": "My name is lovejit."}]
        )
        == []
    )


def test_spelling_capitalized_unknowns_offer_optional_alternatives():
    text = "I met Lovejit in Zorvania."
    raw = spelling_evidence(text, [("Lovejit", ["Lovejoy"]), ("Zorvania", ["Romania"])])
    suggestions = grammar.spelling_suggestions(text, raw)
    assert len(suggestions) == 2
    assert suggestions[0]["alternatives"] == ["Lovejoy"]
    assert suggestions[1]["alternatives"] == ["Romania"]


def test_spelling_rejects_splitting_and_unsafe_alternatives():
    text = "I like basketballing."
    raw = spelling_evidence(
        text,
        [
            (
                "basketballing",
                [
                    "basket balling",
                    "<script>",
                    "https://example.com",
                    "Basketball",
                    "basketball",
                    "basketball",
                ],
            )
        ],
    )
    assert grammar.spelling_suggestions(text, raw) == [
        {"word": "basketballing", "alternatives": ["Basketball"]}
    ]


def test_spelling_does_not_invent_word_choice_replacement():
    text = "I am Lovejit and I like Basketballing."
    raw = spelling_evidence(
        text, [("Lovejit", ["Lovejoy"]), ("Basketballing", ["Basket balling"])]
    )
    assert grammar.spelling_suggestions(text, raw) == [
        {"word": "Basketballing", "alternatives": []}
    ]


def test_spelling_unicode_offsets_and_mismatched_evidence():
    text = "😀 I recieved it."
    raw = spelling_evidence(text, [("recieved", ["received"])])
    assert grammar.spelling_suggestions(text, raw)[0]["word"] == "recieved"
    raw["matches"][0]["context"]["text"] = "wrong text"
    with pytest.raises(ValueError):
        grammar.spelling_suggestions(text, raw)


def test_spelling_disabled_for_unedited_recording(monkeypatch):
    from unittest.mock import AsyncMock

    text = "I recieved it."
    monkeypatch.setattr(
        grammar.local,
        "check",
        AsyncMock(return_value=spelling_evidence(text, [("recieved", ["received"])])),
    )
    result = asyncio.run(grammar.quick_check(text, spelling=False))
    assert "spelling" not in result


def test_spelling_runtime_names_are_case_insensitive():
    text = "I met ZORVANIA and Baskteball."
    raw = spelling_evidence(
        text, [("ZORVANIA", ["Romania"]), ("Baskteball", ["Basketball"])]
    )
    assert grammar.spelling_suggestions(text, raw, names={"zorvania"}) == [
        {"word": "Baskteball", "alternatives": ["Basketball"]}
    ]


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
    decision = grammar.evidence(text, expected, {"matches": []})
    assert decision["state"] == "provisional"
    assert decision["explanation"] == result["explanation"]


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


def test_common_phrase_rejects_unrelated_model_rewrite():
    result = grammar.evidence(
        "I like basketballing.", "I love playing basketball.", {"matches": []}
    )
    assert result["state"] == "withheld"


def test_common_phrase_full_check_uses_shared_rule(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        grammar.local,
        "generate",
        AsyncMock(return_value={"corrected_text": "I like playing basketball."}),
    )
    monkeypatch.setattr(
        grammar.local,
        "check",
        AsyncMock(return_value=evidence("I like basketballing.")),
    )
    result = asyncio.run(grammar.full_check("I like basketballing."))
    assert result["state"] == "offered"
    assert result["rule_id"] == "PLAY_BASKETBALL"


def test_common_article_sentence_initial():
    text = "An dog is here."
    result = grammar._select(text, evidence(text, "An", ["A"], "EN_A_VS_AN"))
    assert result["corrected_text"] == "A dog is here."


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
    assert grammar.evidence(text, expected, {"matches": []})["state"] == "provisional"


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
