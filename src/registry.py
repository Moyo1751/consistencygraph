"""The manual registry (registry.json) and the spaCy label to schema type map."""

import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "registry.json"
with open(REGISTRY_PATH) as f:
    registry = json.load(f)

def lookup(name: str) -> str | None:
    """Schema type for an exact name, or None if it isn't listed."""
    return registry.get(name)

# Fallback for names not in the registry. Any other label resolves to None.
SPACY_TO_SCHEMA = {
    "PERSON": "Character",
    "GPE": "Location",
    "ORG": "Organisation",
}
