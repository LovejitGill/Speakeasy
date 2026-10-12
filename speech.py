"""Validated WAV input and offline Whisper inference in a time-bounded child process."""

import io
import json
import os
import subprocess
import sys
import threading
import wave
from pathlib import Path

import numpy as np

from errors import PracticeError


class TranscriptionError(PracticeError):
    pass


class UnclearSpeechError(TranscriptionError):
    pass


class SpeechServiceError(TranscriptionError):
    pass


MODEL_DIR = Path(
    os.environ.get(
        "SPEAKWELL_SPEECH_MODEL",
        str(Path(__file__).parent / ".models/faster-whisper-base.en"),
    )
)

MODEL_ID = "Systran/faster-whisper-base.en"


MODEL_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"


MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


MAX_SECONDS = 60


MAX_BYTES = 2_000_000


_INFERENCE_LOCK = threading.Lock()


def decode_recording(audio: bytes) -> np.ndarray:
    """Accept the 16 kHz, mono PCM16 WAV produced by our recording widget."""
    if not isinstance(audio, bytes) or not audio:
        raise TranscriptionError("Record a short sentence first.")
    if len(audio) > MAX_BYTES:
        raise TranscriptionError("Recording is too large. Keep it under 60 seconds.")
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (
                1,
                2,
                16000,
            ) or wav.getcomptype() != "NONE":
                raise TranscriptionError("Use a mono, 16 kHz, 16-bit WAV recording.")
            frames = wav.getnframes()
            if not 0.3 <= frames / 16000 <= MAX_SECONDS:
                raise TranscriptionError("Record between 0.3 and 60 seconds of speech.")
            raw = wav.readframes(frames)
            if len(raw) != frames * 2:
                raise TranscriptionError(
                    "Recording is incomplete. Please record again."
                )
    except (wave.Error, EOFError, OSError) as exc:
        raise TranscriptionError("Cannot read this WAV. Please record again.") from exc
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    # This catches near-silence, not all noise; VAD handles speech detection later.
    if float(np.sqrt(np.mean(samples**2))) < 0.001:
        raise UnclearSpeechError(
            "I didn't catch clear speech. Please repeat your statement."
        )
    return samples


def get_model():
    """Load once per Python process; normal use must not download missing files."""
    if not all((MODEL_DIR / filename).is_file() for filename in MODEL_FILES):
        raise SpeechServiceError(
            "Speech model missing. Run: uv run python tools/setup.py speech"
        )
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(MODEL_DIR),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
        local_files_only=True,
    )


def transcribe_audio(audio: bytes) -> str:
    """Validate, detect speech, then consume the model's lazy segment iterator."""
    samples = decode_recording(audio)
    try:
        # Serialize model access, including lazy iteration, to bound CPU use.
        with _INFERENCE_LOCK:
            segments, _ = get_model().transcribe(
                samples,
                language="en",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            parts = []
            for segment in segments:
                if segment.no_speech_prob > 0.6 or segment.avg_logprob < -1.0:
                    raise UnclearSpeechError(
                        "I couldn't get a clear transcript. Please repeat your statement."
                    )
                parts.append(segment.text.strip())
    except TranscriptionError:
        raise
    except Exception as exc:
        # Includes errors during lazy generation, not just model construction.
        raise SpeechServiceError(
            "Local transcription failed. Check the speech model or use typed input."
        ) from exc
    text = " ".join(part for part in parts if part).strip()
    if not text:
        raise UnclearSpeechError(
            "I didn't catch clear speech. Please repeat your statement."
        )
    return text


def transcribe(audio):
    # Reject bad input before allocating a model process. Audio never reaches disk.
    decode_recording(audio)
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"},
    )
    try:
        stdout, _ = process.communicate(audio, timeout=90)
        if process.returncode or len(stdout) > 10000:
            raise SpeechServiceError(
                "Local transcription failed. Check the speech model or use typed input."
            )
        result = json.loads(stdout)
        if result.get("state") == "unclear":
            raise UnclearSpeechError(
                "I couldn't get a clear transcript. Please record again."
            )
        text = result["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("Invalid transcript")
        return text
    except (subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        raise SpeechServiceError(
            "Transcription could not finish. Your draft is unchanged; retry or type instead."
        ) from exc
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


if __name__ == "__main__":
    try:
        text = transcribe_audio(sys.stdin.buffer.read(MAX_BYTES + 1))
        print(json.dumps({"text": text}))
    except UnclearSpeechError:
        print(json.dumps({"state": "unclear"}))
    except Exception:  # noqa: BLE001 -- preserve jobs and suppress private diagnostics
        sys.exit(1)
