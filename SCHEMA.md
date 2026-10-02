# ConsistencyGraph schema

The Neo4j graph written by `src/storage.py` and read by `src/detection.py`. Structure first,
then the reasons for it. Anything designed but not built is marked.

## 1. Nodes

The graph has two kinds of node. **Entities** are things in the story world, identified by
name. **Occurrences** are claims the text makes about an entity, identified by the path they
sit on.

| Label | Kind | Properties | Identified by | Written by | Status |
|---|---|---|---|---|---|
| `Character` | Entity | `name` | `name` | `store_character_location`, `store_character_age`, `store_membership` | Built |
| `Location` | Entity | `name` | `name` | `store_character_location` | Built |
| `Organisation` | Entity | `name` | `name` | `store_organisation`, `store_membership` | Functions exist; the pipeline does not call them |
| `Presence` | Occurrence | `chapter`, `paragraphs` | its path: character, chapter, location | `store_character_location` | Built |
| `AgeMention` | Occurrence | `age`, `chapter` | its path: character, age, chapter | `store_character_age` | Built |

`paragraphs` is a list of the paragraph numbers that state the presence. It is not part of
identity.

## 2. Relationships

| Type | From | To | Status |
|---|---|---|---|
| `IS_AT` | `Character` | `Presence` | Built |
| `LOCATION` | `Presence` | `Location` | Built |
| `HAS_AGE` | `Character` | `AgeMention` | Built |
| `MEMBER_OF` | `Character` | `Organisation` | Function exists; the pipeline does not call it |

## 3. How it fits together

```
(Character)-[:IS_AT]->(Presence {chapter, paragraphs})-[:LOCATION]->(Location)
(Character)-[:HAS_AGE]->(AgeMention {age, chapter})
(Character)-[:MEMBER_OF]->(Organisation)          not written by the pipeline
```

Example: "Zelkarev is in Thornhaven in chapter 1" becomes

```
(:Character {name: "Zelkarev"})-[:IS_AT]->(:Presence {chapter: 1, paragraphs: [...]})-[:LOCATION]->(:Location {name: "Thornhaven"})
```

If chapter 1 also puts him in Kaldon, he gets a second `Presence` for chapter 1, and the
location query reports the pair.

### Writes (`src/storage.py`)

```cypher
// presence: entities merged by name, the occurrence merged by its whole path
MERGE (c:Character {name: $name})
MERGE (l:Location {name: $location})
MERGE (c)-[:IS_AT]->(p:Presence {chapter: $chapter})-[:LOCATION]->(l)
SET p.paragraphs = CASE
    WHEN $paragraph IN coalesce(p.paragraphs, [])
    THEN p.paragraphs
    ELSE coalesce(p.paragraphs, []) + $paragraph
END

// age: the occurrence merged under its character, keyed on age and chapter
MERGE (c:Character {name: $name})
MERGE (c)-[:HAS_AGE]->(a:AgeMention {age: $age, chapter: $chapter})
```

### Reads (`src/detection.py`)

| Query | Finds | Condition |
|---|---|---|
| `find_location_inconsistencies` | one character, two presences in the same chapter, different locations | `p1.chapter = p2.chapter AND l1.name < l2.name` |
| `find_age_inconsistencies` | one character, two different ages in different chapters | `a1.chapter < a2.chapter AND a1.age <> a2.age` |

### Where node types come from

`src/registry.json` (117 entries) types a name as `Character`, `Location` or `Organisation`.
Names not in the registry fall back to `SPACY_TO_SCHEMA` in `src/registry.py`
(`PERSON` to `Character`, `GPE` to `Location`, `ORG` to `Organisation`). Any other label
resolves to `None` and never reaches the graph.

## 4. Design rationale

### Why presence and age are nodes, not edges

A statement such as "Zelkarev is in Thornhaven in chapter 1" is stored as a node of its own
(reification) rather than as a single edge. An edge carrying the chapter,
`(Character)-[:AT {chapter}]->(Location)`, would keep both locations and do the same job today,
but it has no room to grow. An edge joins exactly two things. A `Presence` node can take a
third or fourth, such as an event, another character or a position in the text, without being
rebuilt.

### Why the chapter sits on the occurrence

The chapter belongs to the statement, not to the character or the place. Zelkarev is in many
places across the book, and Thornhaven holds many characters; only the claim "he is here, in
this chapter" has one chapter. The paragraph is stored on the same node for the same reason.

### Why every write is a MERGE, and why occurrences merge on the whole path

`CREATE` always makes a new node; `MERGE` finds a matching one and creates it only if none
exists. The first design used `CREATE` for occurrences. A planted clash then came back as two
identical rows: every sentence made a new `Presence`, so a fact stated in five sentences gave
five nodes, and two locations with five nodes each would give 25 rows for one inconsistency.
That would distort precision through storage rather than detection.

A `Presence` has no identity of its own. It means "this character, at this place, in this
chapter", so it can only be found by that full path. Merging on the chapter alone would match
any `Presence` in the chapter, so every character in it would share one node and the
contradiction would be lost without any error. `AgeMention` follows the same rule, but the age
is part of its key: two different ages in one chapter give two nodes, because a different age
is itself the contradiction.

### Why paragraphs are a list, not part of identity

Switching to `MERGE` kept each fact but lost which paragraph stated it, and the gold standard
locates every row by paragraph. The fix is a list on the `Presence`: each paragraph is added
unless it is already there. Because the list is not part of identity, the same fact stated in
two paragraphs still shares one node. The duplicate check has not yet been exercised on real
data.

### Why Organisation is a single flat node

No detection case needs a house's internal structure. Modelling lineage or retainers would be
world-building scope creep rather than research, so an organisation is one node joined to its
members by `MEMBER_OF`.

### Why `<` in the location query and `<>` in the age query

Matching two presences of one character returns every combination, both A with B and B with A.
`<>` kept both orderings, so every clash was reported twice. `<` keeps only the alphabetical
ordering and also excludes a location compared with itself. The age query can use `<>` because
its chapter condition (`a1.chapter < a2.chapter`) has already removed the second ordering.

### Identity is the exact name string

Entities merge on `name`, so one person written two ways ("ceremonial" and short forms, see
GS-17) becomes two nodes, and two people sharing a name become one. The same applies to places.
This is a known cost of the design, listed below.

## 5. Deferred work and limitations

| Item | State |
|---|---|
| `Event` node type | Designed, not built. spaCy already labels "the War of Two Monarchs" as `EVENT`; the pipeline discards it |
| Timeline query | Not built; depends on `Event`. Timeline cases are left to the LLM arm |
| Journey problem | A character who travels within a chapter is flagged. A fix recording each mention's position was designed, not built; reading order is still not story order |
| Same-chapter ages | Not compared; the age query only looks across chapters |
| Legitimate ageing | Any change of age across chapters is flagged; the graph has no record of story time |
| Organisation and `MEMBER_OF` | Storage functions written, never called, no query |
| Names that are both an organisation and a place (GS-39, Graystone) | One name can only hold one type |
| Knowledge and appearance (GS-24, GS-21, GS-37) | No node or relationship for them |
| Titles and nicknames typed as `Character` | Known limitation; a title would be better as a relationship |
| Name-form identity (people and places) | Known defect, see section 4 |
