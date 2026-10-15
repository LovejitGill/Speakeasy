"""Opt-in offline smoke checks against the installed T5 weights and ERRANT."""

import asyncio
import json
import os

import pytest

import grammar
import local

pytestmark = pytest.mark.skipif(
    os.environ.get("SPEAKWELL_REAL_T5_TEST") != "1",
    reason="Set SPEAKWELL_REAL_T5_TEST=1 to exercise cached model weights",
)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("I like swimming.", id="already-correct"),
        pytest.param("I go to school yesterday.", id="tense"),
        pytest.param("She work every day.", id="subject-verb-agreement"),
        pytest.param("I eat apple.", id="article"),
        pytest.param("I bought three apple yesterday.", id="plural"),
        pytest.param("I like swim every morning.", id="verb-form"),
        pytest.param("I recieve letters.", id="spelling"),
        pytest.param("I go yesterday and she work today.", id="multiple-mistakes"),
        pytest.param("He work in a bank.", id="sample-agreement"),
        pytest.param("Did you visited the castle?", id="sample-auxiliary"),
        pytest.param("I packed seven bottle.", id="sample-plural"),
    ],
)
def test_real_t5_offline_proposal_is_structured_not_quality_guaranteed(
    text, monkeypatch
):
    assert all(
        (local.GRAMMAR_MODEL_DIR / name).is_file() for name in local.GRAMMAR_MODEL_FILES
    )

    async def no_http(*args, **kwargs):
        raise AssertionError("grammar inference must not require Ollama or HTTP")

    monkeypatch.setattr(local, "request", no_http)
    result = asyncio.run(grammar.full_check(text))
    print(json.dumps({"input": text, "result": result}, ensure_ascii=False))
    assert result["state"] in {"offered", "withheld"}, result
    if result["state"] == "withheld":
        assert "does not mean" in result["message"]
        return
    assert result["proposal_provenance"] == "AI-generated"
    assert result["corrected_text"] != text
    assert result["edits"]
    for edit in result["edits"]:
        assert edit["operation"] in {"insertion", "deletion", "replacement"}
        assert edit["category"] and edit["explanation"]
        assert edit["provenance"] == "generic local"
        start = edit["original_span"]["start"]
        end = edit["original_span"]["end"]
        assert text[start:end] == edit["before"]
        start = edit["corrected_span"]["start"]
        end = edit["corrected_span"]["end"]
        assert result["corrected_text"][start:end] == edit["after"]
