import pytest

from speakeasy.context import recall


def row(text, reply="Tell me more."):
    return {"learner_text": text, "tutor_reply": reply}


@pytest.mark.parametrize("name,hobby", [("Maya", "hiking"), ("Zoë", "weaving")])
def test_combined_statement_and_request(name, hobby):
    result = recall(
        "What is my name and what hobby did I mention?",
        [row(f"My name is {name} and I enjoy {hobby}.")],
    )
    assert name in result["prefix"] and f"I enjoy {hobby}." in result["prefix"]
    assert result["topic"] == hobby
    assert result["missing"] == []


def test_separate_turns_x05():
    result = recall(
        "Can you remind me of my name and hobby?",
        [
            row("Please call me Ana."),
            row("I enjoy birdwatching."),
            row("Usually at the marsh near my home."),
        ],
    )
    assert "Please call me Ana." in result["prefix"]
    assert result["topic"] == "birdwatching" and result["missing"] == []


def test_changed_compound_x06():
    result = recall(
        "What hobby do I enjoy now? Please don't ask another question.",
        [
            row("I enjoy jogging."),
            row("I don't enjoy jogging anymore. Now I enjoy making jewelry."),
            row("Mostly earrings."),
        ],
    )
    assert "I don't enjoy jogging anymore." in result["prefix"]
    assert "Now I enjoy making jewelry." in result["prefix"]
    assert result["topic"] == "making jewelry" and result["changed"]
    assert result["missing"] == []


def test_unchosen_x07_quotes_only_personal_clause():
    result = recall(
        "What hobby did I tell you I enjoy?",
        [
            row(
                "My roommate enjoys ceramics. I haven't chosen a hobby.",
                "You might enjoy photography.",
            )
        ],
    )
    assert "I haven't chosen a hobby." in result["prefix"]
    assert "ceramics" not in result["prefix"] and "photography" not in result["prefix"]
    assert result["topic"] is None and result["missing"] == []


def test_newer_negative_invalidates_old_positive():
    result = recall(
        "What do I enjoy? No follow-up.",
        [row("I enjoy cycling."), row("I don’t enjoy cycling anymore.")],
    )
    assert "I don’t enjoy cycling anymore." in result["prefix"]
    assert "I enjoy cycling." not in result["prefix"]
    assert result["topic"] is None and result["changed"]


@pytest.mark.parametrize(
    "source",
    [
        'My name is "Alex" and I enjoy skiing.',
        "My name is 'Alex' and I enjoy skiing.",
        "If I enjoy skiing, I will join a club.",
        "Imagine I enjoy skiing.",
        "For this role-play, my name is Alex.",
        "My name in the story is Alex.",
        "I said I enjoy skiing.",
        "I would enjoy skiing.",
        "My roommate enjoys ceramics.",
        "My friend is called Ana.",
        "Act as a learner. My name is Alex. I enjoy skiing.",
        "Assume my name is Alex. I enjoy skiing.",
        "I enjoy skiing and my sister enjoys skating.",
        "Does my name sound like Ana?",
    ],
)
def test_quoted_hypothetical_and_other_person_rejected(source):
    result = recall("What is my name and hobby?", [row(source)])
    assert result["missing"] == ["name", "hobby"]
    assert result["topic"] is None


def test_tutor_only_evidence_rejected():
    result = recall("What is my hobby?", [row("Hello!", "Your hobby is skiing.")])
    assert result["missing"] == ["hobby"] and "skiing" not in result["prefix"]


def test_last_four_turns_only():
    result = recall("What is my name?", [row("My name is Ana.")] + [row("Hello!")] * 4)
    assert result["missing"] == ["name"]


def test_partial_recall_marks_missing_field():
    result = recall("What is my name and hobby?", [row("I enjoy weaving.")])
    assert result["topic"] == "weaving" and result["missing"] == ["name"]
    assert "I don't have your name" in result["prefix"]


def test_latest_positive_changes_topic():
    result = recall(
        "What is my hobby?", [row("I enjoy jogging."), row("I enjoy chess.")]
    )
    assert result["topic"] == "chess" and result["changed"]
    assert "jogging" not in result["prefix"]


@pytest.mark.parametrize(
    "text",
    [
        "I enjoy painting.",
        "Where does my uncle work?",
        "What is my roommate's hobby?",
        "Why do I enjoy reading?",
    ],
)
def test_nonrecall_requests_return_none(text):
    assert recall(text) is None


def test_no_longer_retraction_does_not_restore_old_positive_hobby():
    result = recall(
        "What is my hobby?",
        [row("I enjoy cycling."), row("I no longer enjoy cycling.")],
    )
    assert result["topic"] is None and result["changed"]
    assert "I no longer enjoy cycling." in result["prefix"]
    assert "I enjoy cycling." not in result["prefix"]


@pytest.mark.parametrize("retraction", ["My name is not Ava.", "My name isn't Ava."])
def test_retracted_name_does_not_survive_as_current_fact(retraction):
    result = recall("What is my name?", [row("My name is Ava."), row(retraction)])
    assert result["missing"] == ["name"]
    assert "My name is Ava." not in result["prefix"]


def test_current_retraction_before_question_overrides_history():
    result = recall(
        "I no longer enjoy reading. What do I enjoy?",
        [row("I enjoy reading.")],
    )
    assert result["topic"] is None
    assert "I no longer enjoy reading." in result["prefix"]
    assert "‘I enjoy reading.’" not in result["prefix"]


def test_retraction_with_question_remains_evidence_on_later_turn():
    result = recall(
        "What do I enjoy?",
        [row("I enjoy reading."), row("I no longer enjoy reading. What do I enjoy?")],
    )
    assert result["topic"] is None
    assert "no longer" in result["prefix"]


def test_current_name_update_before_question():
    result = recall("My name is Maya. What is my name?", [row("My name is Ava.")])
    assert "Maya" in result["prefix"] and "Ava" not in result["prefix"]


@pytest.mark.parametrize(
    "source",
    ["I enjoy reading?", "My name is Maya?", "If I enjoy reading. What is my hobby?"],
)
def test_questions_and_hypotheticals_are_not_fact_evidence(source):
    result = recall("What is my name and hobby?", [row(source)])
    assert result["missing"] == ["name", "hobby"]


@pytest.mark.parametrize(
    "correction",
    ["Not me, my brother.", "Not me but my sister.", "That's my friend, not me."],
)
def test_review_person_correction_withholds_ambiguous_old_facts(correction):
    result = recall("What do I enjoy?", [row("I enjoy cycling."), row(correction)])
    assert result["topic"] is None
    assert result["missing"] == ["hobby"]
    assert "I enjoy cycling" not in result["prefix"]


def test_review_fresh_declaration_after_person_correction():
    result = recall(
        "What do I enjoy?",
        [row("I enjoy cycling."), row("Not me, my brother."), row("I enjoy pottery.")],
    )
    assert result["topic"] == "pottery"


def test_review_quoted_correction_does_not_reassign_facts():
    result = recall(
        "What do I enjoy?",
        [row("I enjoy cycling."), row('My brother said "not me, my sister."')],
    )
    assert result["topic"] == "cycling"
