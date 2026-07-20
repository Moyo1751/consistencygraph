import spacy

nlp = spacy.load("en_core_web_sm")

# text = """
# Chapter 1: The Return

# Aldric Stormborn had not seen the walls of Thornhaven in fifteen years. 
# The last time he had passed through these gates, he was a boy of twelve, 
# fleeing the coup that killed his father, King Aldric the Elder.

# Now he returned as a man grown, with Mira Shadowblade at his side and 
# the legendary Sword of Dawn strapped to his back. The blade had been 
# forged in the fires of Mount Kaelos three thousand years ago.

# "The guards will recognise you," Mira warned, her dark eyes scanning 
# the battlements. "Your face is your father's face."

# Aldric nodded. He was twenty-seven now, the same age his father had been 
# when he took the throne.
# """

# doc = nlp(text)

# print("Entities found:")
# for ent in doc.ents:
#     print(f"  {ent.text:25} -> {ent.label_}")

# ## Run it:
# ## python extract.py

def extract(text, chapter): 
    doc = nlp(text)
    result = []

    for ent in doc.ents:
        result.append({"text": ent.text, "label": ent.label_, "chapter": chapter, "startChar": ent.start_char, "endChar": ent.end_char})

    # returns all labels intentionally — filter at consumer, keeping the RQ1 baseline honest
    return result


ext = extract("Aldric Stormborn had not seen the outskirts of Thornton in fifteen years. The last time he had passed through these gates, he was a boy of twelve, fleeing the coup that killed his father, King Aldric the Elder.", 1)
print(ext)
for data in ext:
    print(f" {data["text"]} -> {data["label"]} (start: {data["startChar"]}, end: {data["endChar"]}) -> Chapter {data["chapter"]}")