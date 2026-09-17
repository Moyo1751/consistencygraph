# ConsistencyGraph

An author-side consistency checker for long-form fiction. It extracts named entities from manuscript prose with spaCy, resolves their types against a manually curated registry, and stores them as a Neo4j knowledge graph so that deterministic Cypher queries can surface contradictions the author has not noticed, such as a character appearing in two places within the same chapter.

Built as the software artefact for an MSc Computing (Software Engineering) dissertation.

## Prerequisites

- **Python 3.14.3 or later.**
- **A running Neo4j instance.** Developed against Neo4j 2026.02 via Neo4j Desktop, reachable on the default Bolt port `7687`.
- **The `en_core_web_sm` spaCy model.** Pinned in `requirements.txt`, so no separate download step is needed.

## Setup

Clone the repository, then from the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows PowerShell
# source venv/bin/activate            # macOS / Linux

pip install -r requirements.txt
```

Create a `.env` file in the repository root with your Neo4j connection details:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
```

`.env` is gitignored and must not be committed.

## Running

Start your Neo4j instance, then run the pipeline **from inside `src/`**:

```powershell
cd src
python pipeline.py
```

The working directory matters. The modules are flat rather than packaged, so `src/` needs to be on `sys.path`, which running from within it provides.

The pipeline prints the entities it found, their resolved types, the character-location pairs it derived, and a line per fact written to the graph.

> **Note:** `pipeline.py` calls `clear_database()` before storing, so every run wipes the connected database first.

## Project structure

```
consistencygraph/
  .env                  Neo4j credentials (not committed)
  requirements.txt      Pinned dependencies, including the spaCy model
  src/
    config.py           Environment loading, shared spaCy pipeline, Neo4j driver factory
    registry.py         Entity type resolution: manual registry lookup and spaCy label mapping
    extraction.py       Prose to structured entity data: NER, type resolution, sentence-level pairing
    storage.py          Writes characters, locations, ages and presences to the graph
    detection.py        Cypher queries that find contradictions in the stored graph
    pipeline.py         Entry point; orchestrates extraction, resolution and storage
    registry.json       Manually curated map of entity names to schema types
```

### Modules

| Module          | Responsibility                                                                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`     | Loads `.env`, creates the spaCy pipeline once, and exposes `get_driver()` for Neo4j connections. Nothing else creates either.                                       |
| `registry.py`   | Loads `registry.json` and owns type resolution: `lookup()` for manual overrides, `SPACY_TO_SCHEMA` for the default spaCy-label-to-schema mapping.                   |
| `extraction.py` | `extract()` for raw NER output, `resolve_entity_types()` to apply registry resolution, and `pair_character_locations()` to derive co-occurrence facts per sentence. |
| `storage.py`    | Graph writes: `store_character_age`, `store_character_location`, `store_pairs`, `clear_database`. Takes the driver as a parameter rather than importing it.         |
| `detection.py`  | Graph reads: `find_age_inconsistencies` and `find_location_inconsistencies`.                                                                                        |
| `pipeline.py`   | Orchestration only. Creates the driver, sequences the above, closes the driver.                                                                                     |

## Graph schema

| Node         | Properties       |
| ------------ | ---------------- |
| `Character`  | `name`           |
| `Location`   | `name`           |
| `Presence`   | `chapter`        |
| `AgeMention` | `age`, `chapter` |

| Relationship | From        | To           |
| ------------ | ----------- | ------------ |
| `IS_AT`      | `Character` | `Presence`   |
| `LOCATION`   | `Presence`  | `Location`   |
| `HAS_AGE`    | `Character` | `AgeMention` |

`Presence` exists as an intermediate node so that a character's location can be qualified by chapter, rather than asserting a single unqualified location per character.

## Entity type resolution

spaCy's general-domain NER model performs poorly on invented proper nouns, mislabelling fictional place names as organisations or people. `registry.json` is a manually curated mapping from manuscript entity names to schema types, consulted by `resolve_entity_types()`, which falls back to `SPACY_TO_SCHEMA` when a name is absent.

Both the raw spaCy `label` and the final `resolved_type` are retained on every resolved entity, so the two can be compared to quantify how often the registry corrects the model.

This design can only correct entities that spaCy **detected in the first place**. A manuscript name the model never surfaces as an entity is never passed to the registry at all, so it cannot be rescued. That is a known limitation of the current approach.

## Current status

The artefact is under active development for the dissertation. Known gaps:

- `pipeline.py` runs against a single hardcoded sample sentence. Chapter-file ingestion is not yet implemented.
- The pipeline stores facts but does not yet invoke the queries in `detection.py`.
- Only `Character` and `Location` resolve to schema types. Organisations are not yet modelled.
- Location pairing is sentence-scoped, so a character described as travelling between two places within one sentence produces a false positive.
- There is no automated test suite.
