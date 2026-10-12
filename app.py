"""Streamlit presentation only; jobs and inference do not depend on rendering."""

import atexit
import hashlib
import os
from pathlib import Path

import streamlit as st

import conversation
import speech
import storage
import tutor
from errors import user_message
from worker import Worker

STYLE_PATH = Path(__file__).parent / "assets" / "style.css"

DB_PATH = Path(os.environ.get("SPEAKWELL_DB_PATH", str(storage.DEFAULT_PATH))).resolve()


@st.cache_resource
def worker(path):
    instance = Worker(path)
    atexit.register(instance.close)
    return instance


def feedback(result, label, turn_id):
    if not result:
        return
    offered = result["state"] == "offered"
    status = (
        "Suggested edit"
        if offered
        else (
            "Unavailable" if result["state"] == "unavailable" else "No supported edit"
        )
    )
    if label == "Quick feedback" and result["state"] == "withheld":
        status = "Nice effort! No supported corrections found."
    names = st.session_state.get("spelling_names", set())
    spellings = [
        item
        for item in result.get("spelling", [])
        if item["word"].casefold() not in names
    ]
    if spellings:
        status = "Suggested edit and spelling" if offered else "Spelling to review"
    with st.expander(f"{label} · {status}", expanded=offered or bool(spellings)):
        if offered:
            st.caption("SUGGESTED SENTENCE")
            st.text(result["corrected_text"])
            st.caption("WHY THIS CHANGE")
            st.text(result["explanation"])
            st.caption("Suggested correction; automated feedback can be wrong.")
        else:
            st.caption(
                result.get(
                    "message",
                    "No supported correction found; this is not proof of correct grammar.",
                )
            )
        for item in spellings:
            st.text(f"Check this word: {item['word']}")
            if item["alternatives"]:
                st.text("Did you mean: " + ", ".join(item["alternatives"]) + "?")
            else:
                st.caption("No reliable spelling suggestion was found.")
            st.caption("Or is this a name?")
            if st.button(
                "This is a name", key=f"name_{turn_id}_{label}_{item['word']}"
            ):
                st.session_state.spelling_names = names | {item["word"].casefold()}
                st.rerun()
        if spellings:
            st.caption(
                "Names you confirm are remembered until this browser app session ends."
            )
            st.caption(
                "These are suggestions, not automatic replacements. Choose only wording that matches what you mean."
            )


def render_turn(turn, *, include_reply=True):
    with st.chat_message("user"):
        st.caption("YOU")
        st.text(turn["learner_text"])
        st.divider()
        st.caption("Pointers:")
        feedback(turn.get("quick"), "Quick feedback", turn["id"])
        feedback(turn.get("grammar"), "Full grammar check", turn["id"])
        state = turn.get("job_state")
        if state in {"pending", "running"}:
            st.caption(
                "Full grammar check: waiting to start"
                if state == "pending"
                else "Full grammar check: checking your message…"
            )
            if st.button("Cancel grammar check", key="cancel_" + turn["id"]):
                storage.cancel(turn["id"], DB_PATH)
                st.rerun()
        elif state == "cancelled":
            st.caption("Full grammar check cancelled.")

    if include_reply:
        render_reply(turn)


def render_reply(turn):
    with st.chat_message("assistant"):
        st.caption("SPEAKEASY")
        st.text(turn["tutor_reply"])
        if turn["path"] == "local_fallback":
            st.caption(
                "Prepared reply used: the local model was unavailable or its selection was invalid."
            )
        elif turn["path"] != "model_selected":
            st.caption("Prepared response")


@st.fragment(run_every=2)
def render_history(session, *, older=False):
    try:
        worker(str(DB_PATH)).start()
        turns = storage.history(session["id"], DB_PATH)
        if older:
            previous = turns if st.session_state.get("unsaved") else turns[:-1]
            if previous:
                with st.expander("Conversation History", expanded=False):
                    for turn in reversed(previous):
                        render_turn(turn)
            return
        title, count = st.columns([3, 2], vertical_alignment="center")
        with title:
            st.subheader("Your conversation")
        with count:
            st.caption(f"{len(turns)} completed turns")
        if turns:
            render_turn(turns[-1], include_reply=False)
            return turns[-1]
    except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
        st.error(user_message(exc))


def reset_recording():
    st.session_state.audio_epoch = st.session_state.get("audio_epoch", 0) + 1
    st.session_state.pop("processed_audio", None)
    st.session_state.pop("recording_error", None)


def recording():
    audio = st.audio_input(
        "Record a message",
        sample_rate=16000,
        key=f"audio_{st.session_state.get('audio_epoch', 0)}",
    )
    if audio is None:
        return
    if st.button("Record again", icon=":material/mic:"):
        reset_recording()
        st.rerun()
    data = audio.getvalue()
    fingerprint = hashlib.sha256(data).hexdigest()
    retry = False
    if st.session_state.get("recording_error"):
        st.error(st.session_state.recording_error)
        retry = st.button("Retry transcription")
    if fingerprint != st.session_state.get("processed_audio") or retry:
        st.session_state.pop("recording_error", None)
        try:
            with st.spinner("Transcribing locally…"):
                # Keep the result outside widget state before spinner cleanup can
                # yield to a queued rerun. Apply it when the textbox renders next.
                st.session_state.pending_transcript = speech.transcribe(data)
                st.session_state.processed_audio = fingerprint
        except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
            st.session_state.recording_error = user_message(exc)
            st.session_state.processed_audio = fingerprint
        # A fresh render requires a separate, deliberate Send after transcription.
        st.rerun()


def main():
    st.set_page_config(
        page_title="SpeakEasy · English practice", page_icon="💬", layout="wide"
    )
    # Only trusted local styles and authored markup go through st.html.
    st.html("<style>" + STYLE_PATH.read_text() + "</style>")
    st.html('<p class="sw-eyebrow">Your English practice space</p>')
    st.session_state.setdefault("draft", "")
    if "pending_transcript" in st.session_state:
        st.session_state.draft = st.session_state.pop("pending_transcript")
        st.session_state.recorded_draft = st.session_state.draft
    if st.session_state.pop("clear_draft", False):
        st.session_state.draft = ""
        st.session_state.pop("recorded_draft", None)
        reset_recording()
    try:
        storage.initialize(DB_PATH)
        available = storage.sessions(DB_PATH)
    except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
        st.error(user_message(exc))
        if st.session_state.get("unsaved"):
            st.warning(
                "This reply is NOT saved. Keep this page open and retry loading history."
            )
            render_turn(st.session_state.unsaved)
        st.text_area("Your message", key="draft", disabled=True)
        st.button("Retry loading history")
        return
    session_id = st.query_params.get("session")
    session = next((row for row in available if row["id"] == session_id), None)
    unsaved = st.session_state.get("unsaved")
    if session_id and session is None:
        st.warning(
            "That session could not be found. Choose a saved session or start a new one."
        )
    protected = bool(
        unsaved or st.session_state.draft or st.session_state.get("processed_audio")
    )
    with st.sidebar:
        st.html(
            '<div class="sw-brand"><span class="sw-mark" aria-hidden="true">s</span><span class="sw-wordmark">SpeakEasy</span></div>'
        )
        st.caption("ENGLISH · LOCAL PRACTICE")
        st.divider()
        st.subheader("Set up your practice")
        level = st.selectbox("Level", conversation.LEVELS, format_func=str.capitalize)
        scenario = st.selectbox(
            "Scenario", conversation.SCENARIOS, format_func=str.capitalize
        )
        if st.button(
            "Start new session",
            disabled=protected,
            type="primary",
            width="stretch",
            icon=":material/add:",
        ):
            try:
                st.query_params.session = storage.create_session(
                    level, scenario, DB_PATH
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
                st.error(user_message(exc))
        st.caption("Level and scenario apply to new sessions.")
        if protected:
            st.caption("Save or clear your draft before switching sessions.")
        st.divider()
        st.subheader("Your sessions")
        if available:
            selected = st.selectbox(
                "Saved sessions",
                available,
                format_func=lambda row: (
                    f"{row['created']} · {row['scenario']} · {row['id'][:6]}"
                ),
            )
            if st.button(
                "Open session",
                disabled=protected,
                width="stretch",
                icon=":material/history:",
            ):
                st.query_params.session = selected["id"]
                st.rerun()
        else:
            st.caption("Saved conversations will appear here.")
        st.divider()
        st.subheader("Feedback")
        full = st.checkbox("Full grammar check after sending", value=True)
        st.caption("A closer look at your grammar, after your reply is ready.")
        with st.expander("About your practice", icon=":material/info:"):
            st.caption(
                "Sent text stays on this computer. Recordings are not saved. Keep session URLs private; this app has no accounts."
            )
            st.caption(
                "Feedback can be wrong. No suggested correction does not mean error-free English."
            )
    if not session:
        with st.container(key="welcome"):
            st.html('<span class="sw-tag">One conversation at a time</span>')
            st.header("What would you like to talk about?")
            st.write(
                "Choose a level and an everyday scenario in the sidebar, then start your session. Or return to a saved conversation."
            )
            st.html("""<div class="sw-features">
                <div class="sw-feature"><strong>01 · Make it yours</strong><p>Introductions, daily activities, or ordering a meal. Choose a situation you want to practise.</p></div>
                <div class="sw-feature"><strong>02 · Type or record</strong><p>Write a message or record your voice. Review and edit your transcript before sending.</p></div>
                <div class="sw-feature"><strong>03 · Reflect and return</strong><p>Explore grammar suggestions and pick up a saved conversation whenever you're ready.</p></div>
                </div>""")
        return
    st.html(
        '<div class="sw-brand sw-main-brand"><span class="sw-wordmark">SpeakEasy</span></div>'
    )
    st.title(f"{session['level'].title()} - {session['scenario'].title()}")
    latest = None
    if not unsaved:
        latest = render_history(session)
    if unsaved:
        st.subheader("Your conversation")
        st.warning(
            "This reply is NOT saved. Keep this page open and retry saving. Grammar work has not been queued."
        )
        render_turn(unsaved)
        st.text_area("Your message", key="draft", disabled=True)
        if st.button("Retry saving reply"):
            try:
                storage.save_turn(
                    unsaved, grammar=unsaved["full_grammar"], path=DB_PATH
                )
                del st.session_state.unsaved
                st.session_state.clear_draft = True
                st.rerun()
            except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
                st.error(user_message(exc))
        render_history(session, older=True)
        return
    with st.container(key="composer"):
        if latest:
            render_reply(latest)
        else:
            with st.chat_message("assistant"):
                st.caption("SPEAKEASY")
                st.text(conversation.OPENERS[session["scenario"]])
        st.divider()
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader("Record your response:", anchor=False, width="content")
            st.caption(
                "Record, then review or edit before sending. Speak for 1–60 seconds and click Stop when finished.",
                width="content",
            )
        recording()
        st.text_area(
            "Your message",
            key="draft",
            height=140,
            placeholder="You can also type your response here.",
        )
        st.caption(f"{len(st.session_state.draft)}/1,000 characters")
        with st.container(horizontal=True, vertical_alignment="center"):
            if st.button(
                "Send",
                type="primary",
                icon=":material/arrow_upward:",
            ):
                try:
                    with st.spinner("Preparing a reply…"):
                        turn, saved = tutor.submit(
                            st.session_state.draft,
                            session,
                            full_grammar=full,
                            spelling=st.session_state.draft
                            != st.session_state.get("recorded_draft"),
                            names=st.session_state.get("spelling_names", set()),
                            path=DB_PATH,
                        )
                    if saved:
                        st.session_state.clear_draft = True
                    else:
                        st.session_state.unsaved = turn
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
                    st.error(user_message(exc))
            if st.button("Clear draft", type="tertiary"):
                st.session_state.clear_draft = True
                st.rerun()

    render_history(session, older=True)


if __name__ == "__main__":
    main()
