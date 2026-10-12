import asyncio

import pytest

import conversation as flow
from errors import PracticeError, ServiceError


def run(text, **kwargs):
    return asyncio.run(flow.respond(text, **kwargs))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    async def fail(*args, **kwargs):
        raise ServiceError()

    monkeypatch.setattr(flow.local, "generate", fail)


@pytest.mark.parametrize(
    "text",
    [
        "Stop.",
        "Please stop",
        "Let's stop",
        "Goodbye",
        "Thanks, that's enough practice for today.",
        "I need to stop practicing now.",
        "Please stop asking me questions.",
    ],
)
def test_stop_never_asks(text):
    assert "?" not in run(text)["reply"]


@pytest.mark.parametrize(
    "text",
    [
        "I enjoy reading. Don't ask me another question.",
        "No follow-up.",
        "I am tired. Do not ask questions.",
    ],
)
def test_no_followup(text):
    assert "?" not in run(text)["reply"]


def test_recall_only_learner_and_recent_evidence():
    history = [
        {
            "learner_text": "My sister enjoys reading.",
            "tutor_reply": "Your name is Alice.",
        }
    ]
    assert "don't have your name" in run("What is my name?", history=history)["reply"]
    rows = [
        {"learner_text": "My name is Alice.", "tutor_reply": "Hello."}
    ] + history * 4
    assert "don't have your name" in run("What is my name?", history=rows)["reply"]


def test_negation_retracts_hobby():
    history = [
        {"learner_text": "I enjoy reading.", "tutor_reply": "What do you read?"},
        {"learner_text": "I no longer enjoy reading.", "tutor_reply": "Understood."},
    ]
    reply = run("What do I enjoy? No follow-up.", history=history)["reply"]
    assert "no longer" in reply and "?" not in reply


def test_other_person_food_not_assigned_to_learner():
    reply = run(
        "My sister can't eat dairy. I'd like soup, and she wants a sandwich.",
        scenario="ordering food",
    )["reply"]
    assert "Your sister can't eat dairy" in reply
    assert "You can't" not in reply


@pytest.mark.parametrize(
    "text", ["I didn't pack a bag.", "If I packed a bag.", "My sister packed a bag."]
)
def test_packing_boundaries(text):
    assert "were you packing" not in run(text)["reply"]


def test_unfinished_keeps_negation():
    reply = run("I couldn't repair my bicycle.")["reply"]
    assert "help you repair your bicycle" in reply


def test_no_repeated_question():
    history = [
        {"learner_text": "I packed a bag.", "tutor_reply": "What were you packing for?"}
    ]
    assert (
        run("I packed a bag.", history=history)["reply"]
        == "How did you decide what to pack?"
    )


@pytest.mark.parametrize("selection", [True, -1, 99, "0", {}, None])
def test_invalid_selection_is_explicit_fallback(monkeypatch, selection):
    async def choose(*args, **kwargs):
        return selection

    monkeypatch.setattr(flow.local, "generate", choose)
    assert run("I enjoy reading.")["path"] == "local_fallback"


def test_valid_selection_and_bounded_history(monkeypatch):
    async def choose(model, messages, schema, **kwargs):
        assert model == "qwen3:1.7b"
        assert len(messages[1]["content"]) < 4500
        return 1

    monkeypatch.setattr(flow.local, "generate", choose)
    rows = [{"learner_text": "x" * 1000, "tutor_reply": "y" * 200}] * 6
    assert len(flow.bounded_history(rows)) == 2
    assert run("I enjoy reading.", history=rows)["path"] == "model_selected"


@pytest.mark.parametrize("text", ["", "x" * 1001, None, "\x00"])
def test_input_validation(text):
    with pytest.raises(PracticeError):
        run(text)


def test_language_reference_and_unknown():
    assert (
        "temporarily" in run("What is the difference between lend and borrow?")["reply"]
    )
    assert "supported answer" in run("What is quantum physics?")["reply"]


def pair(question, learner="I enjoy reading."):
    return {"learner_text": learner, "tutor_reply": question}


@pytest.mark.parametrize(
    "question,answer,expected",
    [
        (
            "What do you enjoy most about reading?",
            "The stories.",
            "example of what you enjoy about reading",
        ),
        (
            "How did you get interested in reading?",
            "At school.",
            "try next with reading",
        ),
        ("What were you packing for?", "A holiday.", "decide what to pack"),
        ("What got in the way?", "A missing tool.", "try first"),
        ("How did your walk feel?", "Relaxing.", "walk feel that way"),
        ("How will you prepare it?", "In the oven.", "ingredients"),
        (
            "Your sister can't eat dairy. What kind of soup would your sister like?",
            "Tomato.",
            "your sister like to have",
        ),
    ],
)
def test_short_answer_uses_latest_question(question, answer, expected):
    reply = run(answer, history=[pair(question)])["reply"]
    assert expected in reply
    assert "Thank you for sharing" not in reply


@pytest.mark.parametrize(
    "text",
    [
        "What do you mean?",
        "Could you explain?",
        "Please rephrase your question",
        "I don't understand",
        "Can you say that more simply?",
    ],
)
def test_clarification_explains_supported_question(text):
    reply = run(text, history=[pair("What got in the way?")])["reply"]
    assert "prevented" in reply
    assert "previous reply" not in reply
    assert "?" not in reply


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("daily activities", "today"),
        ("introductions", "name"),
        ("ordering food", "waiter"),
    ],
)
def test_clarify_opening_question(scenario, expected):
    assert expected in run("What do you mean?", scenario=scenario)["reply"]


def test_clarification_preserves_question_for_following_answer():
    rows = [pair("What do you enjoy most about reading?")]
    explanation = run("What do you mean?", history=rows)["reply"]
    rows.append(pair(explanation, "What do you mean?"))
    assert run("Please explain your question", history=rows)["reply"] == explanation
    assert (
        "example of what you enjoy about reading"
        in run("The stories.", history=rows)["reply"]
    )


def test_several_short_answers_progress_without_closing_loop():
    rows = [pair("What do you enjoy most about reading?")]
    replies = []
    for answer in ("The stories.", "Adventure stories.", "On weekends."):
        reply = run(answer, history=rows)["reply"]
        replies.append(reply)
        rows.append(pair(reply, answer))
    assert len(set(replies)) == 3
    assert all("reading" in reply and "?" in reply for reply in replies)


@pytest.mark.parametrize("answer", ["No.", "Yes.", "I don't know.", "Nothing."])
def test_uncertain_answer_gets_answering_help_without_inferred_fact(answer):
    reply = run(answer, history=[pair("How did your walk feel?")])["reply"]
    assert "Describe how you felt" in reply
    assert "You can also choose another topic" in reply


@pytest.mark.parametrize(
    "answer",
    [
        "Not me, my sister.",
        "I never liked it.",
        '"Relaxing," she said.',
        "Actually, I prefer swimming.",
    ],
)
def test_short_answer_does_not_presume_person_or_positive_fact(answer):
    reply = run(answer, history=[pair("What do you enjoy most about reading?")])[
        "reply"
    ]
    assert "enjoy about reading" not in reply
    assert "You enjoy" not in reply


def test_explicit_new_topic_overrides_previous_question():
    reply = run("I enjoy swimming.", history=[pair("What were you packing for?")])[
        "reply"
    ]
    assert "swimming" in reply and "pack" not in reply


def test_clarification_unknown_and_newest_reply_boundaries():
    rows = [pair("What got in the way?"), pair("An unsupported question?")]
    assert "checked explanation" in run("What do you mean?", history=rows)["reply"]
    assert "try first" not in run("A tool.", history=rows)["reply"]
    assert "?" not in run("Explain your question. No follow-up.", history=rows)["reply"]


def test_short_answer_does_not_create_recall_evidence():
    rows = [
        pair("Introduce yourself and tell me what you enjoy.", "Hello"),
        pair("What would you like to share about yourself?", "Alice"),
    ]
    assert "don't have your name" in run("What is my name?", history=rows)["reply"]


def test_continuation_controls_take_priority():
    rows = [pair("What got in the way?")]
    assert run("Stop.", history=rows)["path"] == "stop"
    assert "?" not in run("A missing tool. No follow-up.", history=rows)["reply"]


def test_clarify_uncertain_answer_keeps_original_question():
    rows = [pair("How did your walk feel?")]
    help_reply = run("I don't know.", history=rows)["reply"]
    rows.append(pair(help_reply, "I don't know."))
    reply = run("What do you mean?", history=rows)["reply"]
    assert "Describe how you felt during the walk" in reply


def test_clarification_does_not_revive_question_outside_bounded_history():
    rows = [pair("What got in the way?")]
    explanation = "Describe what prevented you from doing what you wanted to do."
    rows.extend(pair(explanation, "What do you mean?") for _ in range(4))
    assert "checked explanation" in run("What do you mean?", history=rows)["reply"]


def test_repeated_opening_clarification():
    explanation = run("What do you mean?", scenario="ordering food")["reply"]
    rows = [pair(explanation, "What do you mean?")]
    assert (
        run("Could you explain?", history=rows, scenario="ordering food")["reply"]
        == explanation
    )


def test_review_recall_after_person_correction_with_no_followup():
    rows = [
        pair("How did you get interested in cycling?", "I enjoy cycling."),
        pair("What would you like to add?", "Not me, my brother."),
    ]
    result = run("What do I enjoy? No follow-up.", history=rows)
    assert "don't have your hobby" in result["reply"]
    assert "I enjoy cycling" not in result["reply"]
    assert "?" not in result["reply"]
