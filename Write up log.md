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
  [SUPERSEDED 21 Sep] These specific keys no longer match the manuscript. The
  character is now "Roisen Kedvara Kerenath" and "Vardael"/"Ro" appear nowhere
  in it. The aliasing fragility still stands as a finding; these particular
  strings do not. See the registry rebuild entry, 21 Sep.

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

[CORRECTED 18 Sep] This claim was WRONG and stood uncorrected for a month.
spacy.load("en_core_web_sm") remained in BOTH demo.py and extract.py, and
pipeline.py imported from both files, so both module bodies executed and the
model still loaded TWICE on every run. What was actually fixed here was that
pipeline.py started importing the shared nlp; the second load survived
unnoticed. Genuinely fixed at CG-21 (18 Sep), where config.py became the single
load site. See the CG-21 entry.

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

## CG-12 schema design — decided (18 Aug)

Schema document structure (standalone SCHEMA.md, feeds Methodology + Implementation chapters):

1. Entities: Character, Location, Presence, Organisation (+ properties: name, chapter, age)
2. Relationships: IS_AT, LOCATION, HAS_AGE, MEMBER_OF
3. Composition: the reification chain — Character-[:IS_AT]->Presence-[:LOCATION]->Location,
   chapter stored on Presence (the reified occurrence)
4. Design rationale (STANDALONE section — decided to separate rather than weave, so the
   reader grasps structure first then reasoning as one narrative; also citable as a unit
   for the methodology chapter): why reification vs direct edge; why MERGE (Character/Location)
   vs CREATE (AgeMention/Presence); why chapter-on-Presence; why Organisation-as-flat-node.
5. Deferred / limitations: rich House structure; name-variant identity fragility; non-detection.

ORGANISATION decision: modelled MINIMALLY — an Organisation node (name) with
Character-[:MEMBER_OF]->Organisation. Houses, companies, groups, orders are all just
Organisation nodes differing only by name. The rich structure (lineage, collaterals,
retainers, knight orders, advisors) is DEFERRED — no inconsistency-detection case requires
house-internal structure, so modelling it would be world-building scope creep, not RQ work.
BUILD STATUS (be honest in write-up + viva): Organisation + MEMBER_OF are DESIGNED, NOT
IMPLEMENTED. Character/Location are built end-to-end; Organisation storage/extraction is a
small follow-up (re-add ORG entries to registry, map ORG->Organisation, add store fn).

## CG-20 driver-as-parameter refactor — done (18 Aug)

Removed the module-global Neo4j driver. All DB functions (clear_database,
store_character_age, store_character_location, find_age_inconsistencies,
find_location_inconsistencies, store_pairs) now take `driver` as the LAST
parameter, consistently. Entry point (**main**) creates the driver and owns its
lifecycle (create + close). Pure refactor — output unchanged (Reveth at Thornhaven
still lands in the graph). Rationale for the write-up: functions that RECEIVE the
driver are testable (can be handed a test-DB driver) and have no import-time side
effect, unlike reaching for a module global.

Two follow-ups surfaced (NOT done here):

- pipeline.py's **main** should also driver.close() (entry point owns lifecycle;
  demo.py does close, pipeline.py currently doesn't). Tidy resource handling —
  matters for the "good practice" mark and viva. One line.
  [DONE, confirmed present in pipeline.py at the CG-21 split, 18 Sep. Closed
  at some point between 18 Aug and 18 Sep but never logged.]
- The driver-creation block (load_dotenv / URI / AUTH / GraphDatabase.driver) is
  now DUPLICATED verbatim in demo.py and pipeline.py. This is concrete motivation
  for CG-21 (module split): a shared config.py should own driver + nlp creation,
  imported by both. CG-20 surfaced CG-21's need. Deferred to CG-21.
  [DONE at CG-21, 18 Sep. config.py now owns it, exposed as get_driver(),
  a function rather than the module-level global this entry envisaged.]

## CG-15 location-query dedup fix (18 Aug)

Fixed the duplicate-location-inconsistency bug in find_location_inconsistencies.
Changed WHERE l1.name <> l2.name -> WHERE l1.name < l2.name.
Why: the query self-joins a character's locations (l1 x l2). <> is SYMMETRIC, so
both (A,B) and (B,A) survive -> the same clash printed twice ("Mount Kaelos and
Thornhaven" AND "Thornhaven and Mount Kaelos"). < is ASYMMETRIC (one ordering
only) and STRICT (excludes A,A self-pairs for free) -> each unordered pair
appears once, self-pairs excluded, in a single operator. Verified: Aldric now
yields ONE location-inconsistency line, age inconsistency still fires.
General idiom: self-join where pair order doesn't matter -> constrain with < to
get each pair once (SQL and Cypher alike). Age query already used this (< on chapter).

Deferred (part of CG-21): move find_age_inconsistencies / find_location_inconsistencies
out of demo.py into a proper detection.py. demo.py is a poor home for production
detection logic (named "demo", still holds the old hardcoded Aldric script, and the
pipeline importing detection FROM a demo file is a smell). Decided NOT to do a partial
split now — a half-moved codebase is messier than none. Do the detection slice as part
of the full CG-21 module split (config/registry/extraction/storage/detection + thin
pipeline), not ad hoc.

## CG-15 scope + the journey problem (KNOWN LIMITATION, RQ3) (18 Aug)

CG-15 scoped as: same-chapter multi-location clash detection at CHAPTER granularity.
Dedup fixed (< operator). This is DONE at that scope.

KNOWN LIMITATION (deliberately documented, not yet fixed) — "the journey problem":
The query flags a character in two different locations in the same chapter as an
inconsistency. But a character who legitimately TRAVELS within a chapter (Mount
Kaelos in the morning, Thornhaven by evening) is genuinely in two places and is
NOT inconsistent. The current query cannot distinguish "in two places at once"
(real inconsistency) from "moved between two places" (fine), so it produces FALSE
POSITIVES for legitimate intra-chapter travel.

Why this is an RQ3 result, not just a bug: RQ3 asks which inconsistencies can be
reliably detected automatically vs. need human judgement. The journey problem is a
clean example of the limit of automated detection at chapter granularity — worth
writing up in the evaluation chapter as a precision cost with a clear cause.

DESIGNED FIX (deferred — revisit only when everything else is done):
Add sentence_index (a monotonic position counter over the text) to the Presence
node. Two presences in the same chapter but different sentence positions => movement
(sequential) => not flagged. Two at effectively the same position => simultaneous
=> flagged. Requires: (a) schema change on Presence (CG-12/CG-13 touch), (b) pairing
records sentence position, (c) query uses it. Cross-cutting, so deferred. Note:
reading-order != story-chronology (flashbacks etc.) — a residual limitation even
after the fix, also an RQ3 point.

## CG-21 module split — done (18 Sep)

Full split executed in one pass: demo/ renamed to src/, code redistributed
across config.py, registry.py, extraction.py, storage.py, detection.py and a
thin pipeline.py. demo.py is gone. Held to the 18 Aug decision not to do this
partially — a half-moved codebase is messier than none.

METHOD — baseline first. With no test suite, the substitute for tests was a
captured baseline: ran pipeline.py end to end, teed stdout to a file, and
recorded node/relationship counts from Neo4j BEFORE touching anything
(Character 1, Location 1, Presence 1; IS_AT 1, LOCATION 1). The refactor is a
pure refactor, so that output had to come back byte-identical. It did, and the
counts matched. Worth stating in the Implementation chapter: the claim "pure
refactor" is only honest if there is evidence for it, and with no tests the
evidence has to be a recorded before-state.

Committed in TWO commits deliberately. Git does not store renames, it infers
them by content similarity at diff time. storage.py (from demo.py) loses both
detection functions and the whole old demo script, roughly half the file, so
renaming and gutting in one commit would likely drop below git's similarity
threshold and break `git log --follow`. Pure renames committed first (all four
detected at 100%), content redistribution second.

DESIGN DECISIONS taken during the split:

- config.py exposes get_driver() as a FUNCTION, not a module-level driver
  object. This DEVIATES from the CG-21 ticket text, which specified "nlp and
  driver globals." The deviation is deliberate and resolves a contradiction
  between CG-21 and CG-20: CG-20 exists precisely to remove the module-global
  driver. Two reasons a factory is right: (a) ownership — whoever creates the
  driver closes it, and a module-level driver has no obvious owner; (b) a
  module-level driver would mean `from config import nlp` reads os.environ at
  import time, so audit.py (which needs spaCy and never touches Neo4j) would
  fail with a KeyError for an unrelated reason if .env were missing. Note for
  the viva: the tickets contradicted each other and the code resolves it.
- Modules kept FLAT, no __init__.py. Adding one makes src/ a package, which
  changes invocation to `python -m src.pipeline` and rewrites every
  cross-module import. Extra scope for no benefit today. Consequence: the
  pipeline must be run from inside src/, which is now a README line.
- SPACY_TO_SCHEMA lives in registry.py alongside lookup(). lookup() is MANUAL
  type resolution, SPACY_TO_SCHEMA is AUTOMATIC type resolution, and
  resolve_entity_types tries one then falls back to the other. Putting both in
  one module means registry.py owns "how an entity's type is decided" rather
  than merely owning the JSON file.
- Still no utils.py. Nothing generic emerged, so nothing was pre-built.

The import graph is a DAG: config, registry, storage and detection import
nothing internal; extraction imports from config and registry; pipeline imports
from config, extraction and storage. Drawing the graph before moving any code
was worth the ten minutes. Python does not fail circular imports cleanly — it
hands the importing module a partially initialised one and raises
"cannot import name X from partially initialized module", with the failing name
depending on import order.

CORRECTION to the 14 Aug entry. That entry claimed the double nlp() load was
killed. It was not. `spacy.load("en_core_web_sm")` was still present in BOTH
demo.py and extract.py, and since pipeline.py imported from both files, both
module bodies executed and the model loaded twice on every run. What was
actually fixed on 14 Aug was that pipeline.py imported the shared nlp; the
second load in demo.py survived unnoticed for a month. Now genuinely one load,
in config.py. Methodological note: a fix recorded in the log but never verified
is not a fix. Worth a sentence in the write-up on the value of the log itself
being checked against the code.

CORRECTION to the 18 Aug CG-20 entry, in the other direction: the follow-up
"pipeline.py's __main__ should also driver.close()" was ALREADY DONE by the
time of the split. Closed, just never logged.

GAP FOUND during the split: pipeline.py imported find_location_inconsistencies
and never called it. The pipeline stores facts but does not invoke ANY query in
detection.py. Dropping the dead import changed no behaviour, so the baseline
held, but the gap is real and is its own ticket. Be honest about this in the
write-up: detection queries are implemented and verified in isolation, but not
yet wired into the end-to-end run.

## README and repo hygiene (18 Sep)

README written (was 18 bytes). Covers purpose, prerequisites, setup, how to run,
a module table, the graph schema, the entity-resolution design, and an explicit
"Current status" section listing the five known gaps. Writing the limitations
into the artefact's own README rather than only into the dissertation seems the
honest move for a submitted artefact.

.env confirmed NEVER committed on any branch (`git log --all -- .env` empty).
Note for anyone repeating this check: .gitignore does not untrack an
already-committed file, so `git check-ignore .env` is not the test that matters.
`git ls-files .env` is, and it must be run from the repo root — run from a
subdirectory it scopes the pathspec to that subdirectory and gives a misleading
answer.

REPRODUCIBILITY BUG FOUND: requirements.txt was UTF-16, because PowerShell's
`pip freeze > requirements.txt` writes UTF-16 by default. pip can fail to parse
that, which would have made the README's setup instructions untrue for anyone
cloning the repo, including a marker. Re-encoded as UTF-8. Same PowerShell
default also produced a UTF-16 baseline capture file. Small, but exactly the
class of thing that makes an artefact unreproducible on someone else's machine.

Good news found while checking: en_core_web_sm is pinned in requirements.txt as
a direct wheel URL, so `pip install -r requirements.txt` fetches the model and
no separate `spacy download` step is needed.

## Registry/manuscript DRIFT — new RQ1/RQ3 limitation (18 Sep)

Extracted chapters 1 and 2 of the real manuscript to plain text (2,247 words
total) as the first real corpus. Immediately found something that changes how
the audit must be built.

Word-boundary search of all 19 registry.json keys against the draft:

  Elior 25, Roisen 5, Eli 3, and the OTHER SIXTEEN keys ZERO.

Reveth, Thornhaven, Kaldon, Kedmaon, Urien, Shalvien, Zelkarev, Arnael and
Vardael appear NOWHERE in the manuscript. Meanwhile the draft's actual cast is
almost entirely absent from the registry: Oren (12), Alric (8), Arseny (5),
Talia (3), Ren (3), Malcolm (2), Yaela, plus the places Blackmere and
Hollowmere. The registry also has "Roisen Vardael Kerenath" where the text now
says "Roisen Kedvara Kerenath".

Cause: the registry was built on 6 Aug partly from worldbuilding names held in
mind at the time, and the manuscript has since been revised. Nothing warned that
they had diverged.

THIS IS ITSELF A FINDING, not just a housekeeping problem. A manually curated
registry is a static artefact that decays every time the author renames a
character or cuts a place, and the decay is SILENT — the pipeline keeps running
and simply resolves fewer entities. That is a real maintenance cost of the
registry-as-authority design (CG-10) and belongs in the limitations discussion
alongside the non-detection finding of 14 Aug. It also strengthens the CG-19
argument: a registry that must be hand-maintained against a moving manuscript is
more fragile than one whose entries are injected and therefore visibly exercised.

DECISION: do NOT update registry.json to match the current draft. The manuscript
is still being written, chapters 1 and 2 are unfinished and unannotated, and
several registry entries are speculative names that will be pruned. Rewriting it
now is churn. Instead the audit script (CG-22) must REPORT the drift as a
first-class output. A script that treats "registry key absent from corpus" as
its own category works correctly at every stage of drafting; one that assumes
registry and manuscript agree breaks the moment a character is renamed, which
has already happened once.

## CG-22 extraction audit — scope and method constraints (18 Sep)

New ticket for the script that finally READS the dual label/resolved_type
storage that resolve_entity_types has been producing since 6 Aug. Until now
that measurement apparatus has been generating evidence on every run and
discarding it.

FOUR BUCKETS the script must report, per registry key:

1. In registry, NOT in corpus — speculative or cut names. Excluded from the
   non-detection rate. Doubles as a pruning list for the author.
2. In corpus AND in doc.ents — registry consulted, working as designed.
3. In corpus but NOT in doc.ents — NON-DETECTION. The number that quantifies
   the second failure mode from 14 Aug, and the evidence that justifies CG-19.
4. In doc.ents, NOT in registry — registry coverage gap.

Collapsing bucket 1 into bucket 3 would report a catastrophic non-detection rate
that is actually just a stale file. Given 16 of 19 keys currently sit in bucket
1, this distinction is not academic.

COUNTING RULES, decided before writing the loop:

- Word boundaries throughout, or "Eli" matches inside "Elior" and "Ro" inside
  "Roisen". Confirmed live: naive substring matching reports the short aliases
  as present everywhere.
- Per-occurrence, NOT per-name boolean. Elior appears 25 times; if spaCy catches
  19, a boolean records "detected" and hides six misses. Per-occurrence yields a
  detection rate per name, which is a far more useful table.
- Nested names (Elior Kerenath contains Elior) need a stated rule, written into
  the script as a comment. A metric whose definition cannot be stated precisely
  is not usable in a results chapter.

METHOD CONSTRAINTS to state explicitly in the write-up:

- The chapters are NOT YET ANNOTATED, so there is no gold standard. The registry
  is a PROXY for ground truth, not ground truth. The audit can report what the
  system did — entity counts, label distribution, registry overrides,
  non-detections — but CANNOT report precision or recall against truth. Pre-empt
  the question rather than have it asked.
- The first run is a PILOT on ~2,200 words of draft. The instrument is the
  deliverable; the numbers are a dated snapshot, to be re-run when the manuscript
  is complete. Stamp corpus size and run date on the CSV so a provisional run is
  never mistaken for the final one.
- Write the registry BEFORE seeing which entries spaCy missed, never after.
  Adding entries in response to observed misses would invalidate the measurement.
- CSV row-per-entity rather than pre-aggregated, so it can be re-cut without
  re-running.

Corpus note, updating the 6 Aug plan: CG-16 asked for 3-4 chapters with ~20
PLANTED, annotated inconsistencies. That is still the right evaluation corpus and
is NOT what exists today. Today's two chapters are ordinary draft prose with no
deliberate inconsistencies and no annotation, so they support the RQ1 extraction
audit but not the RQ3 detection evaluation. Two distinct corpora, two distinct
purposes — do not let the audit corpus quietly become the evaluation corpus.

ORGANISATION, deferred again and now with a reason: rather than guess whether
Organisation is worth implementing, wait for the audit's ORG counts. The
manuscript contains Kerenath Enterprises and the Ravensworth pack, so there is
something to model, but designing the schema extension from a measurement beats
designing it from memory. CG-12 already has the minimal design (Organisation
node + MEMBER_OF); the audit supplies the justification for building it.

## Corpus v2 frozen, gold standard built, registry rebuilt (21 Sep)

Three days of corpus work between the CG-22 pilot audit and now. This entry
records what changed and, importantly, what it invalidates.

### The snapshot

Chapters 1 and 2 expanded from 2,247 words to 5,484 and frozen as
corpus_ch1-2_v2, in three parallel forms: the .docx as authoritative, a .json
carrying chapters and paragraph indices, and a flat .txt with [ch1:p4] markers.
v1 is kept for the record and is DEAD as a test corpus.

CORRECT BEFORE FREEZING, and the second reason is the one that matters:

1. Locators shift under every post-freeze correction, so annotations made
   before the corrections would need redoing.
2. Typos look like inconsistencies to a consistency checker. Two wrong speaker
   attributions in chapter 2 put words in the wrong character's mouth, and a
   broken verb ("he taken every opportunity") is exactly the kind of thing a
   checker may react to. Left uncorrected, a detection cannot be distinguished
   from a reaction to a typo, and the precision figure silently absorbs the
   difference.
3. Freezing a version already known to be changing defeats the purpose of a
   frozen snapshot.

Worth stating in the methodology chapter: corpus hygiene is not admin, it is a
precondition for the precision figure meaning anything.

### Locator scheme

Three fields in order of authority: quoted ANCHOR TEXT (survives any
renumbering), paragraph index, chapter. All 25 anchors across the 11 live rows
verified to resolve to the paragraph they claim.

GOTCHA recorded for implementation: the corpus uses typographic punctuation
(U+2019, U+201C, U+201D). Anchor matching must normalise first or it fails
SILENTLY. Same failure family as the UTF-16 requirements.txt on 18 Sep: an
encoding mismatch that produces no error, just wrong results.

### Gold standard v1

13 rows, 11 live, 2 retired. Origin split is deliberately lopsided:
0 planted, 2 naturally occurring, 9 LEGITIMATE.

Reasoning: recall is easy to measure once real inconsistencies exist, and none
are planted yet. Precision can only be measured against things that look wrong
and are not. So the set is precision-first by design, and the current figures
are a baseline, not a finished evaluation set.

GS-08 is the most valuable row: Alric assigns travelling teams in chapter 1 and
restates the same assignment in chapter 2 to a different audience, with no
contradiction. A checker that flags it has failed in the way a real user notices
first, regardless of its recall.

GS-07 is the most interesting: Roisen places Oren downstairs; Talia says minutes
later he left for Vienna. A SPEAKER CAN BE WRONG WITHOUT THE NARRATIVE BEING
WRONG. Flagging it is defensible; resolving it as Roisen not having been told is
better. That distinction is an RQ3 result in itself, and it is the kind of
judgement the graph cannot make alone.

RETIREMENT IS ITSELF A FINDING. GS-02's ambiguous pronoun and GS-03's height
contradiction were both removed by ordinary revision before the tool ever ran.
An author revising normally fixes some of what the checker exists to catch,
which bears directly on how such a tool would be used in practice and on what a
realistic recall target even looks like.

### Registry rebuilt: 19 entries to 103

Rebuilt from the world-building bible rather than from memory.
Character 75, Location 10, Organisation 18.

SEQUENCING IS CLEAN and worth saying so: the registry was written from the
bible, BEFORE any audit showed which entries spaCy misses. The 18 Sep
constraint ("write the registry before seeing which entries were missed, never
after") was honoured, so the measurement is not contaminated.

The 18 Sep drift finding drove this: 16 of 19 keys did not appear in the
manuscript at all. That number is now historical, but the phenomenon it named
is exactly what the rebuild answers.

Registry is now BIBLE-SCOPED, not corpus-scoped: 46 of 103 keys appear in
chapters 1 and 2, 57 do not, because their scenes are unwritten. Bucket 1 is
large BY DESIGN. Trimming to the corpus would be fitting the registry to the
test data.

### The Event gap, and why it must be decided before the schema is fixed

Three types cannot hold what the manuscript already contains. The War of Two
Monarchs appears in both chapters and does CAUSAL work: it explains Alric's
standing, and it is why Bloodbane's alpha grew strong while Duskfall lost
warriors. "The incident" anchors the timeline of the whole book.

The argument for adding Event as a fourth type is the sharpest RQ2/RQ3 point
the project has produced so far: a checker that cannot represent events cannot
catch the most valuable class of timeline contradiction, which is not two dates
disagreeing but two statements placing the same fact on OPPOSITE SIDES of an
event. "Bloodbane's alpha earned renown during the war" and "Bloodbane's alpha
was unknown until after the war" contradict each other with no date in either.
That is reasoning a graph is good at and an LLM alone is not, which is the
RQ4 comparison in miniature.

Decide now, not later: entity types set node labels and relationship endpoints,
so retrofitting a type after annotation means revisiting every row that should
have referenced it. Eight candidate entries with approximate dates are drafted.

CHARACTER IS A CATCH-ALL. It currently holds people, monikers (Cheremen,
Emissary of Destruction) and offices (High Warlord). Adequate for recognition,
but a title is a ROLE A PERSON HOLDS, not a person, so it will muddy the graph.
Titles may want to be relationships rather than nodes. Related to, but distinct
from, the name-variant fragility logged 24 Jul.

Two entities deliberately excluded: "western territories" and "eastern
territories" appear once each, lowercase. Either they are proper regions and the
prose should capitalise them, or they are descriptive and should not be entities
at all. Case-sensitive matching currently misses them either way.

### CONSEQUENCE: the 18 Sep pilot audit is void

The CG-22 audit ran against v1 (2,247 words) and the 19-entry registry. BOTH
have been replaced. Every number from that run is superseded:

- 94 entities, the label distribution, the ORG/PERSON inversion
- the 16% detection rate for "Elior"
- zero correctly identified locations
- the four registry/corpus buckets

The FINDINGS may well survive re-running; the FIGURES do not. Do not quote any
18 Sep number in the dissertation. Re-run against v2 plus the 103-entry
registry and treat that as the real pilot. The pre-registered prediction and its
scorecard remain valid as a record of what was expected versus found, but they
describe a corpus that no longer exists.

This is the "instrument is the deliverable, numbers are a dated snapshot"
principle from 18 Sep arriving sooner than expected, and it validates having
built the script to take a path rather than hardcoding the text.

### A built-in control group

The corpus contains real places and invented places in the same prose:
New York 4, Vienna 1, New Jersey 1 against Blackmere 6, Hollowmere 2. Same text,
same model, no confound.
[CORRECTED 23 Sep: Hollowmere is an ORGANISATION, not a place, and belongs in
neither column. The control is New York 4 + Vienna 1 + New Jersey 1 against
Blackmere 6. See the CG-23 entry.] A natural experiment testing the 17 Jul morphology
hypothesis on data it was not derived from.

### Registry type-system problems surfaced

24 substring-nesting pairs (Roisen inside Roisen Kedvara inside Roisen Kedvara
Kerenath; Kerenath inside four keys). Any counting must state its nesting rule.

A flat name->type map cannot express family names. Resolved 22 Sep: bare
Kerenath retyped to Character (no bare organisational use exists in the corpus);
Ravensworth and Ravensworths retyped to Organisation, since 4 of their 5 uses
are the family or pack. Oren Kerenath added, which was missing. 104 entries.
[CORRECTED 23 Sep: NONE OF THIS WAS EVER APPLIED. Verified by lookup: Kerenath
is still Organisation, Ravensworths still Character, Oren Kerenath absent. The
file holds 103 entries (Character 75, Organisation 18, Location 10). These
edits were agreed and logged but never typed into registry.json; commit
9386dd4 captured the 21 Sep rebuild instead, despite its message. Still
outstanding. See the CG-23 entry.]

Rule adopted: LONGEST-MATCH-WINS, COUNTED PER OCCURRENCE. One hit when the full
name appears; separate hits when shorter forms appear alone.

Territories dropped: "eastern territories" and "western territories" are
lowercase and descriptive, not named places. Capitalising the prose to make them
match would be a fiction decision taken for a tooling reason.

### What audit.py has to change

Input format. The script currently globs loose chapter_NN.txt files and parses
the chapter number from the filename. The frozen corpus is a single JSON with
chapters and paragraph indices. Read the JSON instead, for two reasons: the
paragraph index is one of the three locator fields the gold standard depends
on, so any finding the audit reports must be locatable against it; and the JSON
is the structured form, so no re-parsing of markers is needed.

Anchor normalisation. Typographic apostrophes must be normalised before any
string matching, per the gotcha above.

### Numbers that do not yet agree, to be reconciled

The target count for annotated inconsistencies now has three values on record:
CG-16's description says "50+", the 6 Aug log entry says "~20", and the 21 Sep
handover says "15 to 20". The plant plan's own arithmetic lands at 14. Whichever
figure is chosen becomes the denominator in the evaluation chapter, so it needs
settling once and propagating to all three places.

Separately, the handover says "14 specifications sit in the Plant Plan sheet",
but the plan lists 7 plants (P1 to P7) plus 4 legitimate rows (L1 to L4), which
is 11 specifications; 14 is the total including the 3 surviving rows. Minor, but
it is the kind of discrepancy a viva finds.

### State, so nothing is assumed

- No plants are written. The next corpus generation is v3
- Chapters 3 and 4 are unwritten; they get their OWN snapshot, not an append,
  so each frozen file keeps its own locator space
- Bloodbane and Duskfall are placeholder pack names pending a rename
- The manuscript has already moved on from this snapshot, by design

## Detection wired in, and a storage bug it exposed (22 Sep)

pipeline.py had never invoked anything in detection.py. Facts were stored and no
query ever ran. Wiring it in was three lines. Both queries returned empty, which
looked like success.

Age was empty because NOTHING CALLS store_character_age: no AgeMention nodes
exist, so the query has nothing to match. An unimplemented path, not a bug.

Location was empty because one character in one location cannot clash. Also
correct, and also uninformative.

### The positive control

Two empty results are consistent with the queries working and with them being
broken. The CG-15 verification that proved the location query fires was run
against demo.py's Aldric script, deleted in the CG-21 split, so since the
refactor neither query had ever returned a row.

Manually inserting a second location for one character in one chapter returned
TWO IDENTICAL ROWS. Not (A,B) and (B,A), which was the CG-15 symmetry bug, so
that fix survived the refactor. A second, different duplication source.

### Diagnosis: CREATE versus MERGE

store_character_location used CREATE (p:Presence {chapter: $chapter}), so every
call made a new Presence node. The detection query self-joins over Presence, so
duplicate presences multiply into duplicate findings.

Latent since CG-11 and invisible because the pipeline only ever ran on one
sentence. It would have surfaced the moment the corpus was loaded:
pair_character_locations emits every character x every location per sentence, so
a chapter where two entities co-occur five times creates five Presence nodes for
one fact, and two locations at five presences each is TWENTY-FIVE rows for one
inconsistency. The precision denominator would have been destroyed by a storage
artefact rather than a detection error.

### The fix, and the Cypher trap

The obvious fix is wrong: MERGE (p:Presence {chapter: $chapter}) matches ANY
Presence with that chapter, so every character in chapter 1 would share one
node. It fails silently and produces a populated-looking graph that is nonsense.

A Presence is identified only by the path it sits on, so the path is merged:

    MERGE (c:Character {name: $name})
    MERGE (l:Location {name: $location})
    MERGE (c)-[:IS_AT]->(p:Presence {chapter: $chapter})-[:LOCATION]->(l)

Character and Location stay separate MERGE statements because they are
identified by name alone.

VERIFIED, three checks: two pipeline runs produce ONE Presence where CREATE
produced two; a manual second location produces exactly ONE inconsistency row;
repeated runs do not inflate it.

### Trade-off accepted, and a limitation

MERGE collapses five sentences asserting the same presence into one node. The
fact survives; WHERE IT WAS ASSERTED does not. That matters twice: the gold
standard is built on paragraph locators, so a finding that cannot be traced to a
paragraph is half a finding; and the deferred sentence_index fix for the journey
problem needs position, which a merged Presence has discarded.

A cheap version keeps both: merge on character/location/chapter and accumulate
paragraph indices as a list property (ON CREATE SET / ON MATCH SET). Deferred
until the corpus loader supplies paragraph indices. Logged as a limitation.

store_character_age has the same CREATE pattern and the same latent bug, with a
different merge key: two DIFFERENT ages in one chapter are the inconsistency, so
the key must include age. Nothing calls it yet.

### Method note

Two empty results looked like success. The positive control is what found the
bug. Worth stating in the testing chapter: absence of output is not evidence of
correctness, and a detection system needs its detectors proven to fire, not just
proven not to crash.

## Detection metric decided: the three-way split (22 Sep)

The audit's first implementation decided whether a registry name had been
detected by comparing the registry key to ent.text with EXACT STRING EQUALITY.
That is wrong in a way that would have inflated the headline number.

spaCy produces spans like "Malcolm's", "Alpha Malcolm Ravensworth" and
"Knowing Elior". Under exact matching, a name spaCy DID find, but with
different boundaries, counts as NOT DETECTED. That merges two failure modes
this project has kept separate since 14 Aug: non-detection (spaCy never
emitted an entity there) and boundary error (it did, with the wrong span).

Four options were considered.

EXACT ONLY. Strictest. Has a stronger argument than simplicity: the system
keys identity on exact strings (MERGE (c:Character {name: $name})), so a
boundary error does not produce a near-miss, it produces a DIFFERENT NODE.
From the artefact's point of view "Alpha Malcolm Ravensworth" is not a slightly
wrong detection of Malcolm, it is a character who does not exist. Against: it
reports boundary errors as non-detection and collapses the taxonomy.

CONTAINMENT. Detected if the occurrence falls inside any span. Preserves the
taxonomy, but generous: "Elior" inside "Knowing Elior" counts as detected
though that span is wrong in exactly the way that breaks the MERGE above.

ANY OVERLAP. Too loose to carry information; almost nothing fails it. Rejected.

DOWNSTREAM EFFECT. Detected if the occurrence reaches resolved_map correctly
typed. Measures what matters for the artefact, but confounds NER performance
with registry coverage and with SPACY_TO_SCHEMA, so a metric that MOVES WHEN
YOU EDIT registry.json is not measuring RQ1. Rejected for RQ1; kept as a
separate end-to-end coverage figure for the evaluation chapter, explicitly
labelled as not an NER measurement.

DECIDED: report THREE categories per occurrence rather than two.
[CORRECTED 22 Sep: implemented as FOUR — PARTIAL added. See the CG-22 audit
results entry at the end of this log.]

    EXACT      an entity span equals the occurrence exactly
    CONTAINED  the occurrence falls inside a span, boundaries differ
    ABSENT     no entity span covers it at all

ABSENT is the non-detection figure and the headline number for RQ1. It is the
one the registry cannot fix and the one CG-19 exists to address. CONTAINED is
the boundary-error rate and gets its own line.

Why this rather than picking one: computing containment gives exact for free,
so it costs nothing; a reader can collapse the categories whichever way they
prefer, so no judgement call needs defending in the viva; and it preserves the
misclassification / non-detection / boundary-error taxonomy rather than quietly
merging two of its three branches.

Also corrected in the same pass: the audit documented per-occurrence counting
but computed buckets over SETS OF REGISTRY KEYS, so Elior occurring 62 times
and detected 12 times contributed 1. The structural reason is that
resolve_entity_types returns text, label and resolved_type but no character
offsets, so span comparison is impossible through it. Fix: iterate doc.ents
directly for the span work and keep resolve_entity_types for the type analysis.

## Side-effect of adding ORG to SPACY_TO_SCHEMA (22 Sep)

Adding "ORG": "Organisation" was correct in isolation and has a cross-cutting
consequence worth recording before the numbers are read.

On the 18 Sep run, spaCy's ORG label held TWENTY mentions and NOT ONE
organisation: Alric 8, Arseny 5, Eli 2, Talia 1, plus fragments like "Knowing
Elior". Every one a character or part of one.

Previously those resolved to None and were dropped. Now they resolve to
Organisation. Any ORG-labelled entity with no registry entry is now confidently
typed as an organisation and wrong.

It does NOT affect pairing, which filters on Character and Location. It DOES
affect the resolved-type distribution. So the registry's role changes shape:
it is no longer only rescuing entities that would have been dropped, it is now
also preventing entities from being actively mistyped. Worth saying in the
write-up, because it strengthens rather than weakens the registry argument.

## Method note on the side-chat split (22 Sep)

Build work moved to separate chats, with planning and anything touching the
schema, registry, corpus, gold standard or measurement method staying in one
place. The boundary is NOT "small versus large": wiring detection in looked
like three lines and exposed that the pipeline had never touched the corpus,
and CREATE-to-MERGE looked like one line and was a schema decision affecting
the precision denominator.

Both problems found in the audit review were exactly the kind the rule exists
to catch, and neither was escalated. The boundary is right; enforcing it needs
the reviewing to actually happen rather than the rule being stated.

## CG-22 audit results — corpus_ch1-2_v2, 5,480 words (22 Sep)

First audit run against the frozen dev corpus with the rebuilt registry. These
figures SUPERSEDE the 18 Sep run entirely and are NOT comparable to it: the
corpus changed, the registry changed, and nlp() now runs per paragraph rather
than per chapter. Development-set figures on an unfinished corpus, not final
results. 502 rows written to audit_report.csv.

### 1. Entities emitted by spaCy — 258 total

    PERSON 83   ORG 58   CARDINAL 37   DATE 29   GPE 28   TIME 5
    WORK_OF_ART 4   NORP 3   PRODUCT 3   LOC 2   ORDINAL 2   EVENT 2
    MONEY 1   QUANTITY 1

### 2. Resolved types — 258

    Character 144   None 84   Organisation 18   Location 12

### 3. Registry overrides

AGREEMENTS 73: PERSON→Character 64, GPE→Location 5, ORG→Organisation 4.

CORRECTIONS 86: ORG→Character 47, GPE→Character 22, PERSON→Organisation 7,
PERSON→Location 5, LOC→Character 2, PRODUCT→Character 2, PRODUCT→Location 1.

The registry CORRECTS MORE THAN IT CONFIRMS — 86 against 73. ORG→Character
alone (47) is the largest single category, which is the ORG side-effect noted
above showing up in the numbers: without the registry those 47 would now be
confidently typed as organisations rather than quietly dropped.

### 4. Coverage — 244 registry-key occurrences found in the corpus

    EXACT      158  (65%)
    CONTAINED    8  (3%)
    PARTIAL      1  (0%)
    ABSENT      77  (32%)

Bucket (a), in registry but not in corpus: 60 keys — expected, the registry is
bible-scoped and the corpus is two chapters.
Bucket (d), in doc.ents but not in registry: 66 texts.

### THE HEADLINE NUMBER IS NOT 32%

ELIOR ACCOUNTS FOR 57 OF THE 77 ABSENT OCCURRENCES — 74% of all
non-detection in the corpus sits on ONE NAME. Elior: occ=62, exact=4,
contained=1, absent=57. Exact rate 6%, coverage 8%.

Excluding Elior, ABSENT falls to roughly 20 of 182 occurrences, about 11%.

This is a far sharper finding than a flat 32% and it changes what RQ1 can
claim. Non-detection in this corpus is NOT a broad degradation across invented
names; it is CONCENTRATED, and the distribution is the result, not the mean.
The next worst are Marek (occ=7, absent=5), Ren (occ=5, absent=3) and Ric
(occ=3, absent=3) — all short forms, all low-frequency.

### Invented names are NOT uniformly hard to detect

    Alric      occ=33  exact=32  absent=1
    Oren       occ=22  exact=18  absent=2
    Talia      11/11   Kasev  9/9   Arseny  6/6   Eli  5/5

Alric and Oren are invented names of similar shape and length to Elior and
are detected near-perfectly. A simple morphological explanation — "spaCy fails
on invented names" — does not survive this. Whatever is happening to Elior is
not a property of the name class.

### The location finding is sharper than it was

18 Sep recorded "zero correctly identified locations". The span data refines
that considerably:

    Blackmere   6/6 EXACT   — labelled PERSON every time (5 PERSON, 1 PRODUCT)
    Hollowmere  similar pattern
[CORRECTED 23 Sep: the Hollowmere line is wrong. Hollowmere is an Organisation,
not a location, so it does not belong in a location finding at all. It occurs
twice and spaCy detects both. See the CG-23 entry.]

Invented locations are DETECTED RELIABLY AND CLASSIFIED WRONGLY. That is a
misclassification result, not a non-detection result, and it is the precise
claim the registry answers. The previous phrasing conflated the two.

### The real-world control holds

    New York  4/4 EXACT, correctly GPE
    Vienna    1/1 EXACT, correctly GPE

Real places in the same prose, same sentences, same model, detected and typed
correctly. This is the natural control group: the failures are not a property
of the text or the pipeline, they are a property of the invented names.

### Empirical support for the Event type (CG-12)

"the War of Two Monarchs" was detected as EVENT twice. The Event node type was
proposed from the schema side; this is corpus evidence that the model already
emits the label and the information is being discarded. "Lycans" as NORP is a
second type gap of the same kind.

### Known limitation accepted: bucket (d)

Bucket (d) — texts in doc.ents with no registry entry — still uses exact
string comparison, so it does not exclude spans that overlap a registry-key
occurrence. Its 66 entries therefore contain the predicted boundary noise:
"Knowing Elior", "Alpha Malcolm Ravensworth", "Seems Oren's" alongside genuine
non-registry entities ("Ahem", "bush", "Chelsea", "grey jeans").

The cheap fix is to exclude entity spans overlapping any registry-key
occurrence, since both span sets are already computed per paragraph. NOT DOING
IT. Bucket (d) is diagnostic, not a reported metric — the reported figures come
from the four-way span classification, which is unaffected. Recorded as a known
limitation with nine days to submission.

### Correction to the three-way decision recorded above

The entry above records DECIDED: three categories. The implementation is
FOUR: PARTIAL was added during the build because the three-way spec put spans
NARROWER than the occurrence into ABSENT — "Hollowmere" detected where the
registry key is "Hollowmere pack" is a boundary error, not a non-detection, and
the three-way scheme would have inflated the headline figure. PARTIAL fired
once in this run, so the correction changes the result by a single occurrence,
but the spec was wrong and the taxonomy is now complete: EXACT, CONTAINED and
PARTIAL are all detections with differing boundaries; ABSENT alone means spaCy
emitted nothing.
## Write-up log integrity — fourth loss event (22 Sep)

Recorded because it has now happened four times and the cause is finally clear.

Before this entry was written the file on disk had REVERTED: all five 22 Sep
entries were gone and the 21 Sep entry had changed back to its longer form,
with LF line endings replaced by CRLF. CRLF is the signature of a git checkout
under core.autocrlf, so the working-tree version was discarded by a BRANCH
OPERATION, not by a failed write. The 22 Sep entries had never been committed.

Separately, the working-tree version that was lost contained a CONDENSED
rewrite of the 21 Sep entry that had itself silently dropped four subsections,
including the Event gap argument — the sharpest RQ2/RQ3 point in the log. Both
versions were merged by hand rather than one overwriting the other.

RULE ADOPTED: commit the write-up log before any branch operation, and verify
the byte count on disk after every write. An uncommitted log is not saved, it
is staged for deletion by the next checkout.
## CG-23: pipeline over the corpus, and what it actually showed (23 Sep)

pipeline.py processed the manuscript for the first time. Everything before this
ran on one hardcoded sentence.

### The run

148 paragraphs of corpus_ch1-2_v2, nlp() per paragraph, normalise() before
nlp() so the pipeline and audit.py see identical text. clear_database once
before the loop, detection once after.

    Processed 148 paragraphs, stored 4 pairs

    Character 4    Location 2    Presence 4
    IS_AT 4        LOCATION 4

FOUR PAIRS FROM 5,480 WORDS. One Presence per pair, no duplicates, which
independently confirms the CG-11 CREATE-to-MERGE fix is holding under real
volume.

Both detection queries returned empty. Age is empty because nothing calls
store_character_age; that is CG-14 and expected.

THE LOCATION RESULT MUST BE STATED PRECISELY. The query looks for one character
attached to two Presences in the same chapter. No character in this graph has
two. So the empty result is NOT evidence that the manuscript is consistent. It
is evidence that THE GRAPH IS TOO SPARSE TO EXPRESS A CONTRADICTION. Those are
different claims and only the second is true. Writing "no inconsistencies
found" would be a misreport.

### The funnel (src/funnel.py, diagnostic, no Neo4j)

    148 paragraphs, 439 sentences, 258 entities

    Resolved types   Character 144   None 84   Organisation 18   Location 12

    Distinct Location names    4      Blackmere 6, New York 4, Trail 1, Vienna 1
    Distinct Character names  35      Alric 32, Oren 18, Talia 11, Roisen 9, ...

    sentences                439
    with a Character         114   (26%)
    with a Location           12   (2.7%)
    with BOTH                  3

    Pairs: ch2 Oren->Blackmere, Kasev->New York, Arsen->Blackmere,
           Alric->Blackmere

THE BOTTLENECK IS NOT THE PAIRING RULE. Sentences containing a Location (12)
equals total Location resolutions (12), so every location mention sits alone in
its sentence. The ceiling on pairs is twelve whatever the pairing rule is.
Loosening sentence-level co-occurrence to paragraph level reaches perhaps ten
pairs and costs precision. It cannot fix this.

### Verified against audit_report_ch1-2_v2.csv

Of the TEN Location-typed registry keys, only FOUR occur in chapters 1 and 2:

    key              occ   EXACT  CONTAINED  PARTIAL  ABSENT
    Blackmere          6       6          0        0       0
    New York           4       4          0        0       0
    New Jersey         1       0          1        0       0
    Vienna             1       1          0        0       0
    Asheville          0       -          -        -       -
    Demon Mountain     0       -          -        -       -
    Hudson Valley      0       -          -        -       -
    Kaldon             0       -          -        -       -
    Kedmaon            0       -          -        -       -
    Thornhaven         0       -          -        -       -

EVERY LOCATION NAME PRESENT IN THE CORPUS WAS DETECTED. Eleven of twelve
occurrences EXACT, one CONTAINED, ZERO ABSENT. The six with no occurrences are
bucket (a), bible-scoped keys whose scenes are unwritten, not detection
failures.

So spaCy's non-detection is NOT the location bottleneck. The manuscript names
places twelve times in 5,480 words and two of the four names are real-world.
The scarcity is a property of the PROSE, not of the model.

What the registry does is still visible and the contrast is clean:

    Blackmere        6/6 detected, NEVER ONCE GPE (5 PERSON, 1 PRODUCT)
                     reaches the graph only because the registry overrides it
    New York, Vienna always GPE, correct without the registry

That is the invented-versus-real result with a matched control in one table.

### CH1 P35 IS A DOUBLE FAILURE IN ONE PARAGRAPH

spaCy emitted "New Jersey Sightings" as ORG, swallowing the real place name
(this is the CONTAINED row above). In the same paragraph it emitted "Trail" as
GPE, which SPACY_TO_SCHEMA turned into a Location. So one paragraph LOSES a
real location and INVENTS a false one. "Trail" is the noise entry in the funnel
output. Worth quoting in the evaluation: the two error modes are not
independent, they co-occur.

### Registry-key occurrences by type

    Character 220    Organisation 12    Location 12

Ninety percent of what the registry does in this corpus is character names.

### CORRECTIONS TO MY OWN READING OF 22 SEP

Three claims made yesterday and repeated in this log were wrong. Recorded here
rather than quietly fixed.

1. "Six of ten Location keys are invisible to the pipeline." WRONG. They are
   absent from the text, not invisible to it. Zero occurrences each.

2. "Hollowmere is lost to a boundary mismatch between the span spaCy emits and
   the registry key 'Hollowmere pack'." WRONG twice. spaCy detects Hollowmere
   both times it occurs (ch2 p11 as PERSON, ch2 p60 as ORG), and the registry
   types it Organisation deliberately. HOLLOWMERE IS A PACK, NOT A PLACE: a
   body of individuals and families, per the world-building bible. The registry
   is correct and there is no bug.

3. The speculation that a flat name-to-type map cannot express a name denoting
   both a place and the group occupying it was an invented problem. It does not
   arise here.

### THE REGISTRY IS NOT IN THE STATE THIS LOG CLAIMS

Verified by direct lookup, 23 Sep:

    lookup('Kerenath')       -> 'Organisation'
    lookup('Oren Kerenath')  -> None
    lookup('Ravensworths')   -> 'Character'

    Counter: Character 75, Organisation 18, Location 10   TOTAL 103

NONE of the three registry edits recorded against 22 Sep are in the file. The
totals match the 21 Sep rebuild state exactly, untouched. The 21 Sep entry
above claims all three and states 104 entries; commit 9386dd4's message claims
two of them.

Traced through git the same day:

    9386dd4^  registry.json    19 entries (Character 16, Location 3)
    9386dd4   registry.json   103 entries (Character 75, Organisation 18,
                              Location 10), Kerenath 'Organisation',
                              Oren Kerenath absent, Ravensworths 'Character'

NOT A LOSS EVENT. What 9386dd4 captured was the 21 SEP REBUILD, 19 entries to
103, which had never been committed until then. The three 22 Sep retypes were
decided in conversation, recorded in this log in the past tense, and NEVER
TYPED INTO THE FILE. Nothing was overwritten. The work was never performed, and
the commit message repeated the log rather than describing its own diff.

This is a DIFFERENT FAILURE from the four write-up log losses and needs a
different guard. Those were a git problem, answered by committing before branch
operations. This is bookkeeping: agreement was mistaken for execution.

GUARD ADOPTED: a change is recorded as done only after it is VERIFIED IN THE
ARTEFACT IT CLAIMS TO CHANGE. For a registry edit that means a lookup; for
code, a run. Agreement in discussion is not evidence.

Incidental but worth keeping: the pre-rebuild registry was 19 entries,
Character 16 and Location 3. That is the baseline the 18 Sep drift finding
measured against, now recoverable from git rather than from memory.

STILL OUTSTANDING: the three retypes are unapplied. Before applying them they
need re-checking against the corpus rather than re-adopting from this log,
since the Hollowmere reasoning that once sat alongside them has been withdrawn.

Method note: the git check first returned nothing because it was run from src/,
where the pathspec src/registry.json matches nothing. GIT PATHSPECS RESOLVE
RELATIVE TO CWD.

### WHAT THIS DOES TO THE CG-19 ARGUMENT

The case made on 22 Sep was that registry injection had moved from
recommendation to dependency, because without it there was nothing in the graph
to detect. THE VERIFIED DATA DOES NOT SUPPORT THAT.

Total ABSENT across all registry keys is 77, of which 57 are "Elior", a
CHARACTER. Zero are locations. So injection would rescue character mentions and
would add NOT ONE location to the graph. It would also not fix the CONTAINED
cases: under filter_spans a PhraseMatcher hit on "New Jersey" loses to spaCy's
longer "New Jersey Sightings" span.

CG-19 is still worth building, but for a DIFFERENT REASON than the one given
yesterday. It is the INTERVENTION ARM FOR RQ1: 77 ABSENT occurrences before,
some number after, measured on the same corpus with the same instrument. That
is a real experimental result and it is a better contribution than the static
figure alone. What it is not is the thing that unblocks the evaluation.

THE THING THAT UNBLOCKS THE EVALUATION IS THE PLANTS. If chapters 1 and 2 name
places twelve times, corpus v3 has to name them deliberately and repeatedly in
the planted passages or the location query has nothing to compare. CG-16 is the
critical path, not CG-19.

### DECIDED (23 Sep)

Both CG-17 and CG-19 stay in scope. Ordering changed on the evidence above:

    1. Plants into corpus v3 (CG-16)
    2. CG-19 registry injection, as the RQ1 intervention arm
    3. CG-17 LLM integration

That ordering protects the evaluation chapter if the days run out. The
spaCy-only baseline in audit_report_ch1-2_v2.csv must survive in the write-up
alongside any hybrid figure, or the intervention has nothing to be measured
against.

Not doing: loosening pairing to paragraph level. The ceiling of twelve makes it
not worth the precision cost.
## CG-19 registry injection: built and measured (23 Sep)

PhraseMatcher over the 103 registry keys. Spans spaCy never emitted are added to
doc.ents labelled REGISTRY. Provenance rides on the LABEL rather than a custom
Span extension, because labels are stored on the tokens and survive
reassignment of doc.ents; span extension data is keyed on character offsets and
was not verifiable without a live spaCy to test against.

audit.py DELIBERATELY DOES NOT CALL IT. The audit is the spaCy-only baseline and
has to stay that way or the before arm is destroyed.

### Measured on corpus_ch1-2_v2

                                 BEFORE    AFTER
    entities in doc.ents            258      335
    sentences with a Character      114      171
    sentences with a Location        12       12
    sentences with BOTH               3        5
    pairs                             4        6
    distinct Location names           4        4
    distinct Character names         35       39

    resolved BEFORE  Character 144  Organisation 18  Location 12  None 84
    resolved AFTER   Character 220  Organisation 19  Location 12  None 84
    sources  AFTER   spacy 257      registry 78

78 spans injected, 13 distinct names, ZERO NOISE. Every one a genuine registry
proper noun: Elior 57, Marek 5, Ren 3, Ric 3, Oren 2, Urien, High Warlord,
Alric, Mira, Hollowmere pack, Kerenath, Count Halborn, Hector.

THE RECONCILIATION IS EXACT. The 22 Sep audit counted 77 ABSENT occurrences.
Injection added 78 spans: the 77 ABSENT plus one PARTIAL. Two instruments built
independently, agreeing to the unit. Strongest evidence so far that the audit
measures what it claims to.

One spaCy span was displaced, and it is the right one: "Hollowmere" (PERSON) at
ch2 p11 lost to the registry's longer "Hollowmere pack", which types correctly
as Organisation. A boundary error fixed as a side effect.

LOCATIONS UNCHANGED AT 12, exactly as predicted. Injection rescues characters.
It does not and cannot fix the location scarcity, because that was never a
detection failure.

## CG-23 closed: paragraph provenance (23 Sep)

Presence stays keyed on chapter. Paragraph index is carried as a
non-identifying p.paragraphs list, deduplicated by a CASE clause. Six pairs, six
Presence nodes, p.paragraphs populated on every row. All six triples distinct,
so the dedup branch of the CASE was never exercised and remains untested.

Both detection queries still return empty. NO CHARACTER IS AT TWO DIFFERENT
LOCATIONS IN ONE CHAPTER. The graph is richer after injection and still cannot
express a contradiction, because the prose does not contain one in the dimension
the query models.

## CG-17 LLM arm: first run, and it earned its place (23 Sep)

Anthropic API. Model, effort and token budget pinned in config.py, because a run
at one effort setting and a run at another are DIFFERENT EXPERIMENTS and the
write-up has to name which produced the numbers.

    LLM_MODEL       claude-sonnet-5
    LLM_EFFORT      medium
    LLM_MAX_TOKENS  32000

One call for both chapters, so cross-chapter contradictions are reachable. The
corpus is built by the same loader the pipeline uses, so the LLM and the graph
read identical text.

### THE DETERMINISM CLAIM WAS REVISED ON EVIDENCE

The plan was temperature=0 as the reproducibility control. CURRENT CLAUDE MODELS
DO NOT ACCEPT temperature AT ALL; the SDK removed it and the API rejects it. So
that control does not exist.

What remains is the control that mattered anyway: log every raw call, and run
the evaluation several times to REPORT THE SPREAD rather than a single figure.
This is a stronger position to defend, not a weaker one. It claims no
reproducibility the method cannot deliver.

Three failures before the first successful run, all recorded because each one is
a methodological fact and not just a bug:

1. temperature rejected outright.
2. TWO RUNS DIED ON BUDGET. stop_reason max_tokens, first at 4,096 then at
   16,000 output tokens, ENTIRELY THINKING, no text block. Adaptive thinking
   counts against max_tokens and "high" is the default effort on this model, so
   raising the budget alone changed nothing. Fixed by lowering effort to medium
   AND raising the budget to 32,000.
3. The SDK refuses a non-streaming call whose budget could exceed ten minutes.
   Switched to streaming with get_final_message().

Correction to my own reasoning, recorded: the thinking block was logged on the
argument that it would give the model's reasoning as RQ4 evidence. IT DOES NOT.
The block carries a 15,696-character signature and an EMPTY thinking field. The
reasoning is encrypted. Logging the blocks was still right, since it is what
diagnosed the budget failure, but the stated justification was wrong.

### Successful run: 11,865 in / 10,543 out, $0.13, stop_reason end_turn

TWO FINDINGS.

    [low]    number / within-chapter    ch1:p61, ch1:p68
             "over thirty" warriors against "the hundred and ten warriors here"

    [medium] other / cross-chapter      ch1:p73, ch2:p35
             Kasev and Dara "will leave in two days" against "have gone ahead
             and arrived in New York"

### Scored against the gold standard

    recall, naturally occurring      0 / 2     missed GS-01 and GS-07
    strict precision                 0 / 2
    correct rejections, legitimate   8 / 9

Finding 2 IS GS-08, same two locators. GS-08 is the row whose own notes read
"the most valuable precision row in the set... A checker that flags this scores
badly." It fired on the first run. The gold standard did its job.

Finding 1 was not in the gold standard and was adjudicated by the author: NOT a
contradiction. The thirty are the travelling party, five teams, with Dara, Kasev
and Marek contributing twenty between them and the remaining ten to Mira and
Johann. The hundred and ten are the garrison to be trained, whom Mira and Johann
stay behind to train. Added as GS-14, a set-binding precision row, companion to
GS-10 which binds intervals to subjects.

Eight legitimate rows correctly went unflagged, including the clothing change,
the two intervals bound to different subjects, and every alias row.

### BOTH FALSE POSITIVES ARE BINDING ERRORS, WHICH IS WHAT THE GRAPH FIXES

GS-08: read "will leave in two days" and "have gone ahead" as contradicting,
when the second is the first having happened. Binding across TIME.

GS-14: read two counts of different populations as two counts of one.
Binding across SETS.

In both the model had every word it needed and still attached a fact to the
wrong entity. A graph does not make that error, because
(c:Character)-[:IS_AT]->(p:Presence) binds by construction rather than by
inference.

THIS IS THE HYBRID ARGUMENT DEMONSTRATED RATHER THAN ASSERTED. The LLM reaches
contradictions the graph cannot model at all, and loses precision on exactly the
binding problems the graph solves structurally. Neither arm is sufficient.

It correctly rejected GS-10, which is also a binding case. So it is not
incapable at binding, it is UNRELIABLE at it. The inconsistency is the finding.

### A THIRD CATEGORY THE GOLD STANDARD DOES NOT YET HAVE

The author's ruling on GS-08 was that Eli "taking point" means acting as the
point of contact, not travelling with the advance team, AND THAT A READER COULD
PLAUSIBLY MAKE THE SAME MISREADING THE MODEL DID.

So the narrative is consistent, the flag is a false positive against ground
truth, and the text is genuinely ambiguous. For a tool whose user is the AUTHOR,
a flag saying "a reader may think Eli went with them" is useful output, not a
malfunction. GS-07 already distinguishes "a speaker can be wrong without the
narrative being wrong". This is its neighbour: THE TEXT CAN MISLEAD WITHOUT THE
NARRATIVE BEING WRONG.

DECIDED: report precision twice. Strict precision against ground truth, and
separately how many false positives identified a real ambiguity. Neither figure
is honest alone.

Consequence, deferred: if the "take point" line is revised, v2 is frozen so the
change lands in v3 with the plants and GS-08's locators move. It is also a live
instance of the retirement finding from GS-02 and GS-03, except THIS TIME THE
TOOL CAUSED THE REVISION rather than ordinary editing. Worth its own line in the
evaluation chapter.

### Known limitations of this run

One run, not three, so no variance figure yet. Effort fixed at medium; high at a
64,000 budget is a second condition worth running as a reasoning-budget versus
detection-quality comparison. Verification mode is not built: the graph flags
nothing on the natural corpus, so there is nothing to verify until the plants
land.
