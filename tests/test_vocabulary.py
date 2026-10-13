import hashlib
import json
import sqlite3
import zipfile

import pytest

import conversation
import vocabulary


@pytest.fixture
def dictionary(tmp_path, monkeypatch):
    archive = tmp_path / "words.zip"
    data = {
        str(i): {
            "members": ["bank"],
            "partOfSpeech": "n",
            "definition": [f"Meaning {i}"],
            "example": ["An example."],
        }
        for i in range(5)
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("noun.json", json.dumps(data))
        bundle.writestr(
            "entries-b.json",
            json.dumps(
                {"bank": {"n": {"sense": [{"synset": str(i)} for i in range(5)]}}}
            ),
        )
    monkeypatch.setattr(
        vocabulary, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(vocabulary, "DB_PATH", tmp_path / "words.sqlite3")
    vocabulary.build_dictionary(archive, vocabulary.DB_PATH)
    return archive


def test_dictionary_multiple_meanings_are_bounded_and_attributed(dictionary):
    answer = vocabulary.lookup("Bank")
    assert "Meaning 0" in answer and "Meaning 2" in answer
    assert "Meaning 3" not in answer
    assert "more meanings" in answer
    assert "CC BY 4.0" in answer
    assert "not a grammar check" in answer


def test_unknown_word_is_not_called_a_misspelling(dictionary):
    assert "does not mean it is misspelled" in vocabulary.lookup("Lovejit")


@pytest.mark.parametrize(
    "query", ["What does bank mean?", "Define bank.", "What is the meaning of bank?"]
)
def test_dictionary_conversation_route(dictionary, query):
    answer, choices, route = conversation.plan(
        query, [], "beginner", "daily activities"
    )
    assert "Meaning 0" in answer
    assert choices == [] and route == "reference"


def test_dictionary_controls_and_existing_pair_explanation(dictionary):
    assert conversation.plan("stop", [], "beginner", "daily activities")[2] == "stop"
    answer = conversation.reference(
        "What does bank mean? No follow-up questions.", [], "daily activities"
    )
    assert "Meaning 0" in answer
    assert "Lend means" in conversation.reference(
        "Compare lend and borrow", [], "daily activities"
    )
    assert conversation.reference("I work at a bank.", [], "daily activities") is None


def test_missing_dictionary_never_creates_or_downloads(tmp_path, monkeypatch):
    path = tmp_path / "missing.sqlite3"
    monkeypatch.setattr(vocabulary, "DB_PATH", path)
    assert "unavailable" in vocabulary.lookup("bank")
    assert not path.exists()


def test_corrupt_dictionary_is_safe(tmp_path, monkeypatch):
    path = tmp_path / "bad.sqlite3"
    path.write_text("bad")
    monkeypatch.setattr(vocabulary, "DB_PATH", path)
    assert "unavailable" in vocabulary.lookup("bank")


def test_checksum_failure_preserves_previous_dictionary(dictionary):
    original = vocabulary.DB_PATH.read_bytes()
    dictionary.write_bytes(b"bad archive")
    with pytest.raises(ValueError, match="checksum"):
        vocabulary.build_dictionary(dictionary, vocabulary.DB_PATH)
    assert vocabulary.DB_PATH.read_bytes() == original


def test_bad_archive_schema_rolls_back(dictionary, monkeypatch):
    original = vocabulary.DB_PATH.read_bytes()
    with zipfile.ZipFile(dictionary, "w") as bundle:
        bundle.writestr("bad.json", "{}")
    monkeypatch.setattr(
        vocabulary,
        "ARCHIVE_SHA256",
        hashlib.sha256(dictionary.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="no meanings"):
        vocabulary.build_dictionary(dictionary, vocabulary.DB_PATH)
    assert vocabulary.DB_PATH.read_bytes() == original
    assert not vocabulary.DB_PATH.with_suffix(".tmp").exists()


def test_lookup_rejects_injection(dictionary):
    assert "Please ask" in vocabulary.lookup("bank'; DROP TABLE meanings;--")
    with sqlite3.connect(vocabulary.DB_PATH) as db:
        assert db.execute("SELECT count(*) FROM meanings").fetchone()[0] == 5


def test_lookup_includes_different_parts_of_speech(dictionary):
    with sqlite3.connect(vocabulary.DB_PATH) as db:
        db.execute(
            "INSERT INTO meanings VALUES ('bank', 'v', 'A verb meaning', '', 100)"
        )
    assert "verb: A verb meaning" in vocabulary.lookup("bank")
