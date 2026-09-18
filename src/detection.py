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
            WHERE p1.chapter = p2.chapter AND l1.name < l2.name
            RETURN c.name AS character,
                   l1.name AS location1, l2.name AS location2,
                   p1.chapter AS chapter
        """)
        
        issues = []
        for record in result:
            issues.append(record)
        return issues