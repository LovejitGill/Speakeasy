"""Bounded HTTP to fixed loopback services; no proxies or redirects."""

import asyncio
import json

import httpx

from errors import ServiceError

OLLAMA = "http://127.0.0.1:11434"
CHECKER = "http://127.0.0.1:8081/v2/check"
MODELS = {
    "qwen3:1.7b": "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7",
    "qwen3:4b": "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
}


async def request(url, *, payload=None, form=None):
    if url not in {OLLAMA + "/api/tags", OLLAMA + "/api/chat", CHECKER}:
        raise ServiceError()
    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=30
        ) as client:
            method = "GET" if payload is None and form is None else "POST"
            async with client.stream(method, url, json=payload, data=form) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 262144:
                        raise ValueError("Oversized response")
                return json.loads(body)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ServiceError() from exc


async def generate(model, messages, schema, *, budget, tokens=64):
    try:
        async with asyncio.timeout(budget):
            tags = await request(OLLAMA + "/api/tags")
            if not any(
                m["name"] == model and m["digest"] == MODELS[model]
                for m in tags["models"]
            ):
                raise ValueError("Model identity mismatch")
            result = await request(
                OLLAMA + "/api/chat",
                payload={
                    "model": model,
                    "think": False,
                    "stream": False,
                    "keep_alive": "10m",
                    "format": schema,
                    "options": {
                        "num_ctx": 4096,
                        "num_predict": tokens,
                        "temperature": 0,
                        "seed": 42,
                    },
                    "messages": messages,
                },
            )
            if result.get("done") is not True or result.get("done_reason") == "length":
                raise ValueError("Incomplete output")
            return json.loads(result["message"]["content"])
    except (TimeoutError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ServiceError() from exc


async def check(text, *, budget=10):
    try:
        async with asyncio.timeout(budget):
            raw = await request(CHECKER, form={"language": "en-US", "text": text})
            if (
                raw["software"]["version"] != "6.6"
                or raw["warnings"]["incompleteResults"] is not False
                or not isinstance(raw["matches"], list)
            ):
                raise ValueError("Unverified checker")
            return raw
    except (TimeoutError, ValueError, TypeError, KeyError) as exc:
        raise ServiceError() from exc
