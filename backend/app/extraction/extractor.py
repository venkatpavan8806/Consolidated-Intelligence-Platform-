from app.db.schema import get_connection
from app.extraction.regex_patterns import extract_role_labeled_names, extract_structured_identifiers
from app.extraction.gazetteer import match_gazetteer
from app.extraction.ner import extract_spacy_entities

REGEX_SCORE = 0.95
ROLE_KEYWORD_SCORE = 0.85
GAZETTEER_SCORE = 0.8

# Generic role/rank nouns that spaCy's small model occasionally mis-tags as a
# PERSON span in short FIR-style sentences (e.g. a bare "Victim last seen..."
# with no actual name given). These strings are never real names, so a
# spaCy PERSON hit that is exactly one of these (case-insensitive) is dropped
# rather than surfaced as a fabricated identity.
_NON_NAME_PERSON_TOKENS = {
    "victim", "witness", "accused", "complainant", "officer", "inspector",
    "police", "constable", "investigating officer",
}


def _overlaps(span, spans):
    s, e = span
    return any(s < e2 and e > s2 for s2, e2 in spans)


class MentionSeq:
    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return f"MEN{self.n:06d}"


def extract_from_text(record_id: str, text: str, seq: MentionSeq, source_type: str = "FIR"):
    """Run every extractor over one narrative record's text and return
    de-duplicated mentions. Used identically for FIRs, surveillance reports,
    and intelligence-agency reports -- only source_type (provenance) differs;
    the extraction logic itself is source-agnostic."""
    mentions = []
    claimed_spans = []

    for item in extract_structured_identifiers(text):
        mentions.append({
            "mention_id": seq.next(), "source_record_id": record_id, "source_type": source_type,
            "text": item["text"], "entity_type": item["entity_type"], "fir_role": None,
            "extraction_method": "REGEX", "extraction_score": REGEX_SCORE,
            "span_start": item["start"], "span_end": item["end"],
        })
        claimed_spans.append((item["start"], item["end"]))

    for item in extract_role_labeled_names(text):
        mentions.append({
            "mention_id": seq.next(), "source_record_id": record_id, "source_type": source_type,
            "text": item["text"], "entity_type": "PERSON", "fir_role": item["fir_role"],
            "extraction_method": "ROLE_KEYWORD", "extraction_score": ROLE_KEYWORD_SCORE,
            "span_start": item["start"], "span_end": item["end"],
        })
        claimed_spans.append((item["start"], item["end"]))

    for start, end, matched_text, entity_type in match_gazetteer(text):
        span = (start, end)
        if _overlaps(span, claimed_spans):
            continue
        mentions.append({
            "mention_id": seq.next(), "source_record_id": record_id, "source_type": source_type,
            "text": matched_text, "entity_type": entity_type, "fir_role": None,
            "extraction_method": "GAZETTEER", "extraction_score": GAZETTEER_SCORE,
            "span_start": start, "span_end": end,
        })
        claimed_spans.append(span)

    for item in extract_spacy_entities(text):
        span = (item["start"], item["end"])
        if _overlaps(span, claimed_spans):
            continue
        if item["entity_type"] == "PERSON" and item["text"].strip().lower() in _NON_NAME_PERSON_TOKENS:
            continue
        mentions.append({
            "mention_id": seq.next(), "source_record_id": record_id, "source_type": source_type,
            "text": item["text"], "entity_type": item["entity_type"], "fir_role": None,
            "extraction_method": "SPACY_NER", "extraction_score": 0.6,
            "span_start": item["start"], "span_end": item["end"],
        })
        claimed_spans.append(span)

    return mentions


def run_extraction():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM entity_mentions")
    fir_records = cur.execute("SELECT fir_id, text FROM fir_records").fetchall()
    intel_records = cur.execute("SELECT record_id, text, source_category FROM intel_records").fetchall()

    seq = MentionSeq()
    all_mentions = []
    for row in fir_records:
        all_mentions.extend(extract_from_text(row["fir_id"], row["text"], seq, source_type="FIR"))
    for row in intel_records:
        all_mentions.extend(extract_from_text(row["record_id"], row["text"], seq, source_type=row["source_category"]))

    cur.executemany(
        """INSERT INTO entity_mentions
           (mention_id, source_record_id, source_type, text, entity_type, fir_role,
            extraction_method, extraction_score, span_start, span_end)
           VALUES (:mention_id, :source_record_id, :source_type, :text, :entity_type, :fir_role,
                   :extraction_method, :extraction_score, :span_start, :span_end)""",
        all_mentions,
    )
    conn.commit()
    conn.close()
    return {
        "fir_records_processed": len(fir_records),
        "intel_records_processed": len(intel_records),
        "mentions_extracted": len(all_mentions),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_extraction(), indent=2))
