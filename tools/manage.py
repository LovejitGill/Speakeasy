"""Set up or launch local services; never stop services owned by another process."""

import argparse
import asyncio
import json
import os
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
    "SPEAKWELL_OLLAMA",
    "SPEAKWELL_SPEECH_MODEL",
)
OLD_KEYS = ("SPEAKWELL_JAVA", "SPEAKWELL_LT_DIR")


def load_paths():
    if CONFIG.exists():
        values = json.loads(CONFIG.read_text())
        if not isinstance(values, dict) or any(
            key not in (*KEYS, *OLD_KEYS) or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise ValueError(
                "Invalid .env.local.json; expected supported executable/model paths."
            )
        for key in KEYS:
            if key in values:
                os.environ.setdefault(key, values[key])


def discover():
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
    raise ValueError("Unsupported service")


def healthy(name):
    try:
        return asyncio.run(asyncio.wait_for(check_service(name), timeout=4))
    except (ServiceError, TimeoutError, ValueError, TypeError, KeyError):
        return None


def ensure_service(name, children):
    if name != "ollama":
        raise ValueError("Unsupported service")
    port = 11434
    if occupied(port):
        if healthy(name) is None:
            raise ValueError(
                f"Port {port} is occupied but {name} is not healthy. Check the existing process; it was not stopped."
            )
        print(f"Reusing {name} on {port}.", flush=True)
        return
    log_dir = ROOT / ".tools/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command = ["bash", str(ROOT / "tools/ollama.sh"), "serve"]
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
    return tags is not None and any(
        item.get("name") == "qwen3:1.7b"
        and item.get("digest") == local.MODELS["qwen3:1.7b"]
        for item in tags["models"]
    )


def run_step(command, children):
    child = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    children.append(child)
    result = child.wait()
    if result:
        raise subprocess.CalledProcessError(result, command)


def setup(children, *, with_ollama=False):
    for component in ("speech", "grammar", "wordnet"):
        run_step([sys.executable, str(ROOT / "tools/setup.py"), component], children)
    if with_ollama:
        discover()
        ensure_service("ollama", children)
        if not models_ok():
            run_step(
                ["bash", str(ROOT / "tools/ollama.sh"), "pull", "qwen3:1.7b"], children
            )
        if not models_ok():
            raise ValueError(
                "Downloaded conversation model identity differs from the pinned model. Setup is incomplete."
            )
    values = {
        key: os.environ[key]
        for key in KEYS
        if key in os.environ and (with_ollama or key != "SPEAKWELL_OLLAMA")
    }
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(CONFIG)
    print("Setup verified. Local paths saved in .env.local.json (Git-ignored).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "launch"))
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument(
        "--with-ollama",
        action="store_true",
        help="manage the optional Qwen conversation model",
    )
    args = parser.parse_args()
    children = []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")
        load_paths()
        if args.command == "setup":
            setup(children, with_ollama=args.with_ollama)
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
            if args.with_ollama:
                discover()
                ensure_service("ollama", children)
                if not models_ok():
                    raise ValueError(
                        "Conversation model identity does not match. Run setup --with-ollama first."
                    )
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
