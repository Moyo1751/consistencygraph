from extract import pair_character_locations
from demo import store_character_location, clear_database, find_location_inconsistencies

def store_pairs(pairs):
    for pair in pairs:
        name = pair["character"]
        location = pair["location"]
        chapter = pair["chapter"]
        store_character_location(name, location, chapter)
        print(f"Stored: {name} at {location} in chapter {chapter}")



if __name__ == "__main__":
    # Testing the store_pairs function with dummy data
    clear_database()  # Clear the database before storing new data
    dummy_text = "Aldric Stormborn had not seen the walls of Thornton in fifteen years. The last time he had passed through these gates, he was a boy of twelve, fleeing the coup that killed his father, King Aldric the Elder."
    dummy_pairs = pair_character_locations(dummy_text, 1)
    print("Storing the following character-location pairs:")
    store_pairs(dummy_pairs)
    final_issues = find_location_inconsistencies()
    if final_issues:
        print("Inconsistencies found after storing pairs:")
        for issue in final_issues:
            print(f"  {issue['character']}: in both {issue['location1']} and {issue['location2']} during chapter {issue['chapter']}")

