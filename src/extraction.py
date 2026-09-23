from spacy.matcher import PhraseMatcher
from spacy.util import filter_spans

from config import nlp
from registry import lookup, registry, SPACY_TO_SCHEMA

# CG-19. Registry injection.
#
# resolve_entity_types() only ever consulted the registry for spans spaCy had
# already emitted, so a registry key spaCy failed to DETECT was invisible to
# the whole pipeline no matter what the registry said about it. The 22 Sep
# audit put that at 77 ABSENT occurrences out of 244.
#
# The matcher is built once at import. Tokenising 103 keys on each of 148
# paragraphs would dominate runtime.
_REGISTRY_MATCHER = PhraseMatcher(nlp.vocab)
_REGISTRY_MATCHER.add("REGISTRY", list(nlp.tokenizer.pipe(registry.keys())))

# Provenance is carried by the LABEL, not by a custom Span extension. Entity
# labels are stored on the tokens and survive reassignment of doc.ents; span
# extension data is keyed on character offsets in doc.user_data and is easier
# to lose silently. Anything labelled REGISTRY was injected here.
REGISTRY_LABEL = "REGISTRY"


def inject_registry_entities(doc):
    """Add registry keys that spaCy failed to detect to doc.ents.

    Rescues ABSENT occurrences ONLY. Where spaCy already emitted a span that
    overlaps a key, filter_spans keeps the longer span, so CONTAINED and
    PARTIAL boundary errors are NOT fixed by this: "New Jersey" stays lost
    inside spaCy's "New Jersey Sightings" (ch1 p35).

    spaCy's own spans are listed first and filter_spans sorts stably, so an
    exact duplicate keeps spaCy's label and the baseline is never overwritten.

    Mutates doc.ents in place and returns doc.
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
    doc = nlp(text)

    # returns all labels intentionally — filter at consumer, keeping the RQ1 baseline honest
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