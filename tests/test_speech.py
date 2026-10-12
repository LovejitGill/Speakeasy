import io
import subprocess
import wave
from types import SimpleNamespace

import numpy as np
import pytest

import speech


def wav(*, seconds=0.4, rate=16000, channels=1, silent=False):
    output = io.BytesIO()
    samples = (
        np.zeros(int(rate * seconds))
        if silent
        else np.sin(np.arange(int(rate * seconds)) * 0.1) * 4000
    )
    with wave.open(output, "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(samples.astype("<i2").tobytes())
    return output.getvalue()


@pytest.mark.parametrize(
    "audio",
    [
        b"",
        b"not wav",
        b"x" * 2000001,
        wav(seconds=0.1),
        wav(rate=8000),
        wav(channels=2),
        wav()[:-20],
    ],
)
def test_bad_recordings(audio):
    with pytest.raises(speech.TranscriptionError):
        speech.decode_recording(audio)


def test_silence():
    with pytest.raises(speech.UnclearSpeechError):
        speech.decode_recording(wav(silent=True))


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [SimpleNamespace(no_speech_prob=0.8, avg_logprob=0, text="noise")],
        [SimpleNamespace(no_speech_prob=0, avg_logprob=-2, text="unclear")],
    ],
)
def test_unclear_transcription(monkeypatch, segments):
    monkeypatch.setattr(
        speech,
        "get_model",
        lambda: SimpleNamespace(transcribe=lambda *a, **kw: (iter(segments), None)),
    )
    with pytest.raises(speech.UnclearSpeechError):
        speech.transcribe_audio(wav())


def test_lazy_service_failure(monkeypatch):
    def segments():
        raise RuntimeError("private text")
        yield

    monkeypatch.setattr(
        speech,
        "get_model",
        lambda: SimpleNamespace(transcribe=lambda *a, **kw: (segments(), None)),
    )
    with pytest.raises(speech.SpeechServiceError, match="Local transcription failed"):
        speech.transcribe_audio(wav())


def test_timeout_kills_child(monkeypatch):
    class Process:
        killed = False

        def communicate(self, audio, timeout):
            raise subprocess.TimeoutExpired("speech", timeout)

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self):
            pass

    process = Process()
    monkeypatch.setattr(speech.subprocess, "Popen", lambda *a, **kw: process)
    with pytest.raises(speech.SpeechServiceError):
        speech.transcribe(wav())
    assert process.killed
