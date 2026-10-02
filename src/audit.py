"""spaCy-only audit of the corpus against the registry.

No injection, so this is the baseline. Prints a report and writes audit_report.csv.
"""

import csv
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from config import nlp
from corpus import CORPUS_PATH, load_paragraphs, normalise
from extraction import resolve_entity_types
from registry import registry, SPACY_TO_SCHEMA

OUTPUT_CSV = Path(__file__).parent.parent / "audit_report.csv"


def build_registry_pattern(keys) -> re.Pattern:
    """One regex for every registry key, longest first so the full name wins."""
    ordered_keys = sorted(keys, key=len, reverse=True)
    alternation = "|".join(re.escape(key) for key in ordered_keys)
    return re.compile(rf"\b(?:{alternation})\b")


REGISTRY_PATTERN = build_registry_pattern(registry.keys())


def classify_occurrence(occ_start: int, occ_end: int, entity_spans) -> str:
    """How spaCy saw one registry key: EXACT, CONTAINED, PARTIAL or ABSENT."""
    overlapping = [(s, e) for s, e in entity_spans if s < occ_end and e > occ_start]
    if not overlapping:
        return "ABSENT"
    if any(s == occ_start and e == occ_end for s, e in overlapping):
        return "EXACT"
    if any(s <= occ_start and e >= occ_end for s, e in overlapping):
        return "CONTAINED"
    return "PARTIAL"


def main():
    """Runs the audit over the whole corpus."""
    paragraphs = load_paragraphs()

    run_date = date.today().isoformat()
    corpus_name = CORPUS_PATH.name
    total_words = 0

    csv_rows = []

    label_counts = Counter()
    resolved_type_counts = Counter()
    agreements = Counter()
    corrections = Counter()

    doc_ents_texts = Counter()
    registry_occurrences = Counter()
    key_classification = defaultdict(Counter)

    for para in paragraphs:
        text = normalise(para.text)
        total_words += len(text.split())

        doc = nlp(text)

        entity_spans = [(ent.start_char, ent.end_char) for ent in doc.ents]

        for resolved in resolve_entity_types(doc):
            entity_text = resolved["text"]
            spacy_label = resolved["label"]
            resolved_type = resolved["resolved_type"]

            label_counts[spacy_label] += 1
            resolved_type_counts[resolved_type] += 1
            doc_ents_texts[entity_text] += 1

            csv_rows.append({
                "source": "doc_ents",
                "chapter": para.chapter,
                "paragraph_index": para.index,
                "text": entity_text,
                "spacy_label": spacy_label,
                "resolved_type": resolved_type,
                "classification": "",
            })

            registry_type = registry.get(entity_text)
            if registry_type is not None:
                auto_type = SPACY_TO_SCHEMA.get(spacy_label)
                pair = (spacy_label, registry_type)
                if auto_type == registry_type:
                    agreements[pair] += 1
                else:
                    corrections[pair] += 1

        # second pass: find each registry key in the raw text and check what spaCy made of it
        for match in REGISTRY_PATTERN.finditer(text):
            key = match.group(0)
            occ_start, occ_end = match.span()
            classification = classify_occurrence(occ_start, occ_end, entity_spans)

            registry_occurrences[key] += 1
            key_classification[key][classification] += 1

            csv_rows.append({
                "source": "registry_search",
                "chapter": para.chapter,
                "paragraph_index": para.index,
                "text": key,
                "spacy_label": "",
                "resolved_type": registry[key],
                "classification": classification,
            })

    in_registry = set(registry)
    in_corpus = {key for key, n in registry_occurrences.items() if n > 0}
    in_doc_ents = set(doc_ents_texts)

    bucket_a = in_registry - in_corpus
    bucket_d = in_doc_ents - in_registry

    print_report(
        corpus_name, total_words, run_date,
        label_counts, resolved_type_counts,
        agreements, corrections,
        bucket_a, bucket_d,
        key_classification, registry_occurrences,
    )

    write_csv(csv_rows, corpus_name, total_words, run_date)
    print(f"\nWrote {len(csv_rows)} rows to {OUTPUT_CSV}")


def print_report(
    corpus_name, total_words, run_date,
    label_counts, resolved_type_counts,
    agreements, corrections,
    bucket_a, bucket_d,
    key_classification, registry_occurrences,
):
    print(f"Corpus: {corpus_name}  ({total_words} words)  run {run_date}")
    print("*** development-set figures on an unfinished corpus — not final results ***")
    print("*** nlp() run per paragraph, not per chapter ***")

    print(f"\n1. Total entities in doc.ents: {sum(label_counts.values())}")
    for label, n in label_counts.most_common():
        print(f"     {label:12} {n}")

    print(f"\n2. Resolved types ({sum(resolved_type_counts.values())} entities):")
    for resolved_type, n in resolved_type_counts.most_common():
        print(f"     {str(resolved_type):12} {n}")

    print(f"\n3. Registry overrides — AGREEMENTS ({sum(agreements.values())}):")
    print("     spaCy label -> resolved type      count")
    for (label, resolved_type), n in agreements.most_common():
        print(f"     {label:12} -> {resolved_type:12}   {n}")
    print(f"   Registry overrides — CORRECTIONS ({sum(corrections.values())}):")
    for (label, resolved_type), n in corrections.most_common():
        print(f"     {label:12} -> {resolved_type:12}   {n}")

    total_occurrences = sum(registry_occurrences.values())
    total_exact = sum(c["EXACT"] for c in key_classification.values())
    total_contained = sum(c["CONTAINED"] for c in key_classification.values())
    total_partial = sum(c["PARTIAL"] for c in key_classification.values())
    total_absent = sum(c["ABSENT"] for c in key_classification.values())

    print("\n4. Buckets:")
    print(f"     (a) in registry, NOT in corpus:        {len(bucket_a):4}  keys")
    print(f"     (d) in doc.ents, NOT in registry:      {len(bucket_d):4}  texts")

    print(f"\n   Registry-key occurrences found in corpus: {total_occurrences}")
    print(f"     EXACT      {total_exact:4}  ({_pct(total_exact, total_occurrences)})")
    print(f"     CONTAINED  {total_contained:4}  ({_pct(total_contained, total_occurrences)})")
    print(f"     PARTIAL    {total_partial:4}  ({_pct(total_partial, total_occurrences)})")
    print(f"     ABSENT     {total_absent:4}  ({_pct(total_absent, total_occurrences)})")

    if key_classification:
        print("\n   Per registry key (occurrences, exact, contained, partial, absent, exact_rate, coverage):")
        rows = []
        for key, counts in key_classification.items():
            occurrences = registry_occurrences[key]
            exact = counts["EXACT"]
            contained = counts["CONTAINED"]
            partial = counts["PARTIAL"]
            absent = counts["ABSENT"]
            exact_rate = exact / occurrences if occurrences else 0.0
            coverage = (exact + contained + partial) / occurrences if occurrences else 0.0
            rows.append((key, occurrences, exact, contained, partial, absent, exact_rate, coverage))
        rows.sort(key=lambda r: (-r[5], r[0]))
        for key, occurrences, exact, contained, partial, absent, exact_rate, coverage in rows:
            print(
                f"     {key:30} occ={occurrences:4}  exact={exact:4}  contained={contained:4}  "
                f"partial={partial:4}  absent={absent:4}  exact_rate={exact_rate:.0%}  coverage={coverage:.0%}"
            )


def _pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"


def write_csv(csv_rows, corpus_name, total_words, run_date):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "corpus_name", "corpus_words", "run_date",
            "source", "chapter", "paragraph_index",
            "text", "spacy_label", "resolved_type", "classification",
        ])
        writer.writeheader()
        for row in csv_rows:
            writer.writerow({
                "corpus_name": corpus_name,
                "corpus_words": total_words,
                "run_date": run_date,
                **row,
            })


if __name__ == "__main__":
    main()
