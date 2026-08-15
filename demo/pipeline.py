from extract import pair_character_locations, extract, nlp
from demo import store_character_location, clear_database, find_location_inconsistencies

import json

with open("registry.json") as f:
    registry = json.load(f)

def store_pairs(pairs):
    for pair in pairs:
        name = pair["character"]
        location = pair["location"]
        chapter = pair["chapter"]
        store_character_location(name, location, chapter)
        print(f"Stored: {name} at {location} in chapter {chapter}")

def lookup(name: str) -> str | None:
    return registry.get(name)

SPACY_TO_SCHEMA = {
    "PERSON": "Character",
    "GPE": "Location",
}

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





if __name__ == "__main__":
    text = "King Reveth known to all as the Shadow Blade, lived in Thornhaven, a city of stone and steel."
    doc = nlp(text)
    print("Entities found: ", doc.ents)
    resolved = resolve_entity_types(doc)
    print("Resolved Entities: ", resolved)
    resolved_map = {ent["text"]: ent["resolved_type"] for ent in resolved}
    print("Resolved Map: ", resolved_map)
    pairs = pair_character_locations(doc, 1, resolved_map)
    print("Character-Location Pairs: ", pairs)
    clear_database()  # Clear the database before storing new pairs
    store_pairs(pairs)