def clear_database(driver):
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

def store_character_age(name, age, chapter, driver):
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $name})
            CREATE (a:AgeMention {age: $age, chapter: $chapter})
            CREATE (c)-[:HAS_AGE]->(a)
        """, name=name, age=age, chapter=chapter)

def store_character_location(name, location, chapter, driver):
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $name})
            MERGE (l:Location {name: $location})
            CREATE (p:Presence {chapter: $chapter})
            CREATE (c)-[:IS_AT]->(p)
            CREATE (p)-[:LOCATION]->(l)
        """, name=name, location=location, chapter=chapter)

def store_pairs(pairs, driver):
    for pair in pairs:
        name = pair["character"]
        location = pair["location"]
        chapter = pair["chapter"]
        store_character_location(name, location, chapter, driver)
        print(f"Stored: {name} at {location} in chapter {chapter}")