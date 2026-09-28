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
from app.detectors.narcotics_physical import detect_ndps_compliance_flags
from app.detectors.robbery_theft_physical import (
    detect_vehicle_links, detect_property_item_matches, detect_lingering_property,
)
from app.detectors.robbery_theft_digital import detect_mo_series
from app.detectors.assault_homicide_physical import (
    detect_inquest_witness_violations, detect_injury_list_mismatch, detect_postmortem_missing_timing_fields,
    detect_custodial_death_intimation_violation, detect_mlc_classification_inconsistency,
    detect_forensic_matches, detect_forensic_confidence_misuse,
)
from app.detectors.assault_homicide_digital import detect_uncertified_tower_evidence, detect_spatiotemporal_correlation
from app.classification.case_type_classifier import (
    classify_case, suggest_case_types_for_case, score_keyword_signals,
)
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


def test_ndps_compliance_flags_all_planted_violations_detected(conn):
    gt = _gt()["cases"]["C003"]
    hits = {h["property_id"]: h for h in detect_ndps_compliance_flags(conn)}

    assert gt["compliant_property"] not in hits, \
        "a fully s.52A-compliant seizure must produce zero compliance flags -- the detector must not " \
        "fire on clean data"

    assert gt["violation_property"] in hits, "the planted non-compliant seizure must be flagged"
    found_flags = {f["flag"] for f in hits[gt["violation_property"]]["flags"]}
    expected_flags = set(gt["expected_violation_flags"])
    missing = expected_flags - found_flags
    assert not missing, f"expected NDPS compliance flags not raised: {missing}"


def test_classifier_suggests_correct_case_type_for_each_seeded_case(conn):
    # C001 is seeded/confirmed FINANCIAL_FRAUD -- the classifier must
    # independently find it as the top-confidence suggestion from the
    # detector evidence and FIR text alone, not just echo the seed.
    top_c001 = classify_case(conn, "C001")
    assert top_c001, "classifier must find at least one case type for C001"
    assert top_c001[0]["case_type"] == "FINANCIAL_FRAUD"
    assert top_c001[0]["confidence"] >= 0.5
    assert any(s["kind"] == "STRUCTURAL" for s in top_c001[0]["signals"]), \
        "the top suggestion for a case with real detector hits must cite structural evidence, not keywords alone"

    top_c002 = classify_case(conn, "C002")
    assert top_c002 and top_c002[0]["case_type"] == "TRAFFICKING_MISSING_PERSON"
    assert top_c002[0]["confidence"] >= 0.5

    top_c003 = classify_case(conn, "C003")
    assert top_c003 and top_c003[0]["case_type"] == "NARCOTICS"
    assert top_c003[0]["confidence"] >= 0.5

    top_c004 = classify_case(conn, "C004")
    assert top_c004 and top_c004[0]["case_type"] == "ROBBERY_THEFT"
    assert top_c004[0]["confidence"] >= 0.5

    top_c005 = classify_case(conn, "C005")
    assert top_c005 and top_c005[0]["case_type"] == "ROBBERY_THEFT"
    assert top_c005[0]["confidence"] >= 0.5

    top_c006 = classify_case(conn, "C006")
    assert top_c006 and top_c006[0]["case_type"] == "ASSAULT_HOMICIDE"
    assert top_c006[0]["confidence"] >= 0.5

    top_c008 = classify_case(conn, "C008")
    assert top_c008 and top_c008[0]["case_type"] == "ASSAULT_HOMICIDE"
    assert top_c008[0]["confidence"] >= 0.5


def test_classifier_never_overrides_a_confirmed_case_type(conn):
    # C001 is seeded CONFIRMED for FINANCIAL_FRAUD. Running the classifier
    # (e.g. after new evidence lands) must never touch that row -- a human
    # decision stands even if re-classification would produce a different
    # confidence or reason for the same case type.
    before = dict(conn.execute(
        "SELECT * FROM case_case_types WHERE case_id='C001' AND case_type='FINANCIAL_FRAUD'"
    ).fetchone())
    assert before["status"] == "CONFIRMED"

    suggest_case_types_for_case(conn, "C001")

    after = dict(conn.execute(
        "SELECT * FROM case_case_types WHERE case_id='C001' AND case_type='FINANCIAL_FRAUD'"
    ).fetchone())
    assert after == before, "a CONFIRMED case-type row must be byte-for-byte untouched by a classifier re-run"


def test_classifier_suggestion_write_path_only_writes_suggested_rows(conn):
    conn.execute("DELETE FROM case_case_types WHERE case_id='C002'")
    conn.commit()

    suggestions = suggest_case_types_for_case(conn, "C002")
    assert any(s["case_type"] == "TRAFFICKING_MISSING_PERSON" for s in suggestions)

    rows = {r["case_type"]: r["status"] for r in
            conn.execute("SELECT * FROM case_case_types WHERE case_id='C002'").fetchall()}
    assert rows["TRAFFICKING_MISSING_PERSON"] == "SUGGESTED"
    assert all(status == "SUGGESTED" for status in rows.values()), \
        "the classifier's write path must never write CONFIRMED/REJECTED itself"


def test_keyword_scanner_matches_planted_terms_and_ignores_unrelated_text():
    # Direct unit test of the pure text->signal function, independent of
    # any case or DB state -- covers the 3 case types that don't yet have
    # a structured detector (Assault/Homicide, Robbery/Theft, Organized
    # Crime), so the classifier isn't silent on them before their modules
    # are built (see HANDOFF.md Section 6 checklist).
    texts = [
        ("FIR_TEST_1", "The victim was found with fatal injuries; a post-mortem was ordered and the case "
                        "was registered as culpable homicide."),
        ("FIR_TEST_2", "A robbery was reported at the jewellery shop; the accused fled after a chain "
                        "snatching incident nearby."),
        ("FIR_TEST_3", "Surveillance suggests the accused is linked to a wider syndicate operating an "
                        "extortion racket across the district -- organized crime angle to be probed."),
        ("FIR_TEST_4", "The investigating officer filed a routine status report; no new developments."),
    ]
    hits = score_keyword_signals(texts)

    assert "ASSAULT_HOMICIDE" in hits and {"post-mortem", "culpable homicide"}.issubset(hits["ASSAULT_HOMICIDE"])
    assert "ROBBERY_THEFT" in hits and {"robbery", "chain snatching"}.issubset(hits["ROBBERY_THEFT"])
    assert "ORGANIZED_CRIME" in hits and {"syndicate", "extortion"}.issubset(hits["ORGANIZED_CRIME"])

    # The routine, unrelated status report must not trip any lexicon --
    # zero false positives is as important as recall for a suggest-only
    # classifier an investigator has to triage.
    for case_type, kw_hits in hits.items():
        for kw, source_ids in kw_hits.items():
            assert "FIR_TEST_4" not in source_ids, \
                f"unrelated text falsely matched {case_type} keyword '{kw}'"


def test_robbery_theft_vehicle_link_and_tampering_detected(conn):
    gt = _gt()["cases"]["C004"]
    hits = detect_vehicle_links(conn)
    by_pair = {(h["stolen_item_id"], h["recovered_item_id"]): h for h in hits}

    clean = by_pair.get((gt["vehicle_clean_stolen_item"], gt["vehicle_clean_recovered_item"]))
    assert clean is not None, "the clean vehicle-type + 2-of-3 partial-identifier match must be found"
    assert clean["tampering_suspected"] is False

    tampered = by_pair.get((gt["vehicle_tamper_stolen_item"], gt["vehicle_tamper_recovered_item"]))
    assert tampered is not None, "chassis-matches-but-engine-differs must be found even with only 1 field matching"
    assert tampered["tampering_suspected"] is True

    # No other stolen<->recovered vehicle pair should be reported -- the
    # noise TV/bicycle/wallet items carry no vehicle_type at all and must
    # never appear here.
    assert len(hits) == 2


def test_robbery_theft_property_item_matches_link_and_candidate(conn):
    gt = _gt()["cases"]["C004"]
    hits = detect_property_item_matches(conn)
    by_pair = {(h["stolen_item_id"], h["recovered_item_id"]): h for h in hits}

    link = by_pair.get((gt["laptop_stolen_item"], gt["laptop_recovered_item"]))
    assert link is not None and link["match_type"] == "LINK", \
        "an exact serial/IMEI match must be a LINK even though the recovered value differs from the stolen value"

    candidate = by_pair.get((gt["chain_stolen_item"], gt["chain_recovered_item"]))
    assert candidate is not None and candidate["match_type"] == "CANDIDATE", \
        "a description match with no hard identifier, value within tolerance, must be a CANDIDATE not a LINK"

    assert len(hits) == 2, "the noise TV/bicycle/wallet items must never produce a match"


def test_robbery_theft_lingering_property_flagged_and_compliant_property_silent(conn):
    gt = _gt()["cases"]["C004"]
    hits = {h["property_id"]: h for h in detect_lingering_property(conn)}
    assert gt["lingering_property_id"] in hits, \
        "a recovered property with no court-disposal record long past the threshold must be flagged"
    assert gt["compliant_property_id"] not in hits, \
        "a recovered property disposed of well within the threshold must not be flagged -- zero false positives"


def test_robbery_theft_mo_series_and_s112_candidate_detected(conn):
    gt = _gt()["cases"]["C004"]
    hits = detect_mo_series(conn)
    fir_pairs = {frozenset((h["fir_a"], h["fir_b"])) for h in hits}
    expected_pair = frozenset(gt["mo_series_firs"])

    assert expected_pair in fir_pairs, "the two FIRs sharing 5 of 6 IIF-II fields within 60 days must be matched"
    match = next(h for h in hits if frozenset((h["fir_a"], h["fir_b"])) == expected_pair)
    assert len(match["shared_accused"]) >= gt["mo_series_min_shared_accused"]
    assert match["bns_112_candidate"] is True

    # The unrelated noise FIR (different MO entirely, and 150+ days away)
    # must never be paired with either series FIR.
    noise_fir = gt["mo_noise_fir"]
    assert not any(noise_fir in (h["fir_a"], h["fir_b"]) for h in hits), \
        "an FIR with a materially different modus operandi must not be matched into the series"


def test_inquest_witness_violation_detected_and_clean_case_silent(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["inquest_id"]: h for h in detect_inquest_witness_violations(conn)}
    assert gt["inquest_violation_id"] in hits, \
        "an inquest with fewer than the BNSS s.194 minimum witnesses must be flagged"
    assert hits[gt["inquest_violation_id"]]["required"] == gt["inquest_min_witnesses"]

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["inquest_clean_id"] not in hits, \
        "a compliant inquest with enough witnesses must not be flagged -- zero false positives"


def test_injury_list_mismatch_detected_and_clean_case_silent(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["pm_id"]: h for h in detect_injury_list_mismatch(conn)}
    assert gt["pm_violation_id"] in hits, \
        "an injury present in the inquest but missing from the post-mortem must be flagged"
    assert gt["mismatched_injury"] in hits[gt["pm_violation_id"]]["missing_from_pm"]

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["pm_clean_id"] not in hits, \
        "identical injury lists on both records must produce zero mismatch flags"


def test_postmortem_missing_timing_fields_detected_and_clean_case_silent(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["pm_id"]: h for h in detect_postmortem_missing_timing_fields(conn)}
    assert gt["pm_violation_id"] in hits
    assert {"rectal_temperature", "rigor_mortis_timing"}.issubset(set(hits[gt["pm_violation_id"]]["missing_fields"]))

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["pm_clean_id"] not in hits, \
        "a post-mortem with both rectal_temperature and rigor_mortis timing recorded must not be flagged"


def test_custodial_death_intimation_violation_detected(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["inquest_id"]: h for h in detect_custodial_death_intimation_violation(conn)}
    assert gt["inquest_violation_id"] in hits
    hit = hits[gt["inquest_violation_id"]]
    assert hit["violation"] == "INTIMATION_DELAYED"
    assert hit["hours_elapsed"] == gt["custodial_intimation_hours"]

    # C008's death is not custodial at all -- must never be considered here.
    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["inquest_clean_id"] not in hits


def test_mlc_classification_inconsistency_both_directions_detected(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["mlc_id"]: h for h in detect_mlc_classification_inconsistency(conn)}
    assert gt["mlc_low_followup_id"] in hits and hits[gt["mlc_low_followup_id"]]["issue"] == "GRIEVOUS_WITH_LOW_FOLLOWUP"
    assert gt["mlc_high_followup_id"] in hits and hits[gt["mlc_high_followup_id"]]["issue"] == "SIMPLE_WITH_HIGH_FOLLOWUP"

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["mlc_clean_id"] not in hits, \
        "a GRIEVOUS classification backed by a substantial follow-up period must not be flagged"


def test_forensic_matches_respect_per_discipline_evidentiary_strength(conn):
    gt = _gt()["cases"]["C006"]
    gt_clean = _gt()["cases"]["C008"]
    hits = detect_forensic_matches(conn)
    by_id = {h["match_id"]: h for h in hits}

    fp = by_id.get(gt["forensic_fingerprint_link_id"])
    assert fp is not None and fp["finding_type"] == "LINK", \
        "AFIS/NAFIS is a real networked database -- a matching NFN must be an automated LINK"
    assert sorted((fp["case_id_a"], fp["case_id_b"])) == sorted((gt["coldcase_id"], "C006"))

    ballistics = by_id.get(gt["forensic_ballistics_candidate_id"])
    assert ballistics is not None and ballistics["finding_type"] == "CANDIDATE_EXAMINER_ASSERTED", \
        "India has no verified networked ballistics database -- must never surface as an automated LINK"

    dna_clean = by_id.get(gt_clean["forensic_dna_clean_link_id"])
    assert dna_clean is not None and dna_clean["finding_type"] == "LINK", \
        "a categorical DNA 'MATCHES' result must be treated as a LINK"

    # The DNA record marked INCONCLUSIVE must never appear as a LINK/match
    # here, however the case file itself annotated it -- that's exactly
    # what test_forensic_confidence_misuse_detected checks separately.
    assert gt["forensic_dna_misuse_id"] not in by_id


def test_forensic_confidence_misuse_detected_and_clean_case_silent(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["match_id"] for h in detect_forensic_confidence_misuse(conn)}
    assert gt["forensic_dna_misuse_id"] in hits, \
        "an INCONCLUSIVE DNA result treated as positive in the case file must be flagged"

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["forensic_dna_clean_link_id"] not in hits, \
        "a categorical MATCHES result is never mistaken for a misuse case"


def test_uncertified_tower_evidence_detected_and_certified_case_silent(conn):
    gt = _gt()["cases"]["C006"]
    hits = {h["record_id"] for h in detect_uncertified_tower_evidence(conn)}
    assert gt["tower_uncertified_id"] in hits, \
        "a tower record with no s.65B(4) certificate must be flagged"
    assert gt["tower_certified_noise_id"] not in hits

    gt_clean = _gt()["cases"]["C008"]
    assert gt_clean["tower_clean_id"] not in hits, \
        "a certified tower record must never be flagged as uncertified"


def test_spatiotemporal_tower_correlation_detected(conn):
    gt = _gt()["cases"]["C006"]
    hits = detect_spatiotemporal_correlation(conn)
    by_record = {h["record_id"]: h for h in hits}

    hit = by_record.get(gt["tower_uncertified_id"])
    assert hit is not None, \
        "a tower ping near the death place and within the time window must correlate to the inquest"
    assert hit["is_certified_65b"] is False

    # The unrelated certified noise ping (different locality, different
    # time) must never correlate to this inquest.
    assert gt["tower_certified_noise_id"] not in by_record


def test_masked_edge_recovery_runs_and_reports_recall(conn):
    result = evaluate_recall_at_k(conn)
    assert result["held_out_edge_count"] > 0
    for k in (10, 20, 50):
        assert f"recall_at_{k}" in result
        assert 0.0 <= result[f"recall_at_{k}"] <= 1.0
