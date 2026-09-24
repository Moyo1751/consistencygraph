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
## CG-17 verification arm, and the result the whole project was for (23 Sep)

Verification was going to wait for plants, on the reasoning that the graph flags
nothing so there is nothing to verify. WRONG. The gold standard IS a candidate
set: 11 live rows, each with locators, anchors and an author-adjudicated ground
truth. No plants and no graph required.

### Method

One call per row. The verifier receives THE TYPE, THE ENTITIES AND THE PASSAGES,
which is what the graph would hand it. It NEVER receives the gold standard's own
"what the contradiction is" column, because for several rows that column
telegraphs the answer; GS-08's reads "by the same speaker to a different
audience", which is most of the reasoning.

Ground truth is taken mechanically from the Origin column: naturally occurring
means a real contradiction, legitimate means not. No judgement applied at
scoring time.

Same model, effort and budget as the detection run. Every call logged to
llm_runs/ under its row id.

### Scorecard

    true positives    0     false negatives  2     GS-01, GS-07
    true negatives    8     false positives  1     GS-05
    unparseable       0

### GS-08 FLIPPED, AND THAT IS THE ARGUMENT

Detection, reading the whole corpus, called GS-08 a CONTRADICTION at medium
confidence. A false positive.

Verification, handed the SAME TWO PASSAGES plus a type label, called it
CONSISTENT at HIGH confidence:

    "The passages describe sequential events, Kasev and Dara depart first,
     then later arrive in New York ahead of the others, which is a natural
     progression, not a contradiction."

Same model. Same text. Opposite and correct answer. The only difference is that
the candidate arrived PRE-BOUND instead of having to be found.

This is a controlled comparison inside one model, not a comparison between
systems, and it is stronger evidence for the hybrid than either arm's raw score.
The architecture is not "LLM plus graph because two is better than one". It is
"the LLM's failure mode is binding, and binding is what the graph does".

### ALL THREE ERRORS HAVE ONE CAUSE

GS-01 (missed): "the passages never mention Ciaran, Roisen, or Elior, so no
contradiction involving those named individuals is present." It is RIGHT. The
two paragraphs do not name them. The contradiction exists only if you know who
the three generations are, which lives in the family graph.

GS-07 (missed): could not resolve who "he" refers to.

GS-05 (false positive): bound "she" in ch1 p21 to Elior, the nearest named
antecedent, and concluded Elior changes gender.

Every failure is ENTITY RESOLUTION THE PASSAGES DO NOT CONTAIN. That is exactly
what a graph supplies and a passage does not. Three independent failures, one
cause, and it is the cause the architecture predicts.

### THE GS-05 FALSE POSITIVE IS PARTLY AN ARTEFACT OF MY TEST

Checked p21 against p20 and p22. The paragraph is about Roisen throughout; she is
named in p22. The model saw ...," thought Elior. She pulled up the long
sleeves... and bound the pronoun to Elior. The prose is correct.

But the test handed it p21 IN ISOLATION, because candidates were built from the
gold standard's anchor locators alone. With the neighbours attached the pronoun
is unambiguous. So this false positive measures my context window, not the
architecture.

SPECIFICATION DERIVED FROM THIS: a hybrid candidate must carry resolved entities
AND adjacent paragraphs, not only the anchor passages. That is not a design
guess, it is three failures with a shared cause pointing at the same fix.

Craft note, not an error: the name "Elior" sits between "her desk" and "She
pulled up", so the pronoun chain is briefly ambiguous around an intervening
name. Same family as the "take point" case. Author's call; no change recommended.

### Detection versus verification, same corpus, same day

                        DETECTION        VERIFICATION
    input               whole corpus     2 passages + type
    recall (natural)    0 / 2            0 / 2
    precision           0 / 2            0 / 1
    correct rejections  8 / 9            8 / 9
    GS-08               CONTRADICTION    CONSISTENT (high)

NEITHER ARM DETECTED EITHER NATURALLY OCCURRING CONTRADICTION. Both missed GS-01
and GS-07, for the same reason, in both modes. That negative result is consistent
across two independent experiments and should be reported as prominently as the
flip.

### Known limitations

One run per row, no variance figure. Effort fixed at medium. Candidates built
from anchors only, which is the GS-05 artefact above. Ground truth for GS-07 is
itself an author judgement about an ambiguous passage, so counting it as a
contradiction the tool should catch is defensible but not neutral.
## CG-14 age extraction, and a correction it forced (23 Sep)

Kept in scope on the expectation that chapters 3 and 4 will contain ages, not
because chapters 1 and 2 do. They contain NONE: no "years old", no "aged N", no
"N-year-old", no "age of", not even the word "age". One "centuries", one
"Ravensworth birthday".

### The rule, written narrow on purpose

Four surface forms and nothing inferred:

    "<N> years old"    "aged <N>"    "<N>-year-old"    "turned <N>"

Digits and written numbers both, since a world on a millennia scale will say
"four hundred years old" long before it says "400". No birthdays, no date
arithmetic, no inference of any kind.

REGEX, NOT spaCy. spaCy labels "four hundred years old" as DATE and a bare
number as CARDINAL, and neither label tells you it is an age. A narrow regex is
honest about what the rule actually is, and it is the rule that gets written up.

Binding follows pair_character_locations exactly: the character and the age must
share a sentence. Deliberately the same rule, so both arms fail the same way and
the write-up has ONE limitation to explain rather than two.

Tested against eleven strings before wiring, including the three negatives that
matter: "over thirty men and women", "the hundred and ten warriors here" and
"years old news" all correctly yield nothing.

### Positive AND negative control, because the corpus proves nothing

Chapters 1 and 2 cannot exercise this code, so a corpus run is not evidence.
src/control_age.py holds two hand-written pairs:

    CONFLICTING  Roisen 400 in ch1, Roisen 300 in ch2   ->  1 inconsistency
    CONSISTENT   Roisen 400 in ch1, Roisen 400 in ch2   ->  0 inconsistencies

Both pass. The negative half is the important one: it catches a query that
flags everything, which a positive control alone cannot.

Corpus run afterwards: 148 paragraphs, 6 pairs, 0 ages, both queries empty.
EXPECTED, not a failure.

### THE CONTROL STORED 3 AGES, NOT 2, AND THAT IS THE FINDING

Sentence two names two characters: "By then ROISEN was three hundred years old,
or so ALRIC claimed." The binding rule attaches the age to every character in
the sentence, so it produced Roisen=300 AND ALRIC=300. Alric is recorded as
three hundred years old on the strength of a sentence that says nothing of the
sort.

It caused no false detection here only because Alric has one age and nothing to
conflict with. On a fuller corpus it would.

### CORRECTION TO THE CG-17 ENTRY WRITTEN EARLIER TONIGHT

That entry says:

    "A graph does not make that error, because
     (c:Character)-[:IS_AT]->(p:Presence) binds by construction rather than by
     inference."

TOO STRONG, AND THIS CONTROL DISPROVES IT. The graph binds by construction, but
the binding is only as good as the EXTRACTION RULE that built it, and a
sentence-level cartesian product is a crude rule. pair_character_locations does
the same thing: the six corpus pairs include Alric and Arsen both placed at
Blackmere from the single sentence at ch2 p48.

The honest version of the hybrid argument is narrower and still worth making:
THE GRAPH MAKES BINDING EXPLICIT AND INSPECTABLE, which is why this failure is
visible at all, rather than immune to binding error. The LLM's binding
decisions are invisible and unauditable; the graph's are a row you can query.
That is the defensible claim.

### Decided

KEEP THE CARTESIAN RULE. Fixing ages alone would leave two different binding
rules to explain instead of one, and the location arm already ships this
behaviour. One stated limitation across both arms.

The schema now models an attribute the current corpus does not contain. That is
itself worth reporting: the age query existed since CG-14 was written, was dead
code until tonight, and meets real data for the first time in chapters 3 and 4.
## Registry retypes applied, and one reversed on evidence (24 Sep)

The three edits recorded as done on 22 Sep but never made to the file have now
been made, after re-checking each against the corpus rather than re-adopting
them from this log. The guard adopted yesterday says a change is recorded as
done only after it is verified in the artefact it claims to change; this is the
first application of it, and it caught a wrong decision.

### Ravensworth and Ravensworths to Organisation: CONFIRMED

Five occurrences, four collective:

    ch2 p6   "The Ravensworths are practically family"
    ch2 p55  "the Ravensworths' private airstrip"
    ch1 p14  "the Ravensworth birthday"
    ch2 p36  "the Ravensworth team on the ground"
    ch1 p14  "Alpha Malcolm Ravensworth"          <- the one surname use

Four of five denote the family or the pack. Retype stands. "Alpha Malcolm
Ravensworth" added as a Character key so the surname use is covered by a longer
key and never falls through to the collective one.

### Bare Kerenath to Character: REVERSED

The 22 Sep reasoning was "no bare organisational use exists in the corpus".
THE EVIDENCE SAYS THE OPPOSITE. Five occurrences:

    ch1 p3   "the Kerenath shipping company"      the company
    ch1 p3   "Kerenath Enterprises"               the company, existing key
    ch1 p7   "Arseny Kerenath"                    existing Character key
    ch1 p18  "Roisen Kedvara Kerenath"            existing Character key
    ch2 p23  "Oren Kerenath"                      NOT a key, so bare Kerenath fired

Every bare hit is either the company or a fragment of a longer personal name.
Adding "Oren Kerenath" as a key removes the last one under longest-match-wins,
leaving no bare surname use at all in chapters 1 and 2.

The bible agrees: Kerenath is the mother's house name, and the registry already
carries House Kerenath and Kerenath Enterprises as Organisations.

BARE KERENATH STAYS ORGANISATION. Recorded as a decision reversed on evidence,
not as a silent difference from what this log previously claimed.

### Registry now

    105 entries    Character 75    Organisation 20    Location 10

Verified by lookup, not by agreement. Pipeline re-run afterwards: 148
paragraphs, 6 pairs, 0 ages, both queries empty. Unchanged, as expected, since
none of these keys is a Location.

### What this says about the flat map

Three of the five Kerenath occurrences are only correctly typed because a
LONGER key exists to catch them. The registry does not resolve the ambiguity
between a house name and a surname; it sidesteps it by enumerating the longer
forms. That works while the forms are known and fails silently on any new one,
which is the same fragility recorded on 24 Jul for name variants, surfacing in
a third place.

## v3 frozen, both LLM arms balanced, and the corrections they forced (24 Sep, evening)

Second entry for 24 Sep. The morning entry covers the registry retypes. This one
covers everything from the v3 freeze onward: the corpus, the gold standard schema
change, the plants, both LLM arms at n=3, the funnel rewrite, and the corrections
owed. Every figure below was re-derived from the files on disk or from the logs
in llm_runs/, not carried over from discussion.

### Corpus v3 frozen

    corpus/corpus_ch1-2_v3.{docx,json,txt}, mirrored to Dissertation\corpus\
    150 paragraphs (84 ch1, 66 ch2, heading at index 0 in each)
    148 prose paragraphs after load_paragraphs skips the headings
    5,587 words in the snapshot, 5,583 as the audit counts them
    source_sha256 c0129f8feb837829...   derived_from v2
    changes_from_v2 embedded in the JSON, eleven entries
    src/corpus.py CORPUS_PATH -> v3

v2 is untouched. It is the only comparison point for anything measured before
today, and the v2 audit is the spaCy-only RQ1 baseline.

DO NOT RE-CUT v3 WITHOUT A VERY GOOD REASON. It would invalidate three detection
runs and six verification passes.

### Gold standard: truth separated from provenance

New column, Ground truth label, holding CONTRADICTION or CONSISTENT. Scoring reads
it directly. Truth used to be inferred from Origin, which silently scored every
Planted row as consistent the moment Origin gained a third value. ORIGIN IS NOW
PROVENANCE ONLY: Naturally occurring, Legitimate, Planted. A plant can be either
a contradiction or a consistent case, so the two are different facts and are
stored separately.

    20 rows, 18 live, 6 CONTRADICTION, 12 CONSISTENT

Rows planted or reclassified for v3: GS-15 to GS-20. GS-07's anchors moved with
the prose into v3; its mechanism is unchanged. All 18 live rows' anchor text is
present in v3, checked by loading every candidate through load_candidates().

The labels moved five times today as rows were adjudicated. Three of the five
moves made the tool look worse. That is reported as a strength: ground truth came
from author rulings, not from fitting the key to the results.

### Code

    verify.py      truth read from the Ground truth label column
                   code-fence strip before json.loads (GS-09 came back bare on
                   v2 and fenced on v3 from the same prompt, scored UNPARSEABLE)
    extraction.py  age regex: "and" removed from the number-word alternation and
                   allowed only as a connector, because "turned and started
                   walking" matched turned <N>
    funnel.py      rewritten to measure BEFORE and AFTER injection in one run,
                   one parse per paragraph (see below)

### Deterministic arm, identical on every run

    pipeline      148 paragraphs, 12 pairs, 2 ages
      Age         Malcolm 520 ch1 / 630 ch2          GS-16
      Location    Zelkarev Kaldon / Thornhaven ch1    GS-15
    control_age   positive 1 inconsistency, negative 0

    flags 2   true 2   precision 1.00   recall 2/6 = 0.33

control_age.py still earns its place: v3 states no character's age twice in
agreement, so it is the only negative case the age query has.

### LLM detection, three runs on v3

    run          findings  TP  FP              precision  recall  out tokens
    1 141050Z        2      1  1 (GS-18)          0.50     0.17     8,254
    2 164232Z        2      1  1 (GS-14)          0.50     0.17     8,022
    3 164756Z        3      2  1 (GS-18)          0.67     0.33     9,244
    pooled           7      4  3                  0.57     0.22

GS-16 found in all three runs, GS-19 in run 3 only. Detection never reads the gold
standard, so it rescores from the logs for free whenever labels move.

### LLM verification: three superseded passes, three balanced passes

The first three passes were UNBALANCED. They are kept in llm_runs/ and reported
as superseded, not deleted:

    pass A 141141Z   n=15   tp 1  fn 3  tn 11  fp 0   precision 1.00
    pass B 151205Z   n=15   tp 1  fn 3  tn  9  fp 2   precision 0.33
    pass C 151956Z   n=16   tp 1  fn 3  tn 12  fp 0   precision 1.00

GS-19 and GS-20 were never called in A to C, and GS-18 only in C.

Three fresh passes over all 18 live rows, run by me from the repo root:

    pass    TP  FN  TN  FP   precision  recall   F1    out tokens
    D        2   4  11   1     0.67      0.33   0.44     2,862
    E        3   3  11   1     0.75      0.50   0.60     2,726
    F        2   4  11   1     0.67      0.33   0.44     2,448
    pooled   7  11  33   3     0.70      0.39

Checked against the logs, not the console. Every call stop_reason end_turn, none
unparseable, model claude-sonnet-5 throughout. EVERY ROW'S PROMPT WAS
BYTE-IDENTICAL ACROSS ALL SIX PASSES (sha256 of the logged prompt), so the spread
is the model's own run-to-run variation and nothing else.

Verdict identical in all three balanced passes on 17 of 18 rows (GS-01 is the
exception). Confidence identical on 13 of 18.

REASON CHECK. All seven true positives in D to F cite the contradiction their row
records: GS-16 three times (520 against 630), GS-19 three times (Kaldon against
Vienna), GS-01 once (the p3 dates, after the re-scope below). Verdict and reason
agree on every hit, so the verdict-level table stands without a second column.

### Per contradiction row, all three arms

    row     graph                    detection   verification D-F
    GS-01   not modelled                0/3          1/3
    GS-07   not modelled                0/3          0/3
    GS-15   found every run             0/3          0/3
    GS-16   found every run             3/3          3/3
    GS-19   missed (binds to speaker)   1/3          3/3 high
    GS-20   missed (2nd place unnamed)  0/3          0/3

False positives on consistent rows:

    GS-05   detection 0/3   verification D-F 3/3 (medium, high, high)
    GS-14   detection 1/3   verification D-F 0/3
    GS-18   detection 2/3   verification D-F 0/3, all low confidence

### GS-15 AND GS-19 ARE MIRROR IMAGES

GS-15: the graph returns it on every run. NINE LLM CALLS HAVE SEEN IT, three
detection and six verification, and all nine called it consistent.

GS-19: the graph misses it, because the cartesian rule binds Kaldon to Arseny,
the speaker, and nothing places Roisen in Vienna as a graph fact. Verification
finds it three times out of three at high confidence.

The two arms fail on different rows for different reasons. Caveat that goes with
GS-19: verification was handed the gold standard's passages, so its recall is an
UPPER BOUND no graph-fed architecture can reach. In a pipeline where the graph
proposes candidates, verification would never see GS-19.

### DECIDED: THE LLM IS NOT A GATE ON THE GRAPH

The Chapter 4 plan said the LLM must not verify what the queries found, on
model-as-judge circularity grounds. That was written before the LLM arm existed.
GS-15 now proves it empirically: a pipeline where the graph proposes and the LLM
disposes would have filtered out the graph's only unique true positive.

RQ4 STAYS AN ABLATION. Arms independent, both scored against the external,
author-adjudicated gold standard. Verification is a second detection mode under a
narrower input condition, not a check on the queries. The 23 Sep line "binding is
what the graph does" survives as the explanation of why the arms fail
differently. It does not license wiring one into the other.

### CG-19 measured on v3: funnel BEFORE and AFTER

    Corpus: 148 paragraphs, 443 sentences

                                  BEFORE   AFTER
      entities in doc.ents           273     349
      resolved Character             145     221
      resolved Location               18      18
      resolved Organisation           23      23
      resolved None                   87      87
      distinct Location names          7       7
      distinct Character names        34      39
      sentences                      443     443
      with a Character               115     173
      with a Location                 17      17
      with BOTH                        7       9
      pairs                           10      12

    Pairs injection added: 2
      ch1 p66   Elior -> Blackmere
      ch2 p29   Elior -> Blackmere

76 spans injected (349 - 273), RECONCILING EXACTLY WITH THE v3 AUDIT'S 76 ABSENT
OCCURRENCES. Two independently built instruments agreeing to the unit, as on v2,
where 78 injected matched 77 ABSENT plus 1 PARTIAL.

Zero noise: Organisation, Location and None are identical in both columns. Every
injected span resolved to Character. Elior goes from 4 detections to 61 of 62
occurrences, which is where both new pairs come from.

LOCATIONS UNCHANGED AT 18. Injection rescues characters and cannot fix location
scarcity, because that was never a detection failure. Predicted on v2, holds on
v3.

Residual false positives that survive resolution, for the 4.3 limitations:
Chelsea (from "black Chelsea boots"), bush, Lily, bare "Alpha", and Trail from
ch1 p35, the same paragraph where spaCy swallowed New Jersey inside "New Jersey
Sightings". One paragraph loses a real location and invents a false one.

Calibration before committing: BEFORE 273 entities matches audit.py, BEFORE 10
pairs matches the old funnel, AFTER 12 pairs matches pipeline.py. audit.py stays
spaCy-only and untouched.

### Gold standard now tracked in git

The gold standard is now tracked in git; manuscript snapshots remain ignored. Its
labels changed five times on 24 September as rows were adjudicated, and from this
commit forward that history is in the repository rather than resting on the
Notes column alone. The change required corpus/* with a negation rather than
corpus/, because git will not re-include a file inside an excluded directory.

    .gitignore   corpus/*
                 !corpus/corpus_gold_standard.csv

Verified by reading .gitignore back off disk.

### AUTHOR RULINGS TODAY

GS-01, RE-SCOPED. The row claimed "passed through three generations" was
premature because Elior is only a proxy. THAT CLAIM IS WRONG. The company passed
from Ciaran, to Roisen and Kristopher, to Elior, which is three generations, and
verification passes D and F said so. The real error is in the same paragraph and
I had not seen it: founded 230 years ago, 150 years under Roisen, left to
Kristopher 80 years ago, passed to Elior 10 years ago. 150 + 70 + 10 = 230, so
Ciaran never ran the company he founded, and "over the past hundred and fifty
years" read literally overlaps Kristopher's eighty.

Pass E flagged exactly that. A NATURALLY OCCURRING CONTRADICTION THE AUTHOR DID
NOT KNOW ABOUT, SURFACED BY THE TOOL AND THEN ADJUDICATED. It counts as found only
from my ruling, under the guard in correction 1 below. It is a weak signal: one
verification pass in three, no detection run, and verification was handed the
passage rather than finding it.

Why re-scope the row rather than flip it to CONSISTENT and add a new one: the
verification question is whether the passages contradict, and they do, through
p3. Label, type, origin, locators and entities are unchanged, so every logged call
received exactly the passages the row now describes and nothing needs re-running.
The original wording is preserved in the row's Notes. The company dates get
reworked when the manuscript is next edited; v3 stays frozen.

GS-14. Twenty warriors travel: fourteen went ahead and six followed on the plane.
Supersedes the 23 Sep line "The thirty are the travelling party". The thirty are
the people in the training room at ch1 p61. Label unchanged, still CONSISTENT.

GS-19. The Vienna estate is Kaldon's Earth-side seat in canon, but the corpus never
says so. On the text alone "her study at Kaldon" contradicts the Vienna scene and
the label stands. The plant works only if Kaldon is read as the capital, and the
verifier had no access to canon, so it is a weaker plant than GS-15 or GS-16. NOT
EXPLAINED IN THE CORPUS: v3 is frozen, and stating it in the text would make "at
Kaldon" correct and dissolve the plant. Revisit when chapters 3 and 4 unfreeze
the text.

GS-20. Elior finds Talia and Yaela in the crossing room. Oren had already run off
to Vienna (ch1 p57). The contradiction binds to Talia and the label stands.

### CORRECTIONS

A change is recorded as done only after it is verified in the artefact it claims
to change. Each of these failed that test at some point today.

1. THE TWO "UNPROMPTED CATCHES" WERE WRONG. Claude twice claimed the tool had
   caught author errors I did not know about, and called GS-18 "the strongest
   single piece of evidence you have". GS-18 is not a contradiction; the manor is
   on the outskirts of Vienna. GS-19 is a plant. At the time of the claim the
   artefact had caught zero unknown errors. GUARD EXTENDED: a finding is a true
   positive only after the author has adjudicated it. (GS-01 above is the first
   finding to pass that guard.)

2. GS-18 WAS CALLED REPRODUCIBLE BEFORE THERE WAS A THIRD RUN: a catch on n=1,
   then on n=2. It is a reproducible FALSE POSITIVE, 2 of 3 detection runs.

3. A PROPER NOUN FROM A VOICE-TRANSCRIPTION ERROR WAS WRITTEN INTO GS-15's NOTES
   without checking the bible. Removed from every file; the row records the
   correction without naming it. It never reached the manuscript, the snapshot,
   the code or any logged model response.

4. device_commit_files REPORTED "WRITTEN" AND THE FILE DID NOT LAND, because the
   same staged path was reused. GS-18 was missing from disk during a verification
   run, which is why that run scored 15 rows and not 16. RULE: read every file
   back off disk after every write.

5. GS-19 WAS NEVER CALLED IN VERIFICATION PASSES A TO C, not only GS-20. The
   handover named GS-20 alone.

6. THE VARIANCE HEADLINE WAS MEASURED ON AN UNBALANCED DESIGN. Precision
   1.00 / 0.33 / 1.00 came from passes that never asked two of the six
   contradiction rows. Balanced, it is 0.67 / 0.75 / 0.67. The variance is real
   but smaller, and it lives at row level. An unbalanced design inflates
   precision by not asking the hard questions.

7. GS-05 WAS DESCRIBED AS A ONE-OFF FLIP IN PASS B. It is a false positive in 3 of
   3 balanced passes and 4 of 6 overall, from a byte-identical prompt. "13 of 15
   verdicts stable" was a small-sample reading.

8. PASS C WAS ORIGINALLY REPORTED AS fn 4 / tn 11, scored while GS-18 was still
   labelled CONTRADICTION. Under the final labels it is tp 1, fn 3, tn 12, fp 0.

9. THE funnel.py OMISSION OF inject_registry_entities WAS NEVER A DECISION. The only
   deliberate exclusion on record is audit.py's. Funnel was run in both states for
   the v2 CG-19 measurement and left in the BEFORE state, so the 10-against-12
   figure on v3 was correct by accident and would have broken silently the first
   time pipeline.py changed and funnel did not. Fixed, measured, committed.

10. GS-01 PASS E WAS FIRST REPORTED AS VERIFICATION CATCHING THE ROW'S NATURAL
    CONTRADICTION. Its reason was a different contradiction from the one the row
    then recorded. Resolved by the author ruling above, which found the row's
    recorded reason was the thing that was wrong.

11. GS-20's DESCRIPTION SAID ELIOR FINDS TALIA AND OREN. The text has Talia and
    Yaela. Corrected in the row. verify.py sends only the anchor paragraphs, p33
    and p37, so the model never saw p36, which names Yaela. Pass F's reason ("the
    two women could be Talia and Oren if Oren is a female name") comes from that
    missing paragraph, the same anchors-only artefact as GS-05 on 23 Sep.

12. THE FIRST WRITE OF THAT CORRECTION BROKE THE CSV. The new description contained
    a comma, the field was unquoted, and GS-20's label parsed as "WITH YAELA".
    Caught by parsing the read-back through load_candidates(); rewritten with the
    field quoted within minutes; no run read the broken file. A byte comparison
    alone would NOT have caught it, because the broken file was exactly what had
    been written. RULE EXTENDED: a CSV read-back is parsed through the loader, not
    only compared.

13. GS-14: the 23 Sep entry says "The thirty are the travelling party". Superseded
    by the ruling above: twenty travel. The handover repeated the thirty.

14. GS-15 AND GS-20 NOTES WERE OUT OF DATE ("3 of 3 verification runs", "never
    been called"). Dated UPDATE lines appended; the original text is kept.

### Open

- Company dates in ch1 p3 to rework when the manuscript is next edited.
- GS-19 to recheck when chapters 3 and 4 unfreeze the text.
- verify.py builds candidates from anchor paragraphs only. GS-05 and GS-20 both
  show the cost. The 23 Sep specification stands: candidates need adjacent
  paragraphs and resolved entities.
- Optional second condition never run: effort high at a 64,000 budget.
