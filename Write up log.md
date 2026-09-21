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
