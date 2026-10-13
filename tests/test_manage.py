import json
from unittest.mock import Mock

import pytest

from tools import manage


def test_config_is_data_and_shell_overrides_saved_paths(tmp_path, monkeypatch):
    config = tmp_path / ".env.local.json"
    config.write_text(json.dumps({"SPEAKWELL_JAVA": "/saved/java"}))
    monkeypatch.setattr(manage, "CONFIG", config)
    monkeypatch.setenv("SPEAKWELL_JAVA", "/chosen/java")
    manage.load_paths()
    assert manage.os.environ["SPEAKWELL_JAVA"] == "/chosen/java"
    config.write_text(json.dumps({"PATH": "/untrusted"}))
    with pytest.raises(ValueError):
        manage.load_paths()


def test_reuses_service_without_owning_it(monkeypatch):
    monkeypatch.setattr(manage, "occupied", lambda port: True)
    monkeypatch.setattr(manage, "healthy", lambda name: {})
    spawn = Mock()
    monkeypatch.setattr(manage.subprocess, "Popen", spawn)
    children = []
    manage.ensure_service("checker", children)
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
        manage.ensure_service("checker", children)
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


def test_java_override_must_be_version_21(tmp_path, monkeypatch):
    java = tmp_path / "java"
    java.touch()
    monkeypatch.setenv("SPEAKWELL_JAVA", str(java))
    monkeypatch.setattr(
        manage.subprocess,
        "run",
        Mock(
            return_value=Mock(
                returncode=0, stdout="", stderr='openjdk version "18.0.2"'
            )
        ),
    )
    with pytest.raises(ValueError, match="Java 21"):
        manage.discover()


def test_failed_setup_step_remains_owned(monkeypatch):
    child = Mock()
    child.wait.return_value = 2
    monkeypatch.setattr(manage.subprocess, "Popen", Mock(return_value=child))
    children = []
    with pytest.raises(manage.subprocess.CalledProcessError):
        manage.run_step(["false"], children)
    assert children == [child]


def test_download_failure_does_not_promote_partial_archive(tmp_path, monkeypatch):
    from tools import setup

    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup.sys, "argv", ["setup.py", "checker"])
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        Mock(side_effect=manage.subprocess.CalledProcessError(22, "curl")),
    )
    with pytest.raises(manage.subprocess.CalledProcessError):
        setup.main()
    assert not (tmp_path / ".tools/LanguageTool-6.6.zip").exists()
