"""Bounded loopback requests and offline CPU T5 inference in a child process."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from errors import ServiceError

OLLAMA = "http://127.0.0.1:11434"
MODELS = {
    "qwen3:1.7b": "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7",
    "qwen3:4b": "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
}

GRAMMAR_MODEL_DIR = Path(
    os.environ.get(
        "SPEAKWELL_GRAMMAR_MODEL",
        str(Path(__file__).parent / ".models/gec-t5_small"),
    )
)
GRAMMAR_MODEL_ID = "Unbabel/gec-t5_small"
GRAMMAR_MODEL_REVISION = "c958d53bfbce19c87342b69fc6bcaba7303d076f"
GRAMMAR_MODEL_FILES = (
    "config.json",
    "pytorch_model.bin",
    "spiece.model",
    "tokenizer_config.json",
    "special_tokens_map.json",
)


def _correct_text(text):
    """Child-only inference; missing assets must never trigger downloads."""
    if not all((GRAMMAR_MODEL_DIR / name).is_file() for name in GRAMMAR_MODEL_FILES):
        raise ServiceError()
    import torch
    from transformers import T5ForConditionalGeneration, T5Tokenizer

    torch.set_num_threads(4)
    tokenizer = T5Tokenizer.from_pretrained(
        str(GRAMMAR_MODEL_DIR), local_files_only=True, legacy=True
    )
    inputs = tokenizer("gec: " + text, return_tensors="pt", truncation=False)
    # Refuse overlong input instead of silently correcting a truncated sentence.
    if inputs.input_ids.shape[-1] > 128:
        raise ServiceError()
    model = T5ForConditionalGeneration.from_pretrained(
        str(GRAMMAR_MODEL_DIR), local_files_only=True
    ).to("cpu")
    model.eval()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=128,
            num_beams=5,
            do_sample=False,
            early_stopping=True,
        )[0]
    if output[-1].item() != model.config.eos_token_id:
        raise ServiceError()
    return tokenizer.decode(output, skip_special_tokens=True)


async def correct(text):
    """Adapt local T5 to the proposal contract; cancellation kills and reaps it."""
    process = None
    try:
        async with asyncio.timeout(45):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(Path(__file__).resolve()),
                "--grammar",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={
                    **os.environ,
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "HF_HUB_DISABLE_TELEMETRY": "1",
                },
            )
            stdout, _ = await process.communicate(json.dumps({"text": text}).encode())
            if process.returncode or len(stdout) > 16384:
                raise ServiceError()
            return json.loads(stdout)
    except (OSError, TimeoutError, ValueError) as exc:
        raise ServiceError() from exc
    finally:
        if process is not None:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def request(url, *, payload=None):
    if url not in {OLLAMA + "/api/tags", OLLAMA + "/api/chat"}:
        raise ServiceError()
    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=30
        ) as client:
            method = "GET" if payload is None else "POST"
            async with client.stream(method, url, json=payload) as response:
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


if __name__ == "__main__" and sys.argv[1:] == ["--grammar"]:
    try:
        text = json.loads(sys.stdin.buffer.read(16384))["text"]
        print(json.dumps({"corrected_text": _correct_text(text)}))
    except Exception:  # noqa: BLE001 -- do not expose learner text or model diagnostics
        sys.exit(1)
