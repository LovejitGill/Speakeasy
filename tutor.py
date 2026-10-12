"""Complete a typed turn, retaining a generated reply when storage fails."""

import asyncio
import uuid

import conversation
import grammar
import storage
from errors import StorageError


def submit(
    text,
    session,
    *,
    full_grammar=True,
    spelling=True,
    names=(),
    path=storage.DEFAULT_PATH,
):
    text = conversation.validate_text(text)
    rows = storage.history(session["id"], path)

    async def respond():
        # These independent bounded requests share one event loop, without threads.
        async with asyncio.TaskGroup() as tasks:
            reply = tasks.create_task(
                conversation.respond(
                    text,
                    history=rows,
                    level=session["level"],
                    scenario=session["scenario"],
                )
            )
            quick = tasks.create_task(
                grammar.quick_check(
                    text,
                    history=conversation.bounded_history(rows),
                    spelling=spelling,
                    names=names,
                )
            )
        return reply.result(), quick.result()

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
