"""Explicit model/checker downloads. Normal app operation never downloads weights."""

import argparse
import hashlib
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["speech", "checker"])
    args = parser.parse_args()
    if args.component == "speech":
        from speech import MODEL_DIR, MODEL_FILES, MODEL_ID, MODEL_REVISION

        os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from huggingface_hub import snapshot_download

        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=MODEL_DIR,
            allow_patterns=list(MODEL_FILES),
        )
        print("Pinned Whisper base.en files downloaded.")
    else:
        folder = ROOT / ".tools"
        folder.mkdir(exist_ok=True)
        archive = folder / "LanguageTool-6.6.zip"
        if not archive.exists():
            with (
                urllib.request.urlopen(
                    "https://languagetool.org/download/LanguageTool-6.6.zip", timeout=60
                ) as response,
                archive.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != "53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631":
            raise SystemExit(
                "Checksum mismatch. Remove the incomplete checker archive and retry."
            )
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if (
                    not (folder / member.filename)
                    .resolve()
                    .is_relative_to(folder.resolve())
                ):
                    raise SystemExit("Unsafe archive path.")
            bundle.extractall(folder)
        print("LanguageTool 6.6 verified and extracted. Java 21 is required.")


if __name__ == "__main__":
    main()
