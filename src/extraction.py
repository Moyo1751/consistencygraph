from spacy.matcher import PhraseMatcher
from spacy.util import filter_spans

from config import nlp
from registry import lookup, registry, SPACY_TO_SCHEMA

# CG-19. resolve_entity_types only consults the registry for spans spaCy already
# emitted, so keys it misses entirely never reach the pipeline. Matcher built once
# at import; tokenising the keys per paragraph would dominate runtime.
_REGISTRY_MATCHER = PhraseMatcher(nlp.vocab)
_REGISTRY_MATCHER.add("REGISTRY", list(nlp.tokenizer.pipe(registry.keys())))

# label carries provenance — survives doc.ents reassignment, unlike a Span extension
REGISTRY_LABEL = "REGISTRY"


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