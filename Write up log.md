# Dissertation Write-Up Log

A running capture of findings, decisions, and limitations to fold into the
dissertation. Append as they arise — don't trust memory three weeks later.
Each entry notes which research question (RQ) or chapter it serves.

RQ reference:

- RQ1: How well does NER perform on invented fantasy names?
- RQ2: Can a knowledge graph capture enough of a fictional world for consistency checking?
- RQ3: Which inconsistency types are detectable automatically vs. need human judgement?
- RQ4: Does adding LLM reasoning improve detection over pure graph queries?

---

## RQ1 — Baseline spaCy NER on invented names (17 Jul)

Method: ran bare `en_core_web_sm` NER (no registry) on a passage of own fantasy
prose, varying the location name to isolate behaviour. Baseline measured BEFORE
building the registry so spaCy's naked performance is attributable (see CG-11).

### Finding 1 — Person names: handled well

spaCy correctly tagged invented personal names as PERSON, including invented
surnames (e.g. "Aldric Stormborn" -> PERSON; "King Aldric" -> PERSON).

### Finding 2 — Locations: unreliable, and the predictor is MORPHOLOGY, not inventedness

Controlled variation of the place name in a fixed sentence:

- Seattle, London -> GPE (real places)
- Kaldon, Thornton -> GPE (INVENTED, but English place-name morphology)
- Thornhaven -> CARDINAL (invented; misclassified as a NUMBER)

Key insight: it is NOT "invented = fail." Kaldon and Thornton are invented and
were classified correctly. The differentiator appears to be morphological
resemblance to real English place-names — common settlement suffixes like
"-ton"/"-don" (Brighton, London) are recognised; rarer forms like "-haven" are
not. spaCy leans on sub-word/orthographic features, so an invented name that
"wears the costume" of a real place-type is tagged correctly; one that doesn't
is guessed wildly (here, as CARDINAL).

Consequence for a consistency checker: the failure is UNPREDICTABLE per-name.
You cannot know which locations were silently dropped/misclassified, which is
arguably worse than uniform failure. This is the empirical justification for the
manual entity registry (CG-10): identify entities by KNOWN IDENTITY, not by
spaCy's guessed type. A label-filter (e.g. "keep only GPE") is therefore unsafe
— it would silently drop "Thornhaven" because spaCy called it CARDINAL.

### Finding 3 — String-exact entity identity is fragile in BOTH directions

NOTE: "Aldric Stormborn" (son) and "King Aldric the Elder" (father) are DIFFERENT
characters, not two mentions of one — do not conflate (earlier assumption was wrong).
The real issue: keying character identity on the exact string (as
`MERGE (c:Character {name: $name})` does) is fragile two ways:
(a) SPLITS one character across name variants ("Aldric Stormborn" vs bare "Aldric"),
(b) COLLIDES two distinct characters who share a name fragment ("Aldric").
Motivates a registry/identity resolution keyed on identity, not raw surface string.
Relevant to CG-10 (registry) and CG-13 (storage). Also an RQ3 limitation to name.

### Cross-cutting note — one pipeline's noise is another's signal

In the test sentence, "fifteen years" (DATE) and "twelve" (CARDINAL) are noise
for LOCATION detection but SIGNAL for AGE/TIMELINE detection: "hadn't seen it in
fifteen years… a boy of twelve" encodes age progression (12, +15y => ~27). This
supports the design decision that `extract()` stays label-agnostic and filtering
happens at the CONSUMER, not inside extraction — the tokens the location pipeline
discards are exactly what the age pipeline consumes.

---

## Deferred refactors — extract() (17 Jul)

extract() is done for now. It returns a list of dicts (text, label, chapter,
startChar, endChar), doesn't print anything itself, has type hints, and returns
all spaCy labels rather than filtering — filtering happens later, at the consumer.

Things to improve later, noted so I don't forget them:

- Return type is list[dict[str, str | int]]. It works but doesn't say which key is
  which type. A TypedDict or dataclass would. Skipped for now — a plain dict is
  fine for getting text flowing. Do it at hardening.
- extract() builds the whole list in memory. At full novel length a generator
  (yield one mention at a time) would scale better. Skipped for now — a chapter's
  entities are tiny, and a generator would complicate the storage step. Convert at scale.
- Swapped the loop+append for a list comprehension. Checked the output is identical
  to the old version, so it's a safe refactor.

## Extraction vs storage — the gap (17 Jul)

extract() returns entities one by one, tagged by spaCy type (PERSON, GPE, DATE,
CARDINAL). Storage needs relationships instead: a character AT a location, a
character WITH an age. So something has to sit in between and do two jobs:

1. Map spaCy labels to my schema roles (PERSON -> Character, GPE -> Location).
2. Work out which entities go together (Aldric is at Thornton) — the entity list
   doesn't say this; the pairing has to be worked out separately.

Job 1 is easy. Job 2 is the hard part and is really relationship extraction, which
is harder than entity extraction — worth saying so for RQ2/RQ3.

## Crude character–location pairing (24 Jul)

Built pair_character_locations(text, chapter) as the first middle layer between
extraction and storage. Approach: walk doc.sents; within each sentence collect
PERSON entities and GPE entities into two lists; emit a pairing for every
person × location in that sentence. Returns list of dicts:
{"character", "location", "chapter"}.

Deliberate choices / known limitations (all for the evaluation + RQ3 discussion):

- GPE only. Dropped CARDINAL from the location filter — it was scooping up numbers
  like "twelve" as locations. Cost: invented names spaCy misreads as CARDINAL
  (e.g. Thornhaven) are missed here. That's the registry's job (CG-10), not the
  pairer's. Verified: the Thornhaven sentence correctly returns [] (no pair);
  the Thornton sentence returns the pair.
- Same-sentence assumption is crude. If a person and place sit in different
  sentences, no pair is made — observed directly (King Aldric didn't pair with
  Thornton because the sentence boundary fell between them). Cross-sentence
  relationships are missed.
- No verb/negation awareness. "Aldric had never been to X" would still pair
  Aldric with X. Same-sentence co-occurrence ≠ actually being there.
- Over-pairing: N people + M places in one sentence => N×M pairs, some wrong.

Planned improvement (deferred): use dependency parse / preposition + verb evidence
("in"/"at" vs "never"/"left") instead of raw co-occurrence. More accurate,
more work. This is the entity-vs-relationship-extraction difficulty gap (RQ2/RQ3).

Also deferred: pair() and extract() each call nlp(text) separately (two passes).
Dedupe by creating doc once and passing it to both, once the module split happens.

## CG-11 done — full pipeline round-trip (4 Aug)

End-to-end pipeline working: prose -> spaCy extraction -> same-sentence pairing
-> store_pairs() loop -> Neo4j. Verified in Neo4j Browser: the sentence
"Aldric Stormborn had not seen the walls of Thornton..." produced three nodes —
Character (Aldric Stormborn), Location (Thornton), and a Presence node
(chapter: 1) linking them via IS_AT and LOCATION. The reification pattern
(Character -[:IS_AT]-> Presence -[:LOCATION]-> Location, chapter on Presence)
confirmed working on real extracted data, not hardcoded facts.

Wiring: new file pipeline.py imports pair_character_locations from extract and
store_character_location/clear_database from demo, defines store_pairs(pairs)
which loops pairs and calls storage. Option B taken: store functions still use
the module-global driver (driver-as-parameter refactor deferred to CG-13).

Limitation reconfirmed live: only "Aldric -> Thornton" stored; "King Aldric the
Elder" in the same test text was NOT paired because a sentence boundary fell
between him and Thornton. The end-to-end run reproduced the known cross-sentence
miss (already logged 24 Jul). Nothing to fix — expected behaviour.

Still pending in Foundation: CG-10 (registry — the main unbuilt piece, rescues
CARDINAL-misclassified locations like Thornhaven), CG-12 (schema — mostly
designed, needs writing up + sentence_index decision), CG-13 (storage — store
functions exist; remaining work is driver-as-parameter refactor). Also still
pending: proper module split (extraction / storage / detection) and dedupe of
the double nlp() load across extract.py and demo.py.

## CG-10 registry — started (6 Aug)

Manual entity registry: closes the RQ1 gap from the baseline (spaCy misclassifies
invented locations by morphology, e.g. Thornhaven -> CARDINAL). Registry keys on
KNOWN IDENTITY instead of spaCy's guessed label. Chosen design (Path A): a flat
JSON name->type map, loaded into a dict, looked up with .get() (returns None on
miss). Kept transparent/explicit rather than spaCy's built-in EntityRuler (Path B)
so the registry's correction is measurable for RQ1 (can log "spaCy said X, registry
overrode to Y"). EntityRuler noted as the slicker-but-less-measurable alternative.

Registry values use SCHEMA vocabulary (Character/Location), not spaCy's
(PERSON/GPE), so no translation needed downstream.

DEFERRED / schema decisions surfaced:

- Organisations (Houses, The Magic Tower, Kerenath, Zemarel) PARKED. The pipeline
  has no Organisation node type — schema handles Character + Location only.
  CG-12 needs to decide: what IS a House in the graph? (a Location? a group of
  Characters? a new node type with its own relationships?). Until then, ORG-type
  names stay out of the registry. Scratch list to re-add later: The Magic Tower,
  House Zemarel, House Kerenath, Kerenath, Zemarel.
- Name-variant aliasing reconfirmed: "Roisen"/"Roisen Vardael"/"Ro"/"Vardael" are
  one character but four dict keys. Fine for typing (all -> Character), but MERGE
  keys on exact string, so the graph will treat them as four separate people.
  Same fragility logged 24 Jul/RQ1 Finding 3. Not solved this sprint.

Corpus note: made-up names used for code testing are THROWAWAY plumbing data —
findings must only accrue to the real invented names (Thornhaven etc.). The
evaluation corpus (CG-16) must be the real manuscript. When writing the 3-4 test
chapters (~1-3k words each), PLANT deliberate, annotated inconsistencies (aim for
~20 across age/location/timeline) and keep a gold-standard annotation of where
they are. Optimise for inconsistency COUNT, not word count.

## Planned module split (6 Aug) — DEFERRED, do not do mid-task

pipeline.py is accreting unrelated jobs (registry, storage wiring, resolution).
Target structure once the pipeline flows and there's a natural pause:

- config.py (or shared.py): the nlp and driver globals, created ONCE and imported
  everywhere. Also kills the double nlp() load (extract.py + demo.py each load
  spaCy today).
- registry.py: JSON load + lookup().
- extraction.py: extract, pair_character_locations, resolve_entity_types
  (everything that turns text into resolved facts).
- storage.py: store_character_location, store_pairs, clear_database.
- detection.py: find_age_inconsistencies, find_location_inconsistencies.
- pipeline.py: becomes THIN — imports the above and orchestrates the flow only.

Deliberately NO utils.py: "utilities/helpers/misc" files have no cohesion and
become a second junk drawer. Group by what code is ABOUT (its domain), not by
"it's a helper." Only add utils.py if a genuinely generic function emerges from
real duplication — let it emerge, don't pre-build the bucket.

Not to be done until Foundation code flows end-to-end. This is a tidy-up pass,
not a feature — must not displace actual build work.

## CG-10 registry integration working — resolve_entity_types (6 Aug)

resolve_entity_types(entities) implements registry-as-authority resolution.
Per entity, three-step priority: (1) registry lookup on the text wins if hit;
(2) else translate spaCy label via SPACY_TO_SCHEMA (PERSON->Character,
GPE->Location); (3) else None. Output keeps spaCy's raw `label` UNTOUCHED and
adds `resolved_type` — so the before/after is preserved for RQ1.

VERIFIED — the key RQ1 result, in the data:
Thornhaven -> label=CARDINAL, resolved_type=Location
spaCy misclassified the invented location as CARDINAL (a number); the registry
recovered it as Location. Both values coexist in the output, so the correction
is measurable (spaCy-said vs registry-resolved). This is the empirical payoff of
the registry and the answer to "does the registry fix the morphology-driven NER
failure" — yes, and here's the evidence row.

All four branches confirmed on one sentence:

- Thornhaven: CARDINAL -> Location (registry rescued a spaCy failure)
- Kaldon: GPE -> Location (spaCy right; map translates to schema vocab)
- King Reveth/Shadow Blade: PERSON -> Character (map, no registry entry needed)
- fifteen years / twelve: DATE|CARDINAL -> None (no schema home; ignored downstream)

Noticed (not fixed): "King Reveth the Shadow Blade" — spaCy split the epithet, so
"Shadow Blade" became a phantom PERSON->Character. Entity-boundary fragility, same
family as baseline NER limitations. Not a resolution bug. Flag for RQ1/RQ3 limits.

Still to do on CG-10: resolve_entity_types is verified in isolation but NOT yet
wired into the storage flow — pairing/storage still consume raw extract output,
so Thornhaven's rescue doesn't yet reach Neo4j. Wiring resolution into the
pipeline is the remaining step.

## CG-10 wiring + a key RQ1 finding: two NER failure modes (14 Aug)

Wired resolution into the storage path (Option B): create doc = nlp(text) ONCE,
resolve_entity_types(doc) reads doc.ents, orchestrator builds a {text:resolved_type}
map, pair_character_locations(doc, chapter, resolved_map) now filters on
resolved_map.get(ent.text) == "Character"/"Location" instead of raw spaCy labels.
Also imports the single shared nlp from extract (kills the double nlp() load).

Thornhaven half works: resolves CARDINAL -> Location correctly via registry.

BUT running on "Elior Kerenath had not seen the walls of Thornhaven..." produced
EMPTY pairs. Diagnosis (verified by printing doc.ents):
Entities found: (Thornhaven, fifteen years, twelve, King Reveth, Shadow Blade)
"Elior Kerenath" is NOT in doc.ents at all — spaCy never detected it as an entity.
Shortening to bare "Kerenath" ALSO missed. So the invented name at sentence-start
isn't picked up, while "King Reveth" IS (the title "King" likely cues spaCy's model).

=> KEY RQ1 FINDING: there are TWO distinct NER failure modes, and the registry
only addresses one:

1. MISCLASSIFICATION — spaCy finds the entity, wrong type (Thornhaven->CARDINAL).
   Registry FIXES this (resolve_entity_types overrides the label). ✓
2. NON-DETECTION — spaCy never emits the entity at all (Elior/Kerenath).
   Registry CANNOT fix this: resolve_entity_types only loops doc.ents, so a name
   spaCy didn't find is never looked up. The registry entry for "Elior Kerenath"
   exists but is never consulted.

Consequence: registry-as-authority-over-spaCy corrects labels but cannot recover
missed entities. To catch non-detection, the registry must be consulted
INDEPENDENTLY of spaCy detection — i.e. scan text for registered names directly
(spaCy PhraseMatcher / EntityRuler injects known names so they BECOME entities).
That is the genuine "hybrid" pipeline. DEFERRED — real design change, do rested.
This limitation is itself a strong RQ1/RQ3 result (honest failure-mode taxonomy),
worth more written up clearly than rushed into a fix tonight.

Also noted: "Shadow Blade" still appears as a phantom PERSON->Character (epithet
split from "King Reveth the Shadow Blade"). Entity-boundary error, separate issue.
