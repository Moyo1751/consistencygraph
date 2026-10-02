"""Runs the corpus through extraction and storage, then both detection queries.

Clears the database first, so every run starts from an empty graph.
"""

from config import nlp, get_driver
from extraction import inject_registry_entities, pair_character_locations, resolve_entity_types
from storage import store_pairs, clear_database
from detection import find_age_inconsistencies, find_location_inconsistencies
from corpus import load_paragraphs, normalise
from extraction import extract_ages, inject_registry_entities, pair_character_locations, resolve_entity_types
from storage import clear_database, store_ages, store_pairs


if __name__ == "__main__":
    # Setup Neo4j connection
    driver = get_driver()
    clear_database(driver)
    pair_count = 0
    age_count = 0
    paragraphs = load_paragraphs()
    
    for para in paragraphs:
        text = normalise(para.text)
        doc = nlp(text)
        inject_registry_entities(doc)  # add registry names spaCy missed
        resolved = resolve_entity_types(doc)
        resolved_map = {ent["text"]: ent["resolved_type"] for ent in resolved}
        # same-sentence binding for both locations and ages
        pairs = pair_character_locations(doc, para.chapter, para.index, resolved_map)
        pair_count += len(pairs)
        store_pairs(pairs, driver)
        ages = extract_ages(doc, para.chapter, resolved_map)
        age_count += len(ages)
        store_ages(ages, driver)
        

    print(f"Processed {len(paragraphs)} paragraphs, stored {pair_count} pairs and {age_count} ages")
    age_issues = find_age_inconsistencies(driver)
    print("Age Inconsistencies: ", age_issues)
    location_issues = find_location_inconsistencies(driver)
    print("Location Inconsistencies: ", location_issues)
    driver.close()
