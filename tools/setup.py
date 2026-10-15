"""Explicit model downloads. Normal app operation never downloads weights."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["speech", "grammar", "wordnet"])
    args = parser.parse_args()
    if args.component == "wordnet":
        from speakeasy.vocabulary import install

        install()
    elif args.component in {"speech", "grammar"}:
        if args.component == "speech":
            from speakeasy.speech import (
                MODEL_DIR,
                MODEL_FILES,
                MODEL_ID,
                MODEL_REVISION,
            )
        else:
            from speakeasy.local import GRAMMAR_MODEL_DIR as MODEL_DIR
            from speakeasy.local import GRAMMAR_MODEL_FILES as MODEL_FILES
            from speakeasy.local import GRAMMAR_MODEL_ID as MODEL_ID
            from speakeasy.local import GRAMMAR_MODEL_REVISION as MODEL_REVISION

        os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from huggingface_hub import snapshot_download

        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=MODEL_DIR,
            allow_patterns=list(MODEL_FILES),
        )
        print(
            "Pinned Whisper base.en files downloaded."
            if args.component == "speech"
            else "Pinned T5 grammar model files downloaded."
        )


if __name__ == "__main__":
    main()
