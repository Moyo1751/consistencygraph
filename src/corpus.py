"""Loads the frozen corpus as numbered paragraphs."""

from pathlib import Path
from typing import NamedTuple
import json

# Anchored to this file's own location, not the working directory the
# process happens to be started from (same pattern as registry.py's
# REGISTRY_PATH, one directory up since corpus/ is a sibling of src/).
# Pinned to a frozen snapshot, never the working manuscript. Every run reported
# in the evaluation has to name the version it read. ch1-4_v2 is the held-out
# run. The development runs read ch1-2_v2 and ch1-2_v3, so both stay on disk
# untouched.
CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "corpus_ch1-4_v2.json"

# The corpus uses typographic (curly) punctuation throughout. Anchors in the
# gold standard and entries in registry.json use plain ASCII quotes, so
# comparing corpus text against either without normalising first fails
# silently (no exception, just a match that should have hit and didn't).
_PUNCTUATION_MAP = {
    "’": "'",  # RIGHT SINGLE QUOTATION MARK -> apostrophe
    "“": '"',  # LEFT DOUBLE QUOTATION MARK -> straight double quote
    "”": '"',  # RIGHT DOUBLE QUOTATION MARK -> straight double quote
}


def normalise(text: str) -> str:
    """Curly quotes to straight ones."""
    for typographic, ascii_equivalent in _PUNCTUATION_MAP.items():
        text = text.replace(typographic, ascii_equivalent)
    return text


class Paragraph(NamedTuple):
    chapter: int
    index: int
    text: str


def load_paragraphs() -> list[Paragraph]:
    """Every paragraph in reading order. Index 0 is the chapter heading, so it is skipped."""
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    paragraphs: list[Paragraph] = []
    for chapter in data["chapters"]:
        chapter_number = chapter["chapter"]
        for paragraph in chapter["paragraphs"]:
            if paragraph["index"] == 0:
                continue
            paragraphs.append(
                Paragraph(
                    chapter=chapter_number,
                    index=paragraph["index"],
                    text=paragraph["text"],
                )
            )
    return paragraphs
