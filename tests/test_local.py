import asyncio

import httpx
import pytest

import local
from errors import ServiceError, user_message


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


@pytest.mark.parametrize(
    "raw",
    [
        {
            "software": {"version": "6.7"},
            "warnings": {"incompleteResults": False},
            "matches": [],
        },
        {
            "software": {"version": "6.6"},
            "warnings": {"incompleteResults": True},
            "matches": [],
        },
        {"software": {"version": "6.6"}, "matches": []},
    ],
)
def test_unverified_checker_is_unavailable(monkeypatch, raw):
    async def request(*a, **kw):
        return raw

    monkeypatch.setattr(local, "request", request)
    with pytest.raises(ServiceError):
        asyncio.run(local.check("Hello"))
