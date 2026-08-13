from extract import pair_character_locations, extract
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

def resolve_entity_types(entities):
    resolved_entities = []
    for entity in entities:
        text = entity["text"]
        label = entity["label"]
        lookup_result = lookup(text)
        if lookup_result:
            resolved_entities.append({"text": text, "label": label, "resolved_type": lookup_result})
        else:
            resolved_entities.append({"text": text, "label": label, "resolved_type": SPACY_TO_SCHEMA.get(label)})

    return resolved_entities





if __name__ == "__main__":
    # Testing the store_pairs function with dummy data
    # clear_database()  # Clear the database before storing new data
    # dummy_text = "Aldric Stormborn had not seen the walls of Thornton in fifteen years. The last time he had passed through these gates, he was a boy of twelve, fleeing the coup that killed his father, King Aldric the Elder."
    # dummy_pairs = pair_character_locations(dummy_text, 1)
    # print("Storing the following character-location pairs:")
    # store_pairs(dummy_pairs)
    # final_issues = find_location_inconsistencies()
    # if final_issues:
    #     print("Inconsistencies found after storing pairs:")
    #     for issue in final_issues:
    #         print(f"  {issue['character']}: in both {issue['location1']} and {issue['location2']} during chapter {issue['chapter']}")

    # lookup_name = "Elo"
    # lookup_location = "Seattle"
    # print(f"Looking up this name {lookup_name} and this location {lookup_location} in the registry...")
    # result_one = lookup(lookup_name)
    # result_two = lookup(lookup_location)
    # if result_one:
    #     print(f"Found {lookup_name} in the registry as a {result_one}.")
    # else:
    #     print(f"{lookup_name} not found in the registry.")

    # if result_two:
    #     print(f"Found {lookup_location} in the registry as a {result_two}.")
    # else:
    #     print(f"{lookup_location} not found in the registry.")

    # print(f"Raw registry results: {result_one}, {result_two}")
    # print("Finished testing the lookup function.")

    entities = extract("Elior Kerenath had not seen the walls of Thornhaven in fifteen years. The last time he had passed through these gates, he was a boy of twelve, fleeing the coup that killed his father, King Reveth the Shadow Blade.", 1)

    resolved_entities = resolve_entity_types(entities)

    print("Resolved Entities:")
    for entity in resolved_entities:
        print(f"  {entity['text']} -> {entity['label']} (resolved type: {entity['resolved_type']})")
