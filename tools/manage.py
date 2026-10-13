"""Set up or launch local services; never stop services owned by another process."""

import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import local
from errors import ServiceError

CONFIG = ROOT / ".env.local.json"
KEYS = (
    "SPEAKWELL_JAVA",
    "SPEAKWELL_OLLAMA",
    "SPEAKWELL_LT_DIR",
    "SPEAKWELL_SPEECH_MODEL",
)


def load_paths():
    if CONFIG.exists():
        values = json.loads(CONFIG.read_text())
        if not isinstance(values, dict) or any(
            key not in KEYS or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise ValueError(
                "Invalid .env.local.json; expected supported executable/model paths."
            )
        for key, value in values.items():
            os.environ.setdefault(key, value)


def discover():
    java_home = os.environ.get("JAVA_HOME", "")
    java_candidates = [
        os.environ.get("SPEAKWELL_JAVA"),
        str(Path(java_home) / "bin/java") if java_home else None,
        str(ROOT / ".tools/java"),
        "/opt/homebrew/opt/openjdk@21/bin/java",
        "/usr/local/opt/openjdk@21/bin/java",
        shutil.which("java"),
    ]
    if not os.environ.get("SPEAKWELL_JAVA") and Path("/usr/libexec/java_home").exists():
        found = subprocess.run(
            ["/usr/libexec/java_home", "-v", "21"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if found.returncode == 0:
            java_candidates.insert(1, str(Path(found.stdout.strip()) / "bin/java"))
    if os.environ.get("SPEAKWELL_JAVA"):
        java_candidates = java_candidates[:1]
    for candidate in filter(None, java_candidates):
        if not Path(candidate).is_file():
            continue
        result = subprocess.run(
            [candidate, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and re.search(
            r'version "21(?:\.|\")', result.stdout + result.stderr
        ):
            os.environ["SPEAKWELL_JAVA"] = str(Path(candidate).resolve())
            break
    else:
        raise ValueError(
            "Java 21 not found. Set SPEAKWELL_JAVA to its bin/java executable."
        )
    ollama = os.environ.get("SPEAKWELL_OLLAMA") or shutil.which("ollama")
    if (
        not ollama
        and Path("/Applications/Ollama.app/Contents/Resources/ollama").is_file()
    ):
        ollama = "/Applications/Ollama.app/Contents/Resources/ollama"
    if not ollama or not Path(ollama).is_file() or not os.access(ollama, os.X_OK):
        raise ValueError("Ollama not found. Set SPEAKWELL_OLLAMA to its executable.")
    os.environ["SPEAKWELL_OLLAMA"] = str(Path(ollama).resolve())


def occupied(port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


async def check_service(name):
    if name == "ollama":
        tags = await local.request(local.OLLAMA + "/api/tags")
        if not isinstance(tags.get("models"), list):
            raise ValueError("Invalid Ollama response")
        return tags
    return await local.check("This is a local service check.")


def healthy(name):
    try:
        return asyncio.run(asyncio.wait_for(check_service(name), timeout=4))
    except (ServiceError, TimeoutError, ValueError, TypeError, KeyError):
        return None


def ensure_service(name, children):
    port = 11434 if name == "ollama" else 8081
    if occupied(port):
        if healthy(name) is None:
            raise ValueError(
                f"Port {port} is occupied but {name} is not healthy. Check the existing process; it was not stopped."
            )
        print(f"Reusing {name} on {port}.", flush=True)
        return
    log_dir = ROOT / ".tools/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    script = "ollama.sh" if name == "ollama" else "checker.sh"
    command = ["bash", str(ROOT / "tools" / script)]
    if name == "ollama":
        command.append("serve")
    with (log_dir / f"{name}.log").open("ab") as log:
        child = subprocess.Popen(
            command, cwd=ROOT, stdout=log, stderr=log, start_new_session=True
        )
    children.append(child)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if child.poll() is not None:
            break
        if healthy(name) is not None:
            print(f"Started {name} on {port}.", flush=True)
            return
        time.sleep(0.5)
    raise ValueError(f"Could not start {name}; inspect {log_dir / (name + '.log')}.")


def cleanup(children):
    for child in reversed(children):
        if child.poll() is not None:
            continue
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def models_ok():
    tags = healthy("ollama")
    return tags is not None and all(
        any(
            item.get("name") == name and item.get("digest") == digest
            for item in tags["models"]
        )
        for name, digest in local.MODELS.items()
    )


def run_step(command, children):
    child = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    children.append(child)
    result = child.wait()
    if result:
        raise subprocess.CalledProcessError(result, command)


def setup(children):
    for component in ("checker", "speech", "wordnet"):
        run_step([sys.executable, str(ROOT / "tools/setup.py"), component], children)
    ensure_service("ollama", children)
    if not models_ok():
        for name in local.MODELS:
            run_step(["bash", str(ROOT / "tools/ollama.sh"), "pull", name], children)
    if not models_ok():
        raise ValueError(
            "Downloaded model identities differ from the app's pinned models. Setup is incomplete."
        )
    ensure_service("checker", children)
    values = {key: os.environ[key] for key in KEYS if key in os.environ}
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(CONFIG)
    print("Setup verified. Local paths saved in .env.local.json (Git-ignored).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "launch"))
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    children = []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        load_paths()
        discover()
        if args.command == "setup":
            setup(children)
        else:
            from speech import MODEL_DIR, MODEL_FILES
            from vocabulary import DB_PATH as WORDNET_PATH

            if not WORDNET_PATH.is_file():
                raise ValueError(
                    "Wordnet is missing. Run: uv run --locked python tools/setup.py wordnet"
                )

            if not all((MODEL_DIR / name).is_file() for name in MODEL_FILES):
                raise ValueError(
                    "Whisper files are missing. Run the setup command first."
                )
            if occupied(args.port):
                raise ValueError(
                    f"App port {args.port} is occupied. Choose --port with a free port."
                )
            ensure_service("ollama", children)
            if not models_ok():
                raise ValueError(
                    "Required model identities do not match. Run setup first."
                )
            ensure_service("checker", children)
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(ROOT / "app.py"),
                    "--server.port",
                    str(args.port),
                ],
                cwd=ROOT,
                start_new_session=True,
            )
            children.append(child)
            return child.wait()
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, subprocess.SubprocessError, ServiceError) as exc:
        print(f"Setup/launch failed: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup(children)


if __name__ == "__main__":
    sys.exit(main())
