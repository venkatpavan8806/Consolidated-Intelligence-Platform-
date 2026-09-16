"""
spaCy NER wrapper. Used only as a supplementary signal, never as the sole
source of role-labeled names or Indian place names -- see the rule-based
backstops in regex_patterns.py and gazetteer.py, added specifically because
the small spaCy model misses/truncates names and mis-handles local place
names (documented gotchas #1 and #6).

Extraction scores here are a fixed, honestly-labeled tier (SPACY_NER_SCORE),
not a fabricated per-entity confidence -- spaCy's small model does not expose
a calibrated probability for NER spans.
"""
import spacy

SPACY_NER_SCORE = 0.6

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_spacy_entities(text: str):
    nlp = get_nlp()
    doc = nlp(text)
    results = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            entity_type = "PERSON"
        elif ent.label_ in ("GPE", "LOC", "FAC"):
            entity_type = "LOCATION"
        elif ent.label_ == "ORG":
            entity_type = "ORGANIZATION"
        else:
            continue
        results.append({
            "start": ent.start_char,
            "end": ent.end_char,
            "text": ent.text,
            "entity_type": entity_type,
        })
    return results
