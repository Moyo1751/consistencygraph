def clear_database(driver):
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

def store_character_age(name, age, chapter, driver):
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $name})
            MERGE (c)-[:HAS_AGE]->(a:AgeMention {age: $age, chapter: $chapter})
        """, name=name, age=age, chapter=chapter)

def store_character_location(name, location, chapter, paragraph, driver):
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $name})
            MERGE (l:Location {name: $location})
            MERGE (c)-[:IS_AT]->(p:Presence {chapter: $chapter})-[:LOCATION]->(l)
            SET p.paragraphs = CASE
                WHEN $paragraph IN coalesce(p.paragraphs, [])
                THEN p.paragraphs
                ELSE coalesce(p.paragraphs, []) + $paragraph
            END
        """, name=name, location=location, chapter=chapter, paragraph=paragraph)


def store_pairs(pairs, driver):
    for pair in pairs:
        store_character_location(
            pair["character"], pair["location"], pair["chapter"], pair["paragraph"], driver
        )

def store_organisation(name, driver):
    with driver.session() as session:
        session.run("""
            MERGE (o:Organisation {name: $name})
        """, name=name)

def store_membership(character, organisation, driver):
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $character})
            MERGE (o:Organisation {name: $organisation})
            MERGE (c)-[:MEMBER_OF]->(o)
        """, character=character, organisation=organisation)