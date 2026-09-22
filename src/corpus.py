from pathlib import Path
from typing import NamedTuple
import json

# Anchored to this file's own location, not the working directory the
# process happens to be started from (same pattern as registry.py's
# REGISTRY_PATH, one directory up since corpus/ is a sibling of src/).
CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "corpus_ch1-2_v2.json"

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
    for typographic, ascii_equivalent in _PUNCTUATION_MAP.items():
        text = text.replace(typographic, ascii_equivalent)
    return text


class Paragraph(NamedTuple):
    chapter: int
    index: int
    text: str


def load_paragraphs() -> list[Paragraph]:
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
