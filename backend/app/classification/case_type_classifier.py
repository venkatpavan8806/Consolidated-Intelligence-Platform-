"""
Case-type classifier (Axis B). Reads whatever evidence already exists for a
case -- structural leads already fired by the digital/physical detectors,
plus keyword matches in the case's free-text FIR/intel narratives -- and
SUGGESTS one or more of the 6 controlled case types, each with a numeric
confidence and a human-readable reason listing exactly which signals fired.

This follows the same governing rule as every other output in this system:
DATA -> RELATIONSHIP/SIGNAL -> ... -> HUMAN DECISION. The classifier never
writes a CONFIRMED row and never activates a module by itself -- it only
ever proposes SUGGESTED rows in case_case_types for an investigator to
confirm or reject (see app/api/routes.py: /cases/{id}/classify and
/cases/{id}/case-types/{case_type}/confirm). It also never overwrites a
row a human has already decided (CONFIRMED or REJECTED) -- re-running the
classifier (e.g. after new evidence lands) only ever touches SUGGESTED rows.

Deterministic and fully explainable by construction: every point of
confidence traces to either (a) a named lead_type that already fired for
this case's entities/records, or (b) a specific keyword string found in a
specific FIR/intel record. No ML, no embeddings, no opaque scoring.
"""
import re
from collections import defaultdict

from app.config import (
    CASE_TYPES,
    CASE_TYPE_KEYWORDS,
    CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE,
    CLASSIFIER_STRUCTURAL_SIGNAL_WEIGHT,
    CLASSIFIER_STRUCTURAL_SIGNAL_MAX,
    CLASSIFIER_KEYWORD_SIGNAL_WEIGHT,
    CLASSIFIER_KEYWORD_SIGNAL_MAX,
    CLASSIFIER_SUGGESTION_THRESHOLD,
)
from app.graph.case_view import get_case_entity_ids
from app.evidence.engine import build_all_leads

_KEYWORD_PATTERNS = {
    case_type: [(kw, re.compile(re.escape(kw), re.IGNORECASE)) for kw in keywords]
    for case_type, keywords in CASE_TYPE_KEYWORDS.items()
}


def _case_narrative_text(conn, case_id: str):
    """Every free-text narrative record tied to this case, as
    (source_record_id, text) pairs -- FIRs and intel/surveillance reports
    alike, since both go through the same NLP pipeline and both are
    legitimate evidence of what kind of case this is."""
    rows = []
    for r in conn.execute("SELECT fir_id AS rid, text FROM fir_records WHERE case_id=?", (case_id,)).fetchall():
        rows.append((r["rid"], r["text"]))
    for r in conn.execute("SELECT record_id AS rid, text FROM intel_records WHERE case_id=?", (case_id,)).fetchall():
        rows.append((r["rid"], r["text"]))
    return rows


def score_keyword_signals(texts):
    """Pure text -> per-case-type matched-keyword-group signals. Kept
    separate from any DB/case concept so it can be unit-tested directly
    against arbitrary strings, and reused unchanged once other case types
    get their own free-text record types (per HANDOFF.md Section 6)."""
    hits = defaultdict(lambda: defaultdict(set))  # case_type -> keyword -> {source_record_id,...}
    for source_id, text in texts:
        if not text:
            continue
        for case_type, patterns in _KEYWORD_PATTERNS.items():
            for keyword, pattern in patterns:
                if pattern.search(text):
                    hits[case_type][keyword].add(source_id)
    return hits


def score_structural_signals(conn, case_id: str):
    """Which case-type-mapped lead_types have actually fired for this
    case's own entities/records, reusing the exact same case-scoping logic
    as GET /cases/{id}/leads (entity-graph intersection, or a lead's own
    case_id for record-level leads like NDPS_COMPLIANCE that don't sit on
    the entity graph) -- so "the classifier suggested it" and "the Leads
    tab shows it" are always consistent with each other."""
    case_node_ids = get_case_entity_ids(conn, case_id)
    all_leads = build_all_leads(conn)
    relevant = [
        l for l in all_leads
        if case_node_ids.intersection(l["entities_involved"]) or l.get("case_id") == case_id
        or case_id in l.get("case_ids", ())
    ]

    hits = defaultdict(lambda: defaultdict(list))  # case_type -> lead_type -> [lead_id,...]
    for lead in relevant:
        case_type = CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE.get(lead["lead_type"])
        if case_type:
            hits[case_type][lead["lead_type"]].append(lead["lead_id"])
    return hits


def classify_case(conn, case_id: str):
    """Returns a list of {case_type, confidence, reason, signals} for every
    case type that cleared the suggestion threshold, sorted by confidence
    descending. Read-only -- does not write to case_case_types itself (see
    suggest_case_types_for_case for the write path)."""
    structural = score_structural_signals(conn, case_id)
    keyword = score_keyword_signals(_case_narrative_text(conn, case_id))

    results = []
    for case_type in CASE_TYPES:
        signals = []
        score = 0.0

        struct_hits = structural.get(case_type, {})
        struct_score = min(len(struct_hits) * CLASSIFIER_STRUCTURAL_SIGNAL_WEIGHT, CLASSIFIER_STRUCTURAL_SIGNAL_MAX)
        if struct_hits:
            score += struct_score
            for lead_type, lead_ids in sorted(struct_hits.items()):
                signals.append({
                    "kind": "STRUCTURAL", "lead_type": lead_type,
                    "lead_count": len(lead_ids), "lead_ids": lead_ids,
                })

        kw_hits = keyword.get(case_type, {})
        kw_score = min(len(kw_hits) * CLASSIFIER_KEYWORD_SIGNAL_WEIGHT, CLASSIFIER_KEYWORD_SIGNAL_MAX)
        if kw_hits:
            score += kw_score
            for kw, source_ids in sorted(kw_hits.items()):
                signals.append({
                    "kind": "KEYWORD", "keyword": kw,
                    "source_record_ids": sorted(source_ids),
                })

        score = round(min(score, 0.95), 3)  # never 1.0 -- a human always confirms
        if score < CLASSIFIER_SUGGESTION_THRESHOLD:
            continue

        reason_parts = []
        if struct_hits:
            reason_parts.append(
                "detector evidence already fired for this case: " +
                ", ".join(f"{lt} ({len(ids)})" for lt, ids in sorted(struct_hits.items()))
            )
        if kw_hits:
            reason_parts.append(
                "matched terms in case narrative text: " + ", ".join(f'"{kw}"' for kw in sorted(kw_hits))
            )
        results.append({
            "case_type": case_type,
            "confidence": score,
            "reason": "; ".join(reason_parts),
            "signals": signals,
        })

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def suggest_case_types_for_case(conn, case_id: str):
    """Writes the classifier's output to case_case_types as status=
    'SUGGESTED' rows. Never touches a row already CONFIRMED or REJECTED by
    a human -- a re-classification (e.g. triggered after new evidence is
    ingested) can only update an existing SUGGESTED row's confidence/reason
    or add a newly-crossed-threshold case type, never override a human
    decision. Returns the suggestions actually written (or left as-is)."""
    suggestions = classify_case(conn, case_id)

    existing = {
        r["case_type"]: r["status"]
        for r in conn.execute("SELECT case_type, status FROM case_case_types WHERE case_id=?", (case_id,)).fetchall()
    }

    for s in suggestions:
        current_status = existing.get(s["case_type"])
        if current_status in ("CONFIRMED", "REJECTED"):
            continue  # human decision stands, classifier does not override it
        conn.execute(
            """INSERT INTO case_case_types (case_id, case_type, status, confidence, reason)
               VALUES (?, ?, 'SUGGESTED', ?, ?)
               ON CONFLICT(case_id, case_type) DO UPDATE SET
                   confidence=excluded.confidence, reason=excluded.reason
               WHERE case_case_types.status = 'SUGGESTED'""",
            (case_id, s["case_type"], s["confidence"], s["reason"]),
        )
    conn.commit()
    return suggestions
