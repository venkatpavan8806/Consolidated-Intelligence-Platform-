"""
Asserts every planted ground-truth case from the synthetic data generator is
correctly recovered by the pipeline -- not just a smoke test that it runs
without crashing.
"""
import json

from app.config import GROUND_TRUTH_PATH
from app.graph.builder import build_analysis_subgraph
from app.graph.analytics import run_full_analytics, compute_communities, top_n
from app.detectors.burner_sim import detect_burner_rotation
from app.detectors.mule_layering import detect_mule_layering
from app.detectors.temporal_motif import detect_call_before_transfer
from app.detectors.women_safety import detect_transporter_candidates, detect_repeat_locations
from app.audit import chain as audit_chain
from app.recovery.missing_link import evaluate_recall_at_k


def _gt():
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _phone_entity(conn, number):
    row = conn.execute("SELECT entity_id FROM entities WHERE entity_type='PHONE' AND canonical_value=?", (number,)).fetchone()
    return row["entity_id"] if row else None


def _person_entities_for_phone_mention(conn, phone_text):
    rows = conn.execute(
        "SELECT DISTINCT mem.entity_id FROM entity_mentions p "
        "JOIN mention_entity_map mem ON p.mention_id = mem.mention_id "
        "WHERE p.entity_type='PERSON' AND p.source_record_id IN "
        "(SELECT source_record_id FROM entity_mentions WHERE entity_type='PHONE' AND text=?)",
        (phone_text,),
    ).fetchall()
    return {r["entity_id"] for r in rows}


def test_name_collision_kept_separate(conn):
    gt = _gt()["cases"]["C001"]["name_collision"]
    a = _person_entities_for_phone_mention(conn, gt["person_a"])
    b = _person_entities_for_phone_mention(conn, gt["person_b"])
    assert a and b
    assert a.isdisjoint(b), "two distinct 'Rajesh Kumar' identities must not be merged"


def test_alias_spellings_merged(conn):
    gt = _gt()["cases"]["C001"]["alias_merge"]
    phone_eid = _phone_entity(conn, gt["phone"])
    assert phone_eid
    rows = conn.execute(
        "SELECT DISTINCT mem2.entity_id FROM entity_mentions em1 "
        "JOIN mention_entity_map mem1 ON em1.mention_id = mem1.mention_id "
        "JOIN entity_mentions em2 ON em2.source_record_id = em1.source_record_id AND em2.entity_type='PERSON' "
        "JOIN mention_entity_map mem2 ON em2.mention_id = mem2.mention_id "
        "WHERE mem1.entity_id = ?", (phone_eid,),
    ).fetchall()
    resolved = {r["entity_id"] for r in rows}
    assert len(resolved) == 1, "both spellings sharing one phone must resolve to a single identity"


def test_officer_excluded_and_never_tops_ranking(conn):
    gt = _gt()["cases"]["C001"]["official"]
    officer_eid = _phone_entity(conn, gt["phone"])
    row = conn.execute("SELECT is_official FROM entities WHERE entity_id=?", (officer_eid,)).fetchone()
    assert row["is_official"] == 1

    analytics = run_full_analytics(conn)
    assert officer_eid not in analytics["graph"], "officer must be structurally excluded from the analysis graph"
    top_ids = {e for e, _ in top_n(analytics["degree"], 10)} | {e for e, _ in top_n(analytics["pagerank"], 10)} \
        | {e for e, _ in top_n(analytics["broker"], 10)}
    assert officer_eid not in top_ids


def test_utility_excluded_and_never_tops_ranking(conn):
    gt = _gt()["cases"]["C001"]["utility_number"]
    utility_eid = _phone_entity(conn, gt["number"])
    row = conn.execute("SELECT is_utility FROM entities WHERE entity_id=?", (utility_eid,)).fetchone()
    assert row["is_utility"] == 1

    analytics = run_full_analytics(conn)
    assert utility_eid not in analytics["graph"]
    top_ids = {e for e, _ in top_n(analytics["degree"], 10)} | {e for e, _ in top_n(analytics["pagerank"], 10)} \
        | {e for e, _ in top_n(analytics["broker"], 10)}
    assert utility_eid not in top_ids


def test_burner_rotation_detected(conn):
    gt = _gt()["cases"]["C001"]["burner_rotation"]
    hits = detect_burner_rotation(conn)
    assert any(h["phone_earlier"] == gt["phone_a"] and h["phone_later"] == gt["phone_b"] for h in hits)


def test_mule_layering_detected(conn):
    gt = _gt()["cases"]["C001"]["mule_layering"]
    result = detect_mule_layering(conn)
    found_l2 = {f["layer2_account"] for f in result["funnels"]}
    assert set(gt["layer2"]).issubset(found_l2)
    for funnel in result["funnels"]:
        if funnel["layer2_account"] in gt["layer2"]:
            assert len(funnel["layer1_accounts"]) >= 2


def test_call_before_transfer_detected(conn):
    hits = detect_call_before_transfer(conn)
    assert len(hits) >= 1
    assert any(h["transfer_amount"] >= 500000 for h in hits)


def test_bridge_broker_detected(conn):
    gt = _gt()["cases"]["C001"]["bridge_broker"]
    analytics = run_full_analytics(conn)
    broker_eid = None
    row = conn.execute("SELECT entity_id FROM entities WHERE entity_type='ACCOUNT' AND canonical_value=?",
                        (gt["account"],)).fetchone()
    broker_eid = row["entity_id"] if row else None
    assert broker_eid in analytics["graph"]
    assert analytics["broker"].get(broker_eid, 0) >= 1


def test_women_safety_recruiter_and_transporter_found(conn):
    gt = _gt()["cases"]["C002"]
    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    result = detect_transporter_candidates(g, membership)

    recruiter_eid = _phone_entity(conn, gt["recruiter"])
    transporter_eid = _phone_entity(conn, gt["transporter"])

    assert recruiter_eid in result["recruiters"], "recruiter must be found via fan-out heuristic"
    assert transporter_eid in result["transporters"], "transporter must be found via bridge detection"
    methods = result["transporters"][transporter_eid]["methods"]
    assert "STRUCTURAL_BRIDGE_PATH" in methods, "structural bridge-path is the primary method for small chains"


def test_repeat_location_signal(conn):
    gt = _gt()["cases"]["C002"]["repeat_location"]
    results = detect_repeat_locations(conn)
    matching = [r for r in results if r["location"] == gt["name"]]
    assert matching, "the repeated trafficking-corridor location must be flagged"
    assert matching[0]["independent_source_count"] >= gt["min_independent_sources"]


def test_mundane_station_not_flagged_as_repeat_location(conn):
    gt = _gt()["cases"]["C002"]
    results = detect_repeat_locations(conn)
    flagged_names = {r["location"] for r in results}
    assert gt["mundane_station"] not in flagged_names, \
        "a police station name recurring as the FILING station is expected, not a repeat-location signal"


def test_audit_chain_detects_and_recovers_from_tampering(conn):
    conn.execute("DELETE FROM audit_log")
    conn.commit()
    first = audit_chain.append_entry(conn, "tester", "QUERY_GRAPH", case_id="C001", reason="test")
    audit_chain.append_entry(conn, "tester", "GENERATE_LEADS", case_id="C001", reason="test")
    assert audit_chain.verify_chain(conn)["valid"] is True

    target_seq = first["seq"]
    tampered = audit_chain.tamper_entry(conn, target_seq, "TAMPERED")
    verify_result = audit_chain.verify_chain(conn)
    assert verify_result["valid"] is False
    assert target_seq in verify_result["broken_at_seq"]

    audit_chain.restore_entry(conn, target_seq, tampered["original"]["reason"], tampered["original"]["payload_raw"])
    assert audit_chain.verify_chain(conn)["valid"] is True


def test_masked_edge_recovery_runs_and_reports_recall(conn):
    result = evaluate_recall_at_k(conn)
    assert result["held_out_edge_count"] > 0
    for k in (10, 20, 50):
        assert f"recall_at_{k}" in result
        assert 0.0 <= result[f"recall_at_{k}"] <= 1.0
