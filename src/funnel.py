from collections import Counter

from config import nlp
from corpus import load_paragraphs, normalise
from extraction import pair_character_locations, resolve_entity_types


def main():
    paragraphs = load_paragraphs()

    entity_count = 0
    resolved_counts = Counter()
    location_names = Counter()
    character_names = Counter()
    sentence_count = 0
    sents_with_character = 0
    sents_with_location = 0
    sents_with_both = 0
    all_pairs = []

    for para in paragraphs:
        text = normalise(para.text)
        doc = nlp(text)

        resolved = resolve_entity_types(doc)
        resolved_map = {ent["text"]: ent["resolved_type"] for ent in resolved}

        entity_count += len(doc.ents)

        for entry in resolved:
            resolved_type = entry["resolved_type"]
            resolved_counts[resolved_type] += 1
            if resolved_type == "Location":
                location_names[entry["text"]] += 1
            elif resolved_type == "Character":
                character_names[entry["text"]] += 1

        for sent in doc.sents:
            sentence_count += 1
            has_character = any(resolved_map.get(ent.text) == "Character" for ent in sent.ents)
            has_location = any(resolved_map.get(ent.text) == "Location" for ent in sent.ents)
            if has_character:
                sents_with_character += 1
            if has_location:
                sents_with_location += 1
            if has_character and has_location:
                sents_with_both += 1

        all_pairs.extend(pair_character_locations(doc, para.chapter, resolved_map))

    print(f"Corpus: {len(paragraphs)} paragraphs, {sentence_count} sentences")
    print(f"Entities in doc.ents: {entity_count}")

    print("\nResolved types:")
    for resolved_type, n in resolved_counts.most_common():
        print(f"  {str(resolved_type):14} {n}")

    print(f"\nDistinct Location names: {len(location_names)}")
    for name, n in location_names.most_common():
        print(f"  {name:24} {n}")

    print(f"\nDistinct Character names: {len(character_names)}")
    for name, n in character_names.most_common():
        print(f"  {name:24} {n}")

    print("\nSentence funnel:")
    print(f"  sentences          {sentence_count}")
    print(f"  with a Character   {sents_with_character}")
    print(f"  with a Location    {sents_with_location}")
    print(f"  with BOTH          {sents_with_both}")

    print(f"\nPairs produced: {len(all_pairs)}")
    for pair in all_pairs:
        print(f"  ch{pair['chapter']}  {pair['character']} -> {pair['location']}")


if __name__ == "__main__":
    main()