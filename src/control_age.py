"""CG-14 positive control.

Chapters 1 and 2 contain no age mentions, so a corpus run proves nothing about
the age path. These passages are the only evidence it works.
"""

from config import get_driver, nlp
from detection import find_age_inconsistencies
from extraction import extract_ages, inject_registry_entities, resolve_entity_types
from storage import clear_database, store_ages

CONFLICTING = [
    (1, "Roisen was four hundred years old when she took the seat."),
    (2, "By then Roisen was three hundred years old, or so Alric claimed."),
]

CONSISTENT = [
    (1, "Roisen was four hundred years old when she took the seat."),
    (2, "By then Roisen was four hundred years old, or so Alric claimed."),
]


def run(passages, driver):
    clear_database(driver)
    stored = 0
    for chapter, text in passages:
        doc = nlp(text)
        inject_registry_entities(doc)
        resolved_map = {e["text"]: e["resolved_type"] for e in resolve_entity_types(doc)}
        ages = extract_ages(doc, chapter, resolved_map)
        stored += len(ages)
        store_ages(ages, driver)
    return stored, find_age_inconsistencies(driver)


if __name__ == "__main__":
    driver = get_driver()

    stored, issues = run(CONFLICTING, driver)
    print(f"positive: {stored} ages stored, {len(issues)} inconsistencies (expect 1)")
    for row in issues:
        print("   ", dict(row))

    stored, issues = run(CONSISTENT, driver)
    print(f"negative: {stored} ages stored, {len(issues)} inconsistencies (expect 0)")

    driver.close()