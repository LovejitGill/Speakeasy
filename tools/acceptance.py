"""Real-service smoke checks using synthetic text, independent of historical scores."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conversation
import grammar
import local


async def main():
    failures = 0
    try:
        tags = await local.request(local.OLLAMA + "/api/tags")
        for model, digest in local.MODELS.items():
            assert any(
                m["name"] == model and m["digest"] == digest for m in tags["models"]
            )
        print("PASS: both Ollama model identities match.")
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
    try:
        await local.check("She go to work.")
        print("PASS: checker version and response verified; warm-up complete.")
    except Exception:  # noqa: BLE001 -- safe diagnostic boundary
        print("BLOCKED: checker service is unavailable or unsupported.")
    quick = await grammar.quick_check("She go to work.")
    print("Quick correction:", quick["state"])
    failures += quick["state"] != "offered"
    full_results = []
    for text in ("He work in a bank.", "Did you visited the castle?"):
        full = await grammar.full_check(text)
        full_results.append(full["state"])
        print("Full grammar:", full["state"])
    failures += "offered" not in full_results or "unavailable" in full_results
    try:
        count = await grammar.count_evidence("I packed seven bottle.")
        assert count["matches"]
        print("PASS: supplemental count rule.")
    except Exception:  # noqa: BLE001 -- safe diagnostic boundary
        print("BLOCKED: supplemental count rule.")
        failures += 1
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
