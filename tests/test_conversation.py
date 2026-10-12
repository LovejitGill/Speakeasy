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
