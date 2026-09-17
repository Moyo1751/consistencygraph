from config import nlp
from registry import lookup, SPACY_TO_SCHEMA

def extract(text: str, chapter: int) -> list[dict[str, str | int]]: 
    doc = nlp(text)
    
    # returns all labels intentionally — filter at consumer, keeping the RQ1 baseline honest
    result = [{"text": ent.text, "label": ent.label_, "chapter": chapter, "startChar": ent.start_char, "endChar": ent.end_char} for ent in doc.ents]

    return result

def pair_character_locations(doc, chapter, resolved_map): 
    character_location_pairs = []

    for sent in doc.sents: 
        characters = []
        locations = []
        characters = [ent.text for ent in sent.ents if resolved_map.get(ent.text) == "Character"]
        locations = [ent.text for ent in sent.ents if resolved_map.get(ent.text) == "Location"]

        if characters and locations:
             for character in characters:
                  for location in locations: 
                        character_location_pairs.append({"character": character, "location": location, "chapter": chapter})

    return character_location_pairs


def resolve_entity_types(doc):
    resolved_entities = []
    for ent in doc.ents:
        text = ent.text
        label = ent.label_
        lookup_result = lookup(text)
        if lookup_result:
            resolved_entities.append({"text": text, "label": label, "resolved_type": lookup_result})
        else:
            resolved_entities.append({"text": text, "label": label, "resolved_type": SPACY_TO_SCHEMA.get(label)})

    return resolved_entities