import spacy
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

# Setup
nlp = spacy.load("en_core_web_sm")

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

def find_age_inconsistencies(driver):
    with driver.session() as session:
        result = session.run("""
            MATCH (c:Character)-[:HAS_AGE]->(a1:AgeMention)
            MATCH (c)-[:HAS_AGE]->(a2:AgeMention)
            WHERE a1.chapter < a2.chapter AND a1.age <> a2.age
            RETURN c.name AS character, 
                   a1.age AS age1, a1.chapter AS chapter1,
                   a2.age AS age2, a2.chapter AS chapter2
        """)
        
        issues = []
        for record in result:
            issues.append(record)
        return issues

def find_location_inconsistencies(driver):
    with driver.session() as session:
        result = session.run("""
            MATCH (c:Character)-[:IS_AT]->(p1:Presence)-[:LOCATION]->(l1:Location)
            MATCH (c)-[:IS_AT]->(p2:Presence)-[:LOCATION]->(l2:Location)
            WHERE p1.chapter = p2.chapter AND l1.name <> l2.name
            RETURN c.name AS character,
                   l1.name AS location1, l2.name AS location2,
                   p1.chapter AS chapter
        """)
        
        issues = []
        for record in result:
            issues.append(record)
        return issues


if __name__ == "__main__":
    #Setup Neo4j connection
    load_dotenv() 
    URI = os.environ["NEO4J_URI"]
    AUTH = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    driver = GraphDatabase.driver(URI, auth=AUTH)
    # === DEMO SCRIPT ===
    print("=" * 50)
    print("WORLD-BUILDING CONSISTENCY CHECKER - DEMO")
    print("=" * 50)

    clear_database(driver)

    # Simulate extracted facts from chapters (normally this comes from NLP)
    print("\n[Processing Chapter 1...]")
    print("  Found: Aldric is 27 years old")
    print("  Found: Aldric is in Thornhaven")
    store_character_age("Aldric", 27, 1, driver)
    store_character_location("Aldric", "Thornhaven", 1, driver)

    print("\n[Processing Chapter 2...]")
    print("  Found: Aldric is in Mount Kaelos")
    store_character_location("Aldric", "Mount Kaelos", 2, driver)

    print("\n[Processing Chapter 3...]")
    print("  Found: Aldric is 32 years old")  # INCONSISTENCY: only weeks have passed!
    print("  Found: Aldric is in Thornhaven")
    print("  Found: Aldric is in Mount Kaelos")  # INCONSISTENCY: two places same chapter!
    store_character_age("Aldric", 32, 3, driver)
    store_character_location("Aldric", "Thornhaven", 3, driver)
    store_character_location("Aldric", "Mount Kaelos", 3, driver)

    # Check for inconsistencies
    print("\n" + "=" * 50)
    print("CONSISTENCY CHECK RESULTS")
    print("=" * 50)

    age_issues = find_age_inconsistencies(driver)
    location_issues = find_location_inconsistencies(driver)

    if not age_issues and not location_issues:
        print("\n✓ No inconsistencies found!")
    else:
        if age_issues:
            print("\n⚠ AGE INCONSISTENCIES:")
            for issue in age_issues:
                print(f"  {issue['character']}: age {issue['age1']} in chapter {issue['chapter1']}, "
                    f"but age {issue['age2']} in chapter {issue['chapter2']}")
        
        if location_issues:
            print("\n⚠ LOCATION INCONSISTENCIES:")
            for issue in location_issues:
                print(f"  {issue['character']}: in both {issue['location1']} and {issue['location2']} "
                    f"during chapter {issue['chapter']}")

    driver.close()
    print("\n" + "=" * 50)