"""Shared setup: .env settings, the spaCy model, the Neo4j driver and the LLM client."""

import spacy
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from anthropic import Anthropic

load_dotenv()
nlp = spacy.load("en_core_web_sm")

# Pinned, never a floating alias. The evaluation has to name the exact model.
LLM_MODEL = "claude-sonnet-5"
LLM_EFFORT = "medium"
LLM_MAX_TOKENS = 32000


def get_driver():
    """Neo4j driver from .env. The caller closes it."""
    URI = os.environ["NEO4J_URI"]
    AUTH = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    return GraphDatabase.driver(URI, auth=AUTH)


def get_llm_client():
    """Anthropic client. Needs ANTHROPIC_API_KEY in .env."""
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
