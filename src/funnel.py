from collections import Counter

from config import nlp
from corpus import load_paragraphs, normalise
from extraction import (
    inject_registry_entities,
    pair_character_locations,
    resolve_entity_types,
)


def new_counts():
    return {
        "entities": 0,
        "sentences": 0,
        "with_character": 0,
        "with_location": 0,
        "with_both": 0,
        "resolved": Counter(),
        "location_names": Counter(),
        "character_names": Counter(),
        "pairs": [],
    }


def count_into(counts, doc, para):
    # resolved_map is keyed on entity text, so it has to be rebuilt after
    # injection or the after column counts against a stale entity set.
    resolved = resolve_entity_types(doc)
    resolved_map = {ent["text"]: ent["resolved_type"] for ent in resolved}

    counts["entities"] += len(doc.ents)

    for entry in resolved:
        resolved_type = entry["resolved_type"]
        counts["resolved"][resolved_type] += 1
        if resolved_type == "Location":
            counts["location_names"][entry["text"]] += 1
        elif resolved_type == "Character":
            counts["character_names"][entry["text"]] += 1

    for sent in doc.sents:
        counts["sentences"] += 1
        has_character = any(resolved_map.get(ent.text) == "Character" for ent in sent.ents)
        has_location = any(resolved_map.get(ent.text) == "Location" for ent in sent.ents)
        if has_character:
            counts["with_character"] += 1
        if has_location:
            counts["with_location"] += 1
        if has_character and has_location:
            counts["with_both"] += 1

    counts["pairs"].extend(
        pair_character_locations(doc, para.chapter, para.index, resolved_map)
    )


def measure_both(paragraphs):
    """Count the same parse with and without registry injection.

    The before column is the spaCy-only condition audit.py reports, so the two
    instruments should agree on entity count. One parse serves both columns, so
    neither can be measuring different text from the other.
    """
    before = new_counts()
    after = new_counts()

    for para in paragraphs:
        doc = nlp(normalise(para.text))

        # inject_registry_entities reassigns doc.ents, so the before counts are
        # unrecoverable once it has run.
        count_into(before, doc, para)
        inject_registry_entities(doc)
        count_into(after, doc, para)

    return before, after


def pair_key(pair):
    return (pair["chapter"], pair["paragraph"], pair["character"], pair["location"])


def print_row(label, before_value, after_value):
    print(f"  {label:26}{before_value:>8}{after_value:>8}")


def main():
    paragraphs = load_paragraphs()
    before, after = measure_both(paragraphs)

    print(f"Corpus: {len(paragraphs)} paragraphs, {after['sentences']} sentences")
    print(f"\n{'':28}{'BEFORE':>8}{'AFTER':>8}")

    print_row("entities in doc.ents", before["entities"], after["entities"])

    for resolved_type in ("Character", "Location", "Organisation", None):
        print_row(
            f"resolved {resolved_type}",
            before["resolved"][resolved_type],
            after["resolved"][resolved_type],
        )

    print_row("distinct Location names", len(before["location_names"]), len(after["location_names"]))
    print_row("distinct Character names", len(before["character_names"]), len(after["character_names"]))

    print_row("sentences", before["sentences"], after["sentences"])
    print_row("with a Character", before["with_character"], after["with_character"])
    print_row("with a Location", before["with_location"], after["with_location"])
    print_row("with BOTH", before["with_both"], after["with_both"])

    print_row("pairs", len(before["pairs"]), len(after["pairs"]))

    print("\nLocation names, after injection:")
    for name, n in after["location_names"].most_common():
        print(f"  {name:26} {n}")

    print("\nCharacter names, after injection:")
    for name, n in after["character_names"].most_common():
        print(f"  {name:26} {n}")

    print(f"\nPairs after injection: {len(after['pairs'])}")
    for pair in after["pairs"]:
        print(f"  ch{pair['chapter']} p{pair['paragraph']:<4} {pair['character']} -> {pair['location']}")

    gained = [p for p in after["pairs"] if pair_key(p) not in {pair_key(q) for q in before["pairs"]}]
    print(f"\nPairs injection added: {len(gained)}")
    for pair in gained:
        print(f"  ch{pair['chapter']} p{pair['paragraph']:<4} {pair['character']} -> {pair['location']}")


if __name__ == "__main__":
    main()
