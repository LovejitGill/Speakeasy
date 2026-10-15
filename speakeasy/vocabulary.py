"""Offline dictionary meanings, never evidence that a sentence needs correction."""

import hashlib
import json
import re
import sqlite3
import subprocess
import zipfile
from contextlib import closing
from pathlib import Path

VERSION = "2025"
DB_PATH = Path(__file__).resolve().parents[1] / ".models/oewn-2025.sqlite3"
SOURCE = "https://en-word.net/downloads"


def lookup(word):
    if not re.fullmatch(r"[A-Za-z]+(?:[ '-][A-Za-z]+){0,3}", word) or len(word) > 60:
        return "Please ask about one short English word or expression."
    try:
        with closing(
            sqlite3.connect(
                DB_PATH.resolve().as_uri() + "?mode=ro", uri=True, timeout=1
            )
        ) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 2025:
                raise sqlite3.DatabaseError("Unsupported dictionary")
            rows = db.execute(
                "SELECT pos, definition, example FROM ("
                "SELECT pos, definition, example, rank, "
                "row_number() OVER (PARTITION BY pos ORDER BY rank) AS sense_order "
                "FROM meanings WHERE word = ?) ORDER BY sense_order, rank, pos LIMIT 4",
                (word.casefold(),),
            ).fetchall()
    except sqlite3.Error:
        return "The local dictionary is unavailable. Run the Wordnet setup command, then try again."
    if not rows:
        return f"I could not find ‘{word}’ in the local dictionary. That does not mean it is misspelled or not a name."
    labels = {
        "n": "noun",
        "v": "verb",
        "a": "adjective",
        "s": "adjective",
        "r": "adverb",
    }
    lines = [f"Possible meanings of ‘{word}’:"]
    for pos, definition, example in rows[:3]:
        lines.append(f"• {labels.get(pos, pos)}: {definition[:600]}")
        if example:
            lines.append(f"  Example: {example[:300]}")
    if len(rows) > 3:
        lines.append("There are more meanings; these are only a few.")
    lines.append(
        "Choose the meaning that fits your sentence. These are dictionary definitions, not a grammar check."
    )
    lines.append(f"Source: Open English Wordnet {VERSION}, CC BY 4.0 — {SOURCE}")
    return "\n".join(lines)


ARCHIVE_URL = "https://en-word.net/downloads/english-wordnet-2025-json.zip"
ARCHIVE_SHA256 = "7d749f6e2c39e6970e4997839dcf6e42fd281f3c2fae0171d2192bae8cfa4b51"


def build_dictionary(archive, destination):
    """Build a compact meanings index; replace the old database only on success."""
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError(
                "Wordnet checksum mismatch; remove its archive and rerun setup."
            )
    temporary = destination.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with (
            closing(sqlite3.connect(temporary)) as db,
            zipfile.ZipFile(archive) as bundle,
        ):
            if sum(item.file_size for item in bundle.infolist()) > 250_000_000:
                raise ValueError("Wordnet archive exceeds the expected size.")
            db.execute(
                "CREATE TABLE meanings (word TEXT, pos TEXT, definition TEXT, example TEXT, rank INTEGER)"
            )
            synsets = {}
            for item in bundle.infolist():
                if item.filename.endswith(".json") and not item.filename.startswith(
                    "entries-"
                ):
                    synsets.update(json.loads(bundle.read(item)))
            count = 0
            for item in bundle.infolist():
                if not item.filename.startswith(
                    "entries-"
                ) or not item.filename.endswith(".json"):
                    continue
                for word, parts in json.loads(bundle.read(item)).items():
                    for entry in parts.values():
                        for rank, reference in enumerate(entry["sense"]):
                            sense = synsets[reference["synset"]]
                            # Synset examples can use a synonym; show only this word's examples.
                            examples = [
                                e if isinstance(e, str) else e["text"]
                                for e in sense.get("example", [])
                            ]
                            example = next(
                                (
                                    e
                                    for e in examples
                                    if re.search(
                                        r"(?<!\w)" + re.escape(word) + r"(?!\w)",
                                        e,
                                        re.IGNORECASE,
                                    )
                                ),
                                "",
                            )
                            db.execute(
                                "INSERT INTO meanings VALUES (?, ?, ?, ?, ?)",
                                (
                                    word.casefold(),
                                    sense["partOfSpeech"],
                                    sense["definition"][0],
                                    example,
                                    rank,
                                ),
                            )
                            count += 1
            if not count:
                raise ValueError("Wordnet contains no meanings.")
            db.execute("CREATE INDEX words ON meanings(word, rank)")
            db.execute("PRAGMA user_version = 2025")
            db.commit()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def install():
    folder = DB_PATH.parent
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / "english-wordnet-2025-json.zip"
    if not archive.exists():
        partial = archive.with_suffix(".part")
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--connect-timeout",
                "15",
                "--max-time",
                "600",
                ARCHIVE_URL,
                "--output",
                str(partial),
            ],
            check=True,
        )
        partial.replace(archive)
    build_dictionary(archive, DB_PATH)
    print("Open English Wordnet 2025 verified and indexed (CC BY 4.0).")
