"""Explicit model/checker downloads. Normal app operation never downloads weights."""

import argparse
import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["speech", "checker", "wordnet"])
    args = parser.parse_args()
    if args.component == "wordnet":
        from vocabulary import install

        install()
    elif args.component == "speech":
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
            # curl handles the official download on Macs where urllib receives 403.
            partial = archive.with_suffix(".part")
            subprocess.run(
                [
                    "curl",
                    "--fail",
                    "--location",
                    "--retry",
                    "2",
                    "--connect-timeout",
                    "15",
                    "--max-time",
                    "300",
                    "https://languagetool.org/download/LanguageTool-6.6.zip",
                    "--output",
                    str(partial),
                ],
                check=True,
            )
            partial.replace(archive)
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
