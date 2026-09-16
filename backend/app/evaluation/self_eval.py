"""
Self-evaluation: resolution correctness, role-exclusion correctness, NER
extraction score summary, masked-edge recovery numbers -- all computed from
the actual run against the planted ground_truth.json checklist, never
hard-coded or improved after the fact.
"""
import json
import os

from app.config import GROUND_TRUTH_PATH, PIPELINE_TIMINGS_PATH
from app.graph.analytics import run_full_analytics, top_n
from app.recovery.missing_link import evaluate_recall_at_k


def _load_ground_truth():
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def stage_timings():
    """Stage timings from the most recent pipeline run, persisted to disk at
    run time (see app/pipeline.py) so they survive independently of the
    audit chain, which can legitimately be reset. Never hard-coded."""
    if not os.path.exists(PIPELINE_TIMINGS_PATH):
        return {"available": False, "reason": "pipeline has not been run yet in this environment"}
    with open(PIPELINE_TIMINGS_PATH, "r", encoding="utf-8") as f:
        run = json.load(f)
    return {
        "available": True,
        "run_at": run.get("run_at"),
        "timings_seconds": run.get("timings_seconds"),
        "record_counts": run.get("record_counts"),
    }


def _entity_for_phone(conn, number):
    row = conn.execute("SELECT entity_id FROM entities WHERE entity_type='PHONE' AND canonical_value=?", (number,)).fetchone()
    return row["entity_id"] if row else None


def check_resolution_correctness(conn):
    gt = _load_ground_truth()["cases"]["C001"]
    checks = []

    rk1 = conn.execute("SELECT entity_id FROM entity_mentions em JOIN mention_entity_map mem ON em.mention_id=mem.mention_id "
                        "WHERE em.entity_type='PERSON' AND em.source_record_id IN "
                        "(SELECT source_record_id FROM entity_mentions WHERE entity_type='PHONE' AND text=?)",
                        (gt["name_collision"]["person_a"],)).fetchone()
    rk2 = conn.execute("SELECT entity_id FROM entity_mentions em JOIN mention_entity_map mem ON em.mention_id=mem.mention_id "
                        "WHERE em.entity_type='PERSON' AND em.source_record_id IN "
                        "(SELECT source_record_id FROM entity_mentions WHERE entity_type='PHONE' AND text=?)",
                        (gt["name_collision"]["person_b"],)).fetchone()
    name_collision_ok = bool(rk1 and rk2 and rk1["entity_id"] != rk2["entity_id"])
    checks.append({"check": "name_collision_kept_separate", "passed": name_collision_ok})

    alias_phone_entity = conn.execute("SELECT entity_id FROM entities WHERE entity_type='PHONE' AND canonical_value=?",
                                       (gt["alias_merge"]["phone"],)).fetchone()
    alias_person_entities = set()
    if alias_phone_entity:
        for row in conn.execute(
            "SELECT DISTINCT mem2.entity_id FROM entity_mentions em1 "
            "JOIN mention_entity_map mem1 ON em1.mention_id = mem1.mention_id "
            "JOIN entity_mentions em2 ON em2.source_record_id = em1.source_record_id AND em2.entity_type='PERSON' "
            "JOIN mention_entity_map mem2 ON em2.mention_id = mem2.mention_id "
            "WHERE mem1.entity_id = ?", (alias_phone_entity["entity_id"],)
        ).fetchall():
            alias_person_entities.add(row["entity_id"])
    checks.append({"check": "alias_spellings_merged", "passed": len(alias_person_entities) == 1,
                   "detail": {"resolved_entities": sorted(alias_person_entities)}})

    return checks


def check_role_exclusion_correctness(conn):
    gt = _load_ground_truth()["cases"]["C001"]
    analytics = run_full_analytics(conn)
    checks = []

    officer_phone_eid = _entity_for_phone(conn, gt["official"]["phone"])
    officer_row = conn.execute("SELECT is_official FROM entities WHERE entity_id=?", (officer_phone_eid,)).fetchone()
    checks.append({"check": "officer_phone_flagged_official", "passed": bool(officer_row and officer_row["is_official"])})

    top_degree_ids = {eid for eid, _ in top_n(analytics["degree"], 10)}
    top_pagerank_ids = {eid for eid, _ in top_n(analytics["pagerank"], 10)}
    top_broker_ids = {eid for eid, _ in top_n(analytics["broker"], 10)}
    officer_absent = officer_phone_eid not in (top_degree_ids | top_pagerank_ids | top_broker_ids)
    checks.append({"check": "officer_never_tops_ranking", "passed": officer_absent})
    checks.append({"check": "officer_excluded_from_analysis_graph", "passed": officer_phone_eid not in analytics["graph"]})

    utility_eid = _entity_for_phone(conn, gt["utility_number"]["number"])
    utility_row = conn.execute("SELECT is_utility FROM entities WHERE entity_id=?", (utility_eid,)).fetchone()
    checks.append({"check": "utility_number_flagged_utility", "passed": bool(utility_row and utility_row["is_utility"])})
    utility_absent = utility_eid not in (top_degree_ids | top_pagerank_ids | top_broker_ids)
    checks.append({"check": "utility_never_tops_ranking", "passed": utility_absent})
    checks.append({"check": "utility_excluded_from_analysis_graph", "passed": utility_eid not in analytics["graph"]})

    return checks


def data_source_coverage(conn):
    """Every distinct data source category actually ingested this run, with
    a live record count -- lets the demo point directly at the problem
    statement's list of source types and show each one is really there,
    not just claimed."""
    sources = []
    fir_count = conn.execute("SELECT COUNT(*) AS n FROM fir_records").fetchone()["n"]
    sources.append({"source": "FIRs and police reports", "record_count": fir_count})
    for row in conn.execute(
        "SELECT source_category, COUNT(*) AS n FROM intel_records GROUP BY source_category"
    ).fetchall():
        label = "Surveillance reports" if row["source_category"] == "SURVEILLANCE_REPORT" else "Intelligence agency reports"
        sources.append({"source": label, "record_count": row["n"]})
    cdr_count = conn.execute("SELECT COUNT(*) AS n FROM cdr_records").fetchone()["n"]
    sources.append({"source": "Call Detail Records (CDRs)", "record_count": cdr_count})
    txn_count = conn.execute("SELECT COUNT(*) AS n FROM transaction_records").fetchone()["n"]
    sources.append({"source": "Financial transaction records", "record_count": txn_count})
    return sources


def ner_extraction_score_summary(conn):
    rows = conn.execute(
        "SELECT extraction_method, COUNT(*) AS n, AVG(extraction_score) AS avg_score "
        "FROM entity_mentions GROUP BY extraction_method"
    ).fetchall()
    return [{"extraction_method": r["extraction_method"], "mention_count": r["n"],
             "avg_extraction_score": round(r["avg_score"], 3)} for r in rows]


def check_detector_hits(conn):
    from app.detectors.burner_sim import detect_burner_rotation
    from app.detectors.mule_layering import detect_mule_layering
    from app.detectors.temporal_motif import detect_call_before_transfer
    from app.graph.builder import build_analysis_subgraph
    from app.graph.analytics import compute_communities
    from app.detectors.women_safety import detect_transporter_candidates

    gt = _load_ground_truth()
    checks = []

    burner_hits = detect_burner_rotation(conn)
    expected = gt["cases"]["C001"]["burner_rotation"]
    burner_ok = any(h["phone_earlier"] == expected["phone_a"] and h["phone_later"] == expected["phone_b"] for h in burner_hits)
    checks.append({"check": "burner_rotation_detected", "passed": burner_ok})

    mule = detect_mule_layering(conn)
    expected_l2 = set(gt["cases"]["C001"]["mule_layering"]["layer2"])
    found_l2 = {f["layer2_account"] for f in mule["funnels"]}
    checks.append({"check": "mule_layering_detected", "passed": expected_l2.issubset(found_l2)})

    motif_hits = detect_call_before_transfer(conn)
    checks.append({"check": "call_before_transfer_detected", "passed": len(motif_hits) >= 1})

    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    ws = detect_transporter_candidates(g, membership)
    recruiter_eid = _entity_for_phone(conn, gt["cases"]["C002"]["recruiter"])
    transporter_eid = _entity_for_phone(conn, gt["cases"]["C002"]["transporter"])
    checks.append({"check": "women_safety_recruiter_found", "passed": recruiter_eid in ws["recruiters"]})
    checks.append({"check": "women_safety_transporter_found", "passed": transporter_eid in ws["transporters"],
                   "detail": {"methods": ws["transporters"].get(transporter_eid, {}).get("methods")}})

    return checks


def run_self_evaluation(conn):
    return {
        "resolution_correctness": check_resolution_correctness(conn),
        "role_exclusion_correctness": check_role_exclusion_correctness(conn),
        "detector_ground_truth_checks": check_detector_hits(conn),
        "data_source_coverage": data_source_coverage(conn),
        "ner_extraction_score_summary": ner_extraction_score_summary(conn),
        "masked_edge_recovery": evaluate_recall_at_k(conn),
        "stage_timings": stage_timings(),
    }
