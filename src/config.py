import spacy
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase


load_dotenv() 

nlp = spacy.load("en_core_web_sm")

def get_driver():
    URI = os.environ["NEO4J_URI"]
    AUTH = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    return GraphDatabase.driver(URI, auth=AUTH)