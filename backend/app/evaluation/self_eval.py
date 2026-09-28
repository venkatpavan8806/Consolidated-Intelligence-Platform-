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
    property_count = conn.execute("SELECT COUNT(*) AS n FROM case_property").fetchone()["n"]
    sources.append({"source": "Physical-evidence property/seizure records", "record_count": property_count})
    ndps_count = conn.execute("SELECT COUNT(*) AS n FROM ndps_sampling").fetchone()["n"]
    sources.append({"source": "NDPS Test Memo (Form-6) records", "record_count": ndps_count})
    mo_count = conn.execute("SELECT COUNT(*) AS n FROM crime_mo_record").fetchone()["n"]
    sources.append({"source": "NCRB IIF-II Crime Details Form (MO) records", "record_count": mo_count})
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
    from app.detectors.narcotics_physical import detect_ndps_compliance_flags
    from app.detectors.robbery_theft_physical import (
        detect_vehicle_links, detect_property_item_matches, detect_lingering_property,
    )
    from app.detectors.robbery_theft_digital import detect_mo_series
    from app.classification.case_type_classifier import classify_case

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

    ndps_hits = {h["property_id"]: h for h in detect_ndps_compliance_flags(conn)}
    gt_ndps = gt["cases"]["C003"]
    clean_ok = gt_ndps["compliant_property"] not in ndps_hits
    checks.append({"check": "ndps_compliant_seizure_produces_zero_flags", "passed": clean_ok})
    violation_hit = ndps_hits.get(gt_ndps["violation_property"])
    found_flags = {f["flag"] for f in violation_hit["flags"]} if violation_hit else set()
    expected_flags = set(gt_ndps["expected_violation_flags"])
    ndps_ok = expected_flags.issubset(found_flags)
    checks.append({"check": "ndps_all_planted_violations_flagged", "passed": ndps_ok,
                   "detail": {"expected": sorted(expected_flags), "found": sorted(found_flags)}})

    gt_robbery = gt["cases"]["C004"]
    vehicle_hits = {(h["stolen_item_id"], h["recovered_item_id"]): h for h in detect_vehicle_links(conn)}
    tamper_hit = vehicle_hits.get((gt_robbery["vehicle_tamper_stolen_item"], gt_robbery["vehicle_tamper_recovered_item"]))
    checks.append({"check": "robbery_vehicle_tampering_detected",
                   "passed": bool(tamper_hit and tamper_hit["tampering_suspected"])})

    property_hits = {(h["stolen_item_id"], h["recovered_item_id"]): h for h in detect_property_item_matches(conn)}
    link_hit = property_hits.get((gt_robbery["laptop_stolen_item"], gt_robbery["laptop_recovered_item"]))
    checks.append({"check": "robbery_property_exact_identifier_link_detected",
                   "passed": bool(link_hit and link_hit["match_type"] == "LINK")})

    lingering_hits = {h["property_id"] for h in detect_lingering_property(conn)}
    checks.append({"check": "robbery_lingering_property_flagged_compliant_silent",
                   "passed": gt_robbery["lingering_property_id"] in lingering_hits
                             and gt_robbery["compliant_property_id"] not in lingering_hits})

    mo_hits = detect_mo_series(conn)
    expected_pair = set(gt_robbery["mo_series_firs"])
    s112_ok = any(set((h["fir_a"], h["fir_b"])) == expected_pair and h["bns_112_candidate"] for h in mo_hits)
    checks.append({"check": "robbery_mo_series_s112_candidate_detected", "passed": s112_ok})

    expected_top_case_type = {"C001": "FINANCIAL_FRAUD", "C002": "TRAFFICKING_MISSING_PERSON", "C003": "NARCOTICS",
                               "C004": "ROBBERY_THEFT", "C005": "ROBBERY_THEFT"}
    for case_id, expected_type in expected_top_case_type.items():
        suggestions = classify_case(conn, case_id)
        top_type = suggestions[0]["case_type"] if suggestions else None
        checks.append({"check": f"case_type_classifier_top_suggestion_{case_id}",
                       "passed": top_type == expected_type,
                       "detail": {"expected": expected_type, "got": top_type,
                                  "all_suggestions": [(s["case_type"], s["confidence"]) for s in suggestions]}})

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
