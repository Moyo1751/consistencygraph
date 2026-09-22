import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "registry.json"
with open(REGISTRY_PATH) as f:
    registry = json.load(f)

def lookup(name: str) -> str | None:
    return registry.get(name)

SPACY_TO_SCHEMA = {
    "PERSON": "Character",
    "GPE": "Location",
    "ORG": "Organisation",
}