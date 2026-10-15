"""Real-service smoke checks using synthetic text, independent of historical scores."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speakeasy import conversation, grammar, local


async def main():
    failures = 0
    try:
        tags = await local.request(local.OLLAMA + "/api/tags")
        assert any(
            m["name"] == "qwen3:1.7b" and m["digest"] == local.MODELS["qwen3:1.7b"]
            for m in tags["models"]
        )
        print("PASS: conversation Ollama model identity matches.")
        await local.generate(
            "qwen3:1.7b",
            [{"role": "user", "content": "Return integer zero."}],
            {"type": "integer", "enum": [0]},
            budget=30,
            tokens=8,
        )
        print("PASS: explicit model warm-up complete.")
    except Exception:  # noqa: BLE001 -- diagnostic command does not expose service bodies
        print("BLOCKED: Ollama unavailable or model identity mismatch.")
        failures += 1
    reply = await conversation.respond("I enjoy reading.")
    print("Conversation path:", reply["path"])
    failures += reply["path"] != "model_selected"
    quick = await grammar.quick_check("I enjoy to swim.")
    print("Quick correction:", quick["state"])
    failures += quick["state"] != "offered"
    full_results = []
    for text in ("He work in a bank.", "Did you visited the castle?"):
        full = await grammar.full_check(text)
        full_results.append(full["state"])
        print("Full grammar:", full["state"])
    failures += "offered" not in full_results or "unavailable" in full_results
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
