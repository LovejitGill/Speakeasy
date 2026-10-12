"""Complete a typed turn, retaining a generated reply when storage fails."""

import asyncio
import uuid

import conversation
import grammar
import storage
from errors import StorageError


def submit(text, session, *, full_grammar=True, path=storage.DEFAULT_PATH):
    text = conversation.validate_text(text)
    rows = storage.history(session["id"], path)

    async def respond():
        reply = await conversation.respond(
            text, history=rows, level=session["level"], scenario=session["scenario"]
        )
        # Quick feedback has a small independent budget; no extra inference thread.
        return reply, await grammar.quick_check(text)

    reply, quick = asyncio.run(respond())
    turn = {
        "id": str(uuid.uuid4()),
        "session_id": session["id"],
        "learner_text": text,
        "tutor_reply": reply["reply"],
        "path": reply["path"],
        "quick": quick,
        "full_grammar": full_grammar,
    }
    try:
        storage.save_turn(turn, grammar=full_grammar, path=path)
    except StorageError:
        return turn, False
    return turn, True
