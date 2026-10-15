import asyncio

import httpx
import pytest

from speakeasy import local
from speakeasy.errors import ServiceError, user_message


def test_no_remote_requests():
    for url in [
        "https://example.com",
        "http://localhost:11434/api/chat",
        "http://127.0.0.1:80",
    ]:
        with pytest.raises(ServiceError):
            asyncio.run(local.request(url))


def test_no_proxy_or_redirect(monkeypatch):
    factory = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/private"})

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return factory(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(local.httpx, "AsyncClient", client)
    with pytest.raises(ServiceError):
        asyncio.run(local.request(local.OLLAMA + "/api/tags"))
    assert seen == [local.OLLAMA + "/api/tags"]


def test_model_identity_precedes_content(monkeypatch):
    calls = []

    async def request(url, **kwargs):
        calls.append(url)
        return {"models": [{"name": "qwen3:1.7b", "digest": "wrong"}]}

    monkeypatch.setattr(local, "request", request)
    with pytest.raises(ServiceError):
        asyncio.run(local.generate("qwen3:1.7b", [], {}, budget=1))
    assert calls == [local.OLLAMA + "/api/tags"]


def test_deadline_cancels_request(monkeypatch):
    cancelled = []

    async def request(*args, **kwargs):
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(local, "request", request)
    with pytest.raises(ServiceError):
        asyncio.run(local.generate("qwen3:1.7b", [], {}, budget=0.02))
    assert cancelled == [True]


@pytest.mark.parametrize(
    "raw",
    [
        {"done": False},
        {"done": True, "done_reason": "length"},
        {"done": True, "message": {"content": "not JSON"}},
    ],
)
def test_incomplete_model_output(monkeypatch, raw):
    async def request(url, **kwargs):
        if url.endswith("/tags"):
            return {
                "models": [{"name": "qwen3:1.7b", "digest": local.MODELS["qwen3:1.7b"]}]
            }
        return raw

    monkeypatch.setattr(local, "request", request)
    with pytest.raises(ServiceError):
        asyncio.run(local.generate("qwen3:1.7b", [], {}, budget=1))


def test_private_error_not_displayed():
    assert "private learner text" not in user_message(
        RuntimeError("private learner text")
    )


def test_oversized_service_response(monkeypatch):
    factory = httpx.AsyncClient

    def client(**kwargs):
        return factory(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"x" * 262145)
            ),
            **kwargs,
        )

    monkeypatch.setattr(local.httpx, "AsyncClient", client)
    with pytest.raises(ServiceError):
        asyncio.run(local.request(local.OLLAMA + "/api/tags"))


def test_t5_child_receives_original_text_and_offline_settings(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    child = Mock(returncode=0)
    child.communicate = AsyncMock(return_value=(b'{"corrected_text":"He works."}', b""))
    child.wait = AsyncMock()
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(local.asyncio, "create_subprocess_exec", spawn)
    assert asyncio.run(local.correct("He work.")) == {"corrected_text": "He works."}
    import json

    assert json.loads(child.communicate.call_args.args[0]) == {"text": "He work."}
    assert "He work." not in spawn.call_args.args
    env = spawn.call_args.kwargs["env"]
    for key in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"]:
        assert env[key] == "1"
    child.wait.assert_awaited_once()
    child.kill.assert_not_called()


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_t5_cancellation_and_timeout_kill_and_reap_child(monkeypatch, mode):
    from unittest.mock import AsyncMock, Mock

    async def exercise():
        began = asyncio.Event()

        async def communicate(data):
            began.set()
            await asyncio.Event().wait()

        child = Mock(returncode=None)
        child.communicate = communicate
        child.wait = AsyncMock()
        monkeypatch.setattr(
            local.asyncio, "create_subprocess_exec", AsyncMock(return_value=child)
        )
        if mode == "timeout":
            timeout = asyncio.timeout
            monkeypatch.setattr(local.asyncio, "timeout", lambda _: timeout(0.01))
        task = asyncio.create_task(local.correct("He work."))
        await began.wait()
        if mode == "cancel":
            task.cancel()
        with pytest.raises(
            asyncio.CancelledError if mode == "cancel" else ServiceError
        ):
            await task
        child.kill.assert_called_once()
        child.wait.assert_awaited_once()

    asyncio.run(exercise())


def test_t5_missing_files_fail_before_loading_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "GRAMMAR_MODEL_DIR", tmp_path)
    with pytest.raises(ServiceError):
        local._correct_text("He work.")


@pytest.mark.parametrize("input_tokens,last_token", [(129, 1), (8, 5), (8, 1)])
def test_t5_cpu_loading_rejects_truncated_inputs_and_outputs(
    tmp_path, monkeypatch, input_tokens, last_token
):
    from unittest.mock import Mock

    import torch
    from transformers import BatchEncoding, T5ForConditionalGeneration, T5Tokenizer

    for name in local.GRAMMAR_MODEL_FILES:
        (tmp_path / name).touch()
    monkeypatch.setattr(local, "GRAMMAR_MODEL_DIR", tmp_path)
    tokenizer = Mock(
        return_value=BatchEncoding(
            {
                "input_ids": torch.ones((1, input_tokens), dtype=torch.long),
                "attention_mask": torch.ones((1, input_tokens), dtype=torch.long),
            }
        )
    )
    tokenizer.decode.return_value = "He works."
    tokenizer_loader = Mock(return_value=tokenizer)
    monkeypatch.setattr(T5Tokenizer, "from_pretrained", tokenizer_loader)
    model = Mock()
    model.to.return_value = model
    model.config.eos_token_id = 1
    model.generate.return_value = torch.tensor([[0, 9, last_token]])
    model_loader = Mock(return_value=model)
    monkeypatch.setattr(T5ForConditionalGeneration, "from_pretrained", model_loader)
    if input_tokens > 128 or last_token != 1:
        with pytest.raises(ServiceError):
            local._correct_text("He work.")
        tokenizer.decode.assert_not_called()
    else:
        assert local._correct_text("He work.") == "He works."
    tokenizer_loader.assert_called_once_with(
        str(tmp_path), local_files_only=True, legacy=True
    )
    tokenizer.assert_called_once_with(
        "gec: He work.", return_tensors="pt", truncation=False
    )
    if input_tokens > 128:
        model_loader.assert_not_called()
    else:
        model_loader.assert_called_once_with(str(tmp_path), local_files_only=True)
        model.to.assert_called_once_with("cpu")
        model.eval.assert_called_once()
