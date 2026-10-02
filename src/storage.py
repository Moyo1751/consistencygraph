"""Graph writes. Each function takes the driver rather than making its own."""


def clear_database(driver):
    """Deletes every node and relationship."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

def store_character_age(name, age, chapter, driver):
    """One AgeMention per character, age and chapter. A second age is a new node."""
    with driver.session() as session:
        session.run("""
            MERGE (c:Character {name: $name})
            MERGE (c)-[:HAS_AGE]->(a:AgeMention {age: $age, chapter: $chapter})
        """, name=name, age=age, chapter=chapter)

def store_ages(mentions, driver):
    """Writes the output of extract_ages."""
    for mention in mentions:
        store_character_age(
            mention["character"], mention["age"], mention["chapter"], driver
        )

def store_character_location(name, location, chapter, paragraph, driver):
    """One Presence per character, chapter and location; the paragraph is added to its list.

    MERGE on the whole path. MERGE on chapter alone would give every character
    in the chapter the same Presence.
    """
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
    """Writes the output of pair_character_locations."""
    for pair in pairs:
        store_character_location(
            pair["character"], pair["location"], pair["chapter"], pair["paragraph"], driver
        )

# Organisations: written but not yet called by the pipeline.
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
