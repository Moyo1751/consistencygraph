from collections import Counter, defaultdict
from pathlib import Path

from config import nlp
from registry import lookup, SPACY_TO_SCHEMA

MANUSCRIPT_DIR = Path(__file__).parent.parent / "manuscript"

chapter_files = sorted(MANUSCRIPT_DIR.glob("*.txt"))

all_ents = []

for path in chapter_files:
    text = path.read_text(encoding="utf-8")
    chapter = int(path.stem.split("_")[1])
    doc = nlp(text)
    all_ents.extend(doc.ents)
    print(f"{path.name}  chapter {chapter}  {len(text.split())} words  {len(doc.ents)} entities")

print(f"\nTotal entities: {len(all_ents)}")
for label, n in Counter(ent.label_ for ent in all_ents).most_common():
    print(f"  {label:10} {n}")

by_label = defaultdict(Counter)
for ent in all_ents:
    by_label[ent.label_][ent.text] += 1

for label, texts in sorted(by_label.items()):
    print(f"\n{label}  ({sum(texts.values())} mentions, {len(texts)} distinct)")
    for text, n in texts.most_common():
        print(f"    {text:30} {n}")