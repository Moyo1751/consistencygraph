from config import nlp, get_driver
from extraction import pair_character_locations, resolve_entity_types
from storage import store_pairs, clear_database


if __name__ == "__main__":
    # Setup Neo4j connection
    driver = get_driver()
    text = "King Reveth known to all as the Shadow Blade, lived in Thornhaven, a city of stone and steel."
    doc = nlp(text)
    print("Entities found: ", doc.ents)
    resolved = resolve_entity_types(doc)
    print("Resolved Entities: ", resolved)
    resolved_map = {ent["text"]: ent["resolved_type"] for ent in resolved}
    print("Resolved Map: ", resolved_map)
    pairs = pair_character_locations(doc, 1, resolved_map)
    print("Character-Location Pairs: ", pairs)
    clear_database(driver)  # Clear the database before storing new pairs
    store_pairs(pairs, driver)
    driver.close()