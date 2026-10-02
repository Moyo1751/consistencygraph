# ConsistencyGraph

An author-side consistency checker for long-form fiction. It finds contradictions in a
manuscript, such as a character placed in two locations in the same chapter, or given two
different ages, and reports them to the author to judge.

It has two arms:

- **Graph arm.** spaCy finds named entities in the prose, a hand-made registry fixes their types,
  and the facts are stored in a Neo4j knowledge graph. Cypher queries then find the
  contradictions. Every result can be traced back to the chapter and paragraph that stated it.
- **LLM arm.** Claude reads the same text, either the whole corpus at once (detection) or one
  flagged passage at a time (verification), for the contradictions the graph has no structure for.

Built as the software artefact for an MSc Computing (Software Engineering) dissertation.
Repository: <https://github.com/Moyo1751/consistencygraph>

## Prerequisites

- **Python 3.14.3 or later.**
- **A running Neo4j instance.** Developed against Neo4j 2026.02 via Neo4j Desktop, on the
  default Bolt port `7687`.
- **An Anthropic API key**, for the LLM arm only.

The corpus is included, so the scripts run straight after cloning. They read
`corpus/corpus_ch1-4_v2.json`; to run on your own text, supply a JSON file in the same shape
(see `src/corpus.py`) and point `CORPUS_PATH` at it.

The spaCy model (`en_core_web_sm` 3.8.0) is pinned in `requirements.txt`, so there is no
separate download step.

## Setup

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows PowerShell
# source venv/bin/activate            # macOS / Linux

pip install -r requirements.txt
```

Create a `.env` file in the repository root:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
ANTHROPIC_API_KEY=your-key-here
```

`.env` is gitignored and must not be committed.

## Running

The modules are flat rather than packaged, so run everything **from inside `src/`**:

```powershell
cd src
```

| Command | What it does | Needs |
|---|---|---|
| `python pipeline.py` | Graph arm, end to end: loads the corpus, extracts and stores character-location pairs and ages, then runs both detection queries and prints the results | Neo4j |
| `python control_age.py` | Positive and negative control for the age path (expects 1 inconsistency, then 0) | Neo4j |
| `python audit.py` | spaCy-only audit of the corpus against the registry; writes `audit_report.csv` | Neither |
| `python funnel.py` | Counts entities, sentences and pairs before and after registry injection | Neither |
| `python llm.py` | LLM detection: the whole corpus in one call | API key |
| `python verify.py` | LLM verification: each held-out gold standard row in turn, with a confusion count at the end | API key |

> **Note:** `pipeline.py` and `control_age.py` call `clear_database()` first, so every run
> wipes the connected database.

Every LLM call is saved in full to `llm_runs/` (prompt, raw response, token counts), so a
result can be checked against what the model actually returned.

## How the graph arm works

1. **Load.** `corpus.py` reads the frozen corpus as numbered paragraphs and turns curly quotes
   into straight ones, so text matches the registry and the gold standard.
2. **Find entities.** spaCy's `en_core_web_sm` model tags names in each paragraph.
3. **Inject.** `inject_registry_entities` adds registry names spaCy missed. spaCy is a
   general-domain model and often misses or mislabels invented names.
4. **Resolve types.** `resolve_entity_types` uses the registry type if the name is listed,
   otherwise maps spaCy's label (`PERSON`, `GPE`, `ORG`).
5. **Extract facts.** A character and a location named in the same sentence become a pair. An
   age in a sentence that names a character is bound to that character ("N years old",
   "aged N", "N-year-old", "turned N", in digits or words).
6. **Store.** Facts are written to Neo4j (see [SCHEMA.md](SCHEMA.md)).
7. **Detect.** Two Cypher queries report a character in two locations in one chapter, and a
   character with different ages in different chapters.

## Project structure

```
consistencygraph/
  .env                      Neo4j and Anthropic credentials (not committed)
  requirements.txt          Pinned dependencies, including the spaCy model
  README.md
  SCHEMA.md                 Graph schema and the reasons for it
  Write up log.md           Development log
  corpus/
    corpus_ch1-4_v2.json      Held-out run corpus (chapters 1 to 4); what the scripts read
    corpus_ch1-2_v2.json      Development snapshots (chapters 1 and 2)
    corpus_ch1-2_v3.json
    *.txt                     Readable copies, paragraphs tagged [chN:pM] as in the gold standard
    corpus_gold_standard.csv  Gold standard every result is scored against
  llm_runs/                 Raw record of every LLM call
  src/
    config.py               .env loading, shared spaCy model, Neo4j driver, LLM client and settings
    corpus.py               Loads the frozen corpus as numbered paragraphs
    registry.py             Registry lookup and the spaCy label to schema type map
    registry.json           Hand-made map of 117 names to schema types
    extraction.py           Injection, type resolution, location pairs and ages
    storage.py              Graph writes
    detection.py            Graph reads: the two detection queries
    pipeline.py             Graph arm entry point
    control_age.py          Age path controls
    audit.py                spaCy-only audit against the registry
    funnel.py               Before and after injection counts
    llm.py                  LLM detection mode
    verify.py               LLM verification mode
```

### Modules

| Module | Responsibility |
|---|---|
| `config.py` | Loads `.env`, creates the spaCy pipeline once, exposes `get_driver()` and `get_llm_client()`, and pins the model settings (`claude-sonnet-5`, effort `medium`, 32,000-token budget). |
| `corpus.py` | `CORPUS_PATH`, `load_paragraphs()` and `normalise()`. Pinned to one frozen snapshot so every reported run names the text it read. |
| `registry.py` | Loads `registry.json`; `lookup()` for the manual type, `SPACY_TO_SCHEMA` as the fallback. |
| `extraction.py` | `inject_registry_entities()`, `resolve_entity_types()`, `pair_character_locations()`, `extract_ages()`, plus `extract()` for raw NER output. |
| `storage.py` | `clear_database`, `store_pairs`, `store_ages` and the single-fact writers. Takes the driver as a parameter. `store_organisation` and `store_membership` exist but are not called. |
| `detection.py` | `find_location_inconsistencies` and `find_age_inconsistencies`. |
| `pipeline.py` | Orchestration only: load, extract, store, detect, print. |
| `llm.py` | Detection prompt, `detect_inconsistencies()`, and `_log_run()` for saving each call. |
| `verify.py` | Verification prompt and `verify_candidate()`. Sends only the type, the entities and the passages, never the gold standard's own description. |

## Evaluation

Results are scored against `corpus/corpus_gold_standard.csv`. Chapters 1 and 2 are the
development split, used while building; chapters 3 and 4 are held out. The full method and
results are in the dissertation.

## Known limitations

- Pairing is sentence-scoped, so a character who travels between two places within a chapter is
  flagged (the journey problem).
- Ages are only compared across chapters, and any change of age is flagged, including a character
  who has legitimately aged.
- There is no `Event` node, so there is no timeline query. Timeline cases are left to the LLM arm.
- Entities are identified by their exact name, so one character written two ways becomes two
  nodes.
- Organisations are typed but not stored.
- Injection only rescues names spaCy missed entirely. A registry name inside a longer spaCy entity
  stays lost.
- There is no automated test suite; `control_age.py` is the only control.

See section 5 of [SCHEMA.md](SCHEMA.md) for the full list.
