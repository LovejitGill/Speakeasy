"""Streamlit presentation only; jobs and inference do not depend on rendering."""

import atexit
import os
from pathlib import Path

import streamlit as st

import conversation
import speech
import storage
import tutor
from errors import user_message
from worker import Worker

DB_PATH = Path(os.environ.get("SPEAKWELL_DB_PATH", str(storage.DEFAULT_PATH))).resolve()


@st.cache_resource
def worker(path):
    instance = Worker(path)
    atexit.register(instance.close)
    return instance


def feedback(result, label):
    if not result:
        return
    with st.expander(label):
        if result["state"] == "offered":
            st.text(result["corrected_text"])
            st.text(result["explanation"])
            st.caption("Suggested correction; automated feedback can be wrong.")
        else:
            st.caption(
                result.get(
                    "message",
                    "No supported correction found; this is not proof of correct grammar.",
                )
            )


def render_turn(turn):
    with st.chat_message("user"):
        st.text(turn["learner_text"])
    with st.chat_message("assistant"):
        st.text(turn["tutor_reply"])
        if turn["path"] == "local_fallback":
            st.caption(
                "Prepared reply used: the local model was unavailable or its selection was invalid."
            )
        elif turn["path"] != "model_selected":
            st.caption("Prepared response")
        feedback(turn.get("quick"), "Quick correction")
        feedback(turn.get("grammar"), "Full grammar check")
        state = turn.get("job_state")
        if state in {"pending", "running"}:
            st.caption("Full grammar check: " + state)
            if st.button("Cancel grammar check", key="cancel_" + turn["id"]):
                storage.cancel(turn["id"], DB_PATH)
                st.rerun()
        elif state == "cancelled":
            st.caption("Full grammar check cancelled.")


@st.fragment(run_every=2)
def render_history(session_id):
    try:
        worker(str(DB_PATH)).start()
        turns = storage.history(session_id, DB_PATH)
        st.caption(f"{len(turns)} completed turns")
        for turn in turns:
            render_turn(turn)
    except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
        st.error(user_message(exc))


def recording():
    with st.expander("Record a message"):
        st.caption(
            "Record 0.3–60 seconds. Audio stays in memory. Transcripts are never sent automatically."
        )
        audio = st.audio_input(
            "Recording",
            sample_rate=16000,
            key=f"audio_{st.session_state.get('audio_epoch', 0)}",
        )
        if st.button("Transcribe recording", disabled=audio is None):
            try:
                with st.spinner("Transcribing locally…"):
                    transcript = speech.transcribe(audio.getvalue())
                st.session_state.transcript = transcript
            except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
                st.error(user_message(exc))
        if "transcript" in st.session_state:
            st.text_area("Review and edit transcript", key="transcript", height=100)
            st.caption(
                "Using this transcript replaces the draft below. Sending is a separate action."
            )
            if st.button("Use reviewed transcript as draft"):
                st.session_state.draft = st.session_state.transcript
            if st.button("Discard recording and transcript"):
                st.session_state.pop("transcript", None)
                st.session_state.audio_epoch = (
                    st.session_state.get("audio_epoch", 0) + 1
                )
                st.rerun()


def main():
    st.set_page_config(page_title="Speakwell", page_icon="💬")
    st.title("Speakwell")
    st.caption("Local English practice · typed messages or reviewed recordings")
    st.session_state.setdefault("draft", "")
    if st.session_state.pop("clear_draft", False):
        st.session_state.draft = ""
        st.session_state.pop("transcript", None)
        st.session_state.audio_epoch = st.session_state.get("audio_epoch", 0) + 1
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
        unsaved or st.session_state.draft or st.session_state.get("transcript")
    )
    with st.sidebar:
        st.header("Practice")
        level = st.selectbox("Level", conversation.LEVELS)
        scenario = st.selectbox("Scenario", conversation.SCENARIOS)
        if st.button("Start new session", disabled=protected):
            try:
                st.query_params.session = storage.create_session(
                    level, scenario, DB_PATH
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
                st.error(user_message(exc))
        if available:
            selected = st.selectbox(
                "Saved sessions",
                available,
                format_func=lambda row: (
                    f"{row['created']} · {row['scenario']} · {row['id'][:6]}"
                ),
            )
            if st.button("Open session", disabled=protected):
                st.query_params.session = selected["id"]
                st.rerun()
        st.caption(
            "Settings apply to new sessions. Save or clear drafts before switching sessions."
        )
        full = st.checkbox("Full grammar check after sending", value=True)
        st.caption(
            "Sent text is stored locally. Keep session URLs private. This app has no accounts."
        )
    if not session:
        st.info("Start a session or open a saved one to practise.")
        return
    st.caption(f"{session['level'].capitalize()} · {session['scenario']}")
    st.text(conversation.OPENERS[session["scenario"]])
    render_history(session["id"])
    if unsaved:
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
        return
    recording()
    st.text_area("Your message", key="draft", height=120)
    st.caption(f"{len(st.session_state.draft)}/1,000 characters")
    if st.button("Send", type="primary", disabled=not st.session_state.draft.strip()):
        try:
            with st.spinner("Preparing a reply…"):
                turn, saved = tutor.submit(
                    st.session_state.draft, session, full_grammar=full, path=DB_PATH
                )
            if saved:
                st.session_state.clear_draft = True
            else:
                st.session_state.unsaved = turn
            st.rerun()
        except Exception as exc:  # noqa: BLE001 -- safe UI/service boundary
            st.error(user_message(exc))
    if st.button("Clear draft"):
        st.session_state.clear_draft = True
        st.rerun()


if __name__ == "__main__":
    main()
