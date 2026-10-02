"""Text to facts: registry injection, type resolution, character-location pairs and ages."""

import re

from spacy.matcher import PhraseMatcher
from spacy.util import filter_spans

from config import nlp
from registry import lookup, registry, SPACY_TO_SCHEMA

# CG-19. Matcher built once at import; tokenising the keys per paragraph would
# dominate runtime.
_REGISTRY_MATCHER = PhraseMatcher(nlp.vocab)
_REGISTRY_MATCHER.add("REGISTRY", list(nlp.tokenizer.pipe(registry.keys())))

REGISTRY_LABEL = "REGISTRY"


# Number words for parse_number and the age patterns.
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000}

# "and" joins number words but is never one itself. In the alternation it could
# stand alone, so "turned and started walking" matched the turned <N> pattern.
_NUM_WORDS = "|".join(list(_UNITS) + list(_TENS) + list(_SCALES))
_NUMBER = rf"(?:\d+|(?:{_NUM_WORDS})(?:[\s\-](?:and[\s\-])?(?:{_NUM_WORDS}))*)"

# CG-14. Four surface forms, nothing inferred. No birthdays, no date arithmetic.
_AGE_PATTERNS = [
    re.compile(rf"\b({_NUMBER})\s+years?\s+old\b", re.I),
    re.compile(rf"\baged\s+({_NUMBER})\b", re.I),
    re.compile(rf"\b({_NUMBER})[\s\-]year[\s\-]old\b", re.I),
    re.compile(rf"\bturned\s+({_NUMBER})\b", re.I),
]

def inject_registry_entities(doc):
    """Add registry keys spaCy missed to doc.ents.

    Rescues non-detections only. filter_spans keeps the longer span, so a key
    swallowed by a wider spaCy entity stays lost, and an exact duplicate keeps
    spaCy's own label.
    """
    injected = [
        doc[start:end]
        for _match_id, start, end in _REGISTRY_MATCHER(doc)
    ]
    injected = [
        doc.char_span(s.start_char, s.end_char, label=REGISTRY_LABEL)
        for s in injected
    ]
    injected = [s for s in injected if s is not None]

    doc.ents = filter_spans(list(doc.ents) + injected)
    return doc


def extract(text: str, chapter: int) -> list[dict[str, str | int]]:
    """Raw spaCy entities for one passage, before any resolution."""
    doc = nlp(text)

    # all labels kept on purpose; filter later so the RQ1 baseline stays honest
    result = [
        {
            "text": ent.text,
            "label": ent.label_,
            "chapter": chapter,
            "startChar": ent.start_char,
            "endChar": ent.end_char,
        }
        for ent in doc.ents
    ]

    return result


def pair_character_locations(doc, chapter, paragraph, resolved_map):
    """Every character paired with every location named in the same sentence.

    A journey (two places in one sentence) gives two pairs. Known limitation.
    """
    character_location_pairs = []

    for sent in doc.sents:
        characters = [ent.text for ent in sent.ents if resolved_map.get(ent.text) == "Character"]
        locations = [ent.text for ent in sent.ents if resolved_map.get(ent.text) == "Location"]

        if characters and locations:
            for character in characters:
                for location in locations:
                    character_location_pairs.append(
                        {
                            "character": character,
                            "location": location,
                            "chapter": chapter,
                            "paragraph": paragraph,
                        }
                    )

    return character_location_pairs


def resolve_entity_types(doc):
    """Registry type if the name is listed, otherwise the spaCy label mapping.

    The spaCy label is kept next to the resolved type so the audit can compare them.
    """
    resolved_entities = []
    for ent in doc.ents:
        text = ent.text
        label = ent.label_
        source = "registry" if label == REGISTRY_LABEL else "spacy"

        lookup_result = lookup(text)
        if lookup_result:
            resolved_type = lookup_result
        else:
            resolved_type = SPACY_TO_SCHEMA.get(label)

        resolved_entities.append(
            {"text": text, "label": label, "resolved_type": resolved_type, "source": source}
        )

    return resolved_entities


def parse_number(text):
    """Digits or a written English number to int. None if it isn't one."""
    text = text.lower().replace("-", " ")
    if text.strip().isdigit():
        return int(text.strip())

    total = current = 0
    seen = False
    for word in text.split():
        if word == "and":
            continue
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word in _SCALES:
            scale = _SCALES[word]
            if scale == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * scale
                current = 0
        else:
            return None
        seen = True

    return total + current if seen else None


def extract_ages(doc, chapter, resolved_map):
    """Ages bound to a character in the same sentence.

    Same binding rule as pair_character_locations, so both fail the same way.
    An age belonging to something other than a character ("a four-hundred-
    year-old oath") binds to whoever is named alongside it.
    """
    mentions = []

    for sent in doc.sents:
        characters = [ent.text for ent in sent.ents if resolved_map.get(ent.text) == "Character"]
        if not characters:
            continue

        for pattern in _AGE_PATTERNS:
            for match in pattern.finditer(sent.text):
                age = parse_number(match.group(1))
                if age is None:
                    continue
                for character in characters:
                    mentions.append(
                        {"character": character, "age": age, "chapter": chapter}
                    )

    return mentions
