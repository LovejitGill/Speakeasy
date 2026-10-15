import json
from unittest.mock import Mock

import pytest

from tools import manage


def test_config_is_data_and_shell_overrides_saved_paths(tmp_path, monkeypatch):
    config = tmp_path / ".env.local.json"
    config.write_text(json.dumps({"SPEAKWELL_OLLAMA": "/saved/ollama"}))
    monkeypatch.setattr(manage, "CONFIG", config)
    monkeypatch.setenv("SPEAKWELL_OLLAMA", "/chosen/ollama")
    manage.load_paths()
    assert manage.os.environ["SPEAKWELL_OLLAMA"] == "/chosen/ollama"
    config.write_text(
        json.dumps({"SPEAKWELL_JAVA": "/old/java", "SPEAKWELL_LT_DIR": "/old/checker"})
    )
    manage.load_paths()
    assert "SPEAKWELL_JAVA" not in manage.os.environ
    config.write_text(json.dumps({"PATH": "/untrusted"}))
    with pytest.raises(ValueError):
        manage.load_paths()


def test_reuses_service_without_owning_it(monkeypatch):
    monkeypatch.setattr(manage, "occupied", lambda port: True)
    monkeypatch.setattr(manage, "healthy", lambda name: {})
    spawn = Mock()
    monkeypatch.setattr(manage.subprocess, "Popen", spawn)
    children = []
    manage.ensure_service("ollama", children)
    assert children == []
    spawn.assert_not_called()


def test_foreign_port_is_not_replaced(monkeypatch):
    monkeypatch.setattr(manage, "occupied", lambda port: True)
    monkeypatch.setattr(manage, "healthy", lambda name: None)
    with pytest.raises(ValueError, match="occupied"):
        manage.ensure_service("ollama", [])


def test_failed_start_is_tracked_for_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "ROOT", tmp_path)
    monkeypatch.setattr(manage, "occupied", lambda port: False)
    child = Mock()
    child.poll.return_value = 1
    monkeypatch.setattr(manage.subprocess, "Popen", Mock(return_value=child))
    children = []
    with pytest.raises(ValueError, match="Could not start"):
        manage.ensure_service("ollama", children)
    assert children == [child]


def test_cleanup_only_signals_live_owned_processes(monkeypatch):
    alive, exited = Mock(pid=111), Mock(pid=222)
    alive.poll.return_value = None
    exited.poll.return_value = 0
    kill = Mock()
    monkeypatch.setattr(manage.os, "killpg", kill)
    manage.cleanup([alive, exited])
    kill.assert_called_once_with(111, manage.signal.SIGTERM)
    alive.wait.assert_called_once_with(timeout=10)
    exited.wait.assert_not_called()


def test_model_digest_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(
        manage,
        "healthy",
        lambda name: {
            "models": [
                {"name": name, "digest": "wrong"} for name in manage.local.MODELS
            ]
        },
    )
    assert not manage.models_ok()


def test_only_conversation_model_is_required(monkeypatch):
    monkeypatch.setattr(
        manage,
        "healthy",
        lambda name: {
            "models": [
                {"name": "qwen3:1.7b", "digest": manage.local.MODELS["qwen3:1.7b"]}
            ]
        },
    )
    assert manage.models_ok()


def test_failed_setup_step_remains_owned(monkeypatch):
    child = Mock()
    child.wait.return_value = 2
    monkeypatch.setattr(manage.subprocess, "Popen", Mock(return_value=child))
    children = []
    with pytest.raises(manage.subprocess.CalledProcessError):
        manage.run_step(["false"], children)
    assert children == [child]


def test_setup_includes_explicit_grammar_model_download(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "CONFIG", tmp_path / ".env.local.json")
    monkeypatch.setenv("SPEAKWELL_OLLAMA", "/missing/ollama")
    import huggingface_hub

    import local
    from tools import setup

    download = Mock()
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    monkeypatch.setattr(setup.sys, "argv", ["setup.py", "grammar"])
    setup.main()
    download.assert_called_once_with(
        local.GRAMMAR_MODEL_ID,
        revision=local.GRAMMAR_MODEL_REVISION,
        local_dir=local.GRAMMAR_MODEL_DIR,
        allow_patterns=list(local.GRAMMAR_MODEL_FILES),
    )
    steps = Mock()
    monkeypatch.setattr(manage, "run_step", steps)
    service = Mock(side_effect=AssertionError("Grammar setup must not start Ollama"))
    monkeypatch.setattr(manage, "ensure_service", service)
    manage.setup([])
    assert [call.args[0][-1] for call in steps.call_args_list] == [
        "speech",
        "grammar",
        "wordnet",
    ]
    service.assert_not_called()
    assert "SPEAKWELL_OLLAMA" not in json.loads(manage.CONFIG.read_text())


def test_optional_conversation_setup_pulls_only_used_model(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "CONFIG", tmp_path / ".env.local.json")
    steps = Mock()
    monkeypatch.setattr(manage, "run_step", steps)
    monkeypatch.setattr(manage, "discover", Mock())
    monkeypatch.setattr(manage, "ensure_service", Mock())
    checks = iter((False, True))
    monkeypatch.setattr(manage, "models_ok", lambda: next(checks))
    manage.setup([], with_ollama=True)
    assert steps.call_args_list[-1].args[0][-2:] == ["pull", "qwen3:1.7b"]
    manage.ensure_service.assert_called_once_with("ollama", [])


def test_discover_only_requires_executable_ollama(tmp_path, monkeypatch):
    executable = tmp_path / "ollama"
    executable.touch()
    monkeypatch.setenv("SPEAKWELL_OLLAMA", str(executable))
    with pytest.raises(ValueError, match="Ollama not found"):
        manage.discover()
    executable.chmod(0o700)
    manage.discover()
    assert manage.os.environ["SPEAKWELL_OLLAMA"] == str(executable.resolve())


@pytest.mark.parametrize("with_ollama", [False, True])
def test_launch_starts_app_with_optional_conversation_service(
    tmp_path, monkeypatch, with_ollama
):
    import speech
    import vocabulary

    args = ["manage.py", "launch"] + (["--with-ollama"] if with_ollama else [])
    monkeypatch.setattr(manage.sys, "argv", args)
    monkeypatch.setattr(manage, "load_paths", Mock())
    monkeypatch.setattr(manage, "discover", Mock())
    monkeypatch.setattr(manage.signal, "signal", Mock())
    monkeypatch.setattr(manage, "occupied", lambda port: False)
    monkeypatch.setattr(manage, "models_ok", lambda: True)
    service = Mock()
    monkeypatch.setattr(manage, "ensure_service", service)
    monkeypatch.setattr(manage, "cleanup", Mock())
    monkeypatch.setattr(speech, "MODEL_DIR", tmp_path)
    for name in speech.MODEL_FILES:
        (tmp_path / name).touch()
    dictionary = tmp_path / "wordnet.sqlite3"
    dictionary.touch()
    monkeypatch.setattr(vocabulary, "DB_PATH", dictionary)
    child = Mock()
    child.wait.return_value = 0
    spawn = Mock(return_value=child)
    monkeypatch.setattr(manage.subprocess, "Popen", spawn)
    assert manage.main() == 0
    assert [call.args[0] for call in service.call_args_list] == (
        ["ollama"] if with_ollama else []
    )
    assert spawn.call_args.args[0][1:4] == ["-m", "streamlit", "run"]
