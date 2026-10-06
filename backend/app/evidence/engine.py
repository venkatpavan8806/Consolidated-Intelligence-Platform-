"""
Evidence engine: turns raw detector output into investigator-facing Leads.
Every lead answers "why was this flagged?" with concrete signals and links
to source record IDs -- never a bare score. Every lead is a LEAD or PATH,
never a per-person guilt score (see governing principle: DATA -> RELATIONSHIP
-> PATTERN -> LEAD/PATH -> EVIDENCE -> HUMAN DECISION).
"""
import hashlib
import json
from datetime import datetime, timezone

from app.db.schema import get_connection
from app.graph.builder import build_analysis_subgraph
from app.graph.analytics import compute_communities, compute_broker_scores, compute_degree
from app.detectors.burner_sim import detect_burner_rotation
from app.detectors.mule_layering import detect_mule_layering
from app.detectors.temporal_motif import detect_call_before_transfer
from app.detectors.narcotics_physical import detect_ndps_compliance_flags
from app.detectors.assault_homicide_physical import (
    detect_inquest_witness_violations, detect_injury_list_mismatch, detect_postmortem_missing_timing_fields,
    detect_custodial_death_intimation_violation, detect_mlc_classification_inconsistency,
    detect_forensic_matches, detect_forensic_confidence_misuse,
)
from app.detectors.assault_homicide_digital import detect_uncertified_tower_evidence, detect_spatiotemporal_correlation
from app.detectors.robbery_theft_physical import (
    detect_vehicle_links, detect_property_item_matches, detect_lingering_property,
)
from app.detectors.robbery_theft_digital import detect_mo_series
from app.detectors.trafficking_physical import (
    detect_uidb_missing_person_candidates, detect_ignored_zipnet_match, detect_unsampled_body,
    detect_late_dna_dispatch, detect_weak_dna_conclusion_relied_alone,
)
from app.detectors.organized_crime_digital import (
    detect_cross_case_identifier_links, detect_shared_infrastructure, detect_syndicate_charge_sheet_threshold,
)
from app.detectors.imei_mapping import detect_imei_msisdn_mapping, detect_imei_corroborated_burner_rotation


def _lead_id(lead_type: str, key: str) -> str:
    digest = hashlib.sha256(f"{lead_type}:{key}".encode()).hexdigest()[:12]
    return f"LEAD_{lead_type}_{digest}"


def entity_label(conn, entity_id: str) -> str:
    row = conn.execute("SELECT canonical_value, entity_type FROM entities WHERE entity_id=?", (entity_id,)).fetchone()
    if not row:
        return entity_id
    return f"{row['canonical_value']} ({row['entity_type']})"


def _phone_entity(conn, number: str):
    row = conn.execute("SELECT entity_id FROM entities WHERE entity_type='PHONE' AND canonical_value=?", (number,)).fetchone()
    return row["entity_id"] if row else None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_leads(conn):
    leads = []

    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    broker_scores = compute_broker_scores(g, membership)
    degree_scores = compute_degree(g)

    # --- Broker / cross-community bridge leads (general "kingpin" analysis) ---
    for node, score in broker_scores.items():
        if score < 1:
            continue
        deg = degree_scores.get(node, 0)
        leads.append({
            "lead_id": _lead_id("BROKER_BRIDGE", node),
            "lead_type": "BROKER_BRIDGE",
            "severity": "HIGH" if score >= 2 and deg <= 5 else "MEDIUM",
            "entities_involved": [node],
            "requires_human_verification": True,
            "summary": f"{entity_label(conn, node)} bridges {score} otherwise-separate communities "
                       f"despite low connection volume (degree {deg}) -- the 'few calls, touches both "
                       f"sides' signature of a broker, not just a busy hub.",
            "signals": [
                {"signal": "cross_community_degree", "value": score},
                {"signal": "own_degree", "value": deg},
            ],
            "source_record_ids": [],
            "created_at": _now(),
        })

    # --- Burner-SIM rotation leads ---
    for hit in detect_burner_rotation(conn):
        a_eid, b_eid = _phone_entity(conn, hit["phone_earlier"]), _phone_entity(conn, hit["phone_later"])
        key = f"{hit['phone_earlier']}_{hit['phone_later']}"
        leads.append({
            "lead_id": _lead_id("BURNER_ROTATION", key),
            "lead_type": "BURNER_ROTATION",
            "severity": "HIGH",
            "entities_involved": [e for e in (a_eid, b_eid) if e],
            "requires_human_verification": True,
            "summary": f"Phone {hit['phone_earlier']} went silent on {hit['earlier_last_active']} and phone "
                       f"{hit['phone_later']} activated on {hit['later_first_active']} ({hit['gap_days']} day gap) "
                       f"sharing {hit['shared_contact_count']} contacts (Jaccard {hit['jaccard']}) -- a likely "
                       f"burner-SIM rotation. The two numbers never call each other directly.",
            "signals": [
                {"signal": "shared_contact_count", "value": hit["shared_contact_count"]},
                {"signal": "jaccard", "value": hit["jaccard"]},
                {"signal": "activation_gap_days", "value": hit["gap_days"]},
            ],
            "source_record_ids": [],
            "created_at": _now(),
        })

    # --- IMEI<->MSISDN device-continuity leads (mentor-requested feature:
    # IMEI mapping, GSM_CALL vs IP_CALL) ---
    for hit in detect_imei_msisdn_mapping(conn):
        eids = [e for e in (_phone_entity(conn, m) for m in hit["msisdns"]) if e]
        corroboration_note = (
            "backed by GSM-voice CDR tower trail" if hit["tower_corroborated"]
            else "backed only by IP_CALL records, which carry no reliable tower trail"
        )
        leads.append({
            "lead_id": _lead_id("IMEI_MSISDN_MAPPING", hit["imei"]),
            "lead_type": "IMEI_MSISDN_MAPPING",
            "severity": "MEDIUM",
            "entities_involved": eids,
            "requires_human_verification": True,
            "summary": f"Handset IMEI {hit['imei']} was used by {len(hit['msisdns'])} distinct phone numbers "
                       f"({', '.join(hit['msisdns'])}) -- a device-continuity candidate ({corroboration_note}). "
                       f"Could be shared/lent-out use, or the same person swapping SIMs to evade surveillance; "
                       f"needs a human check against the case file either way.",
            "signals": [
                {"signal": "distinct_msisdn_count", "value": len(hit["msisdns"])},
                {"signal": "gsm_call_count", "value": hit["gsm_call_count"]},
                {"signal": "ip_call_count", "value": hit["ip_call_count"]},
                {"signal": "tower_corroborated", "value": hit["tower_corroborated"]},
            ],
            "source_record_ids": sorted({rid for w in hit["msisdn_windows"].values() for rid in w["record_ids"]}),
            "created_at": _now(),
        })

    # --- IMEI-corroborated burner-SIM rotation: same social pattern as
    # BURNER_ROTATION above, PLUS the earlier/later phone sharing a
    # handset IMEI -- the SIM-swap-to-evade pattern, now with device-level
    # evidence, not just contact-overlap. Reported as its own lead rather
    # than silently upgrading BURNER_ROTATION (see detector docstring). ---
    for hit in detect_imei_corroborated_burner_rotation(conn):
        a_eid, b_eid = _phone_entity(conn, hit["phone_earlier"]), _phone_entity(conn, hit["phone_later"])
        key = f"{hit['phone_earlier']}_{hit['phone_later']}"
        leads.append({
            "lead_id": _lead_id("IMEI_CORROBORATED_BURNER_SWAP", key),
            "lead_type": "IMEI_CORROBORATED_BURNER_SWAP",
            "severity": "HIGH",
            "entities_involved": [e for e in (a_eid, b_eid) if e],
            "requires_human_verification": True,
            "summary": f"Phone {hit['phone_earlier']} and phone {hit['phone_later']} -- already a contact-overlap "
                       f"burner-rotation candidate -- were also both used on handset IMEI(s) "
                       f"{', '.join(hit['shared_imeis'])}, the SIM-swap-to-evade pattern: same physical device, "
                       f"two SIMs used one after the other.",
            "signals": [
                {"signal": "shared_contact_count", "value": hit["shared_contact_count"]},
                {"signal": "shared_imeis", "value": hit["shared_imeis"]},
                {"signal": "activation_gap_days", "value": hit["gap_days"]},
            ],
            "source_record_ids": [],
            "created_at": _now(),
        })

    # --- Mule layering leads ---
    mule = detect_mule_layering(conn)
    for funnel in mule["funnels"]:
        l2_eid = None
        row = conn.execute("SELECT entity_id FROM entities WHERE entity_type='ACCOUNT' AND canonical_value=?",
                            (funnel["layer2_account"],)).fetchone()
        l2_eid = row["entity_id"] if row else funnel["layer2_account"]
        l1_eids = []
        for l1 in funnel["layer1_accounts"]:
            r = conn.execute("SELECT entity_id FROM entities WHERE entity_type='ACCOUNT' AND canonical_value=?", (l1,)).fetchone()
            l1_eids.append(r["entity_id"] if r else l1)
        leads.append({
            "lead_id": _lead_id("MULE_LAYERING", funnel["layer2_account"]),
            "lead_type": "MULE_LAYERING",
            "severity": "HIGH",
            "entities_involved": [l2_eid] + l1_eids,
            "requires_human_verification": True,
            "summary": f"Account {funnel['layer2_account']} receives consolidated funds from "
                       f"{len(funnel['layer1_accounts'])} intermediate accounts, each of which fanned "
                       f"in from many small senders in a short window -- a layering pattern consistent "
                       f"with mule-account structuring, not a single suspicious transfer.",
            "signals": [{"signal": "layer1_account_count", "value": len(funnel["layer1_accounts"])}],
            "source_record_ids": [],
            "created_at": _now(),
        })

    # --- Cross-source temporal motif (call before large transfer) ---
    for hit in detect_call_before_transfer(conn):
        key = f"{hit['call_record_id']}_{hit['transfer_record_id']}"
        leads.append({
            "lead_id": _lead_id("CALL_BEFORE_TRANSFER", key),
            "lead_type": "CALL_BEFORE_TRANSFER",
            "severity": "HIGH",
            "entities_involved": hit["call_phones"] + hit["transfer_accounts"],
            "requires_human_verification": True,
            "summary": f"A {hit['minutes_between']}-minute call preceded a transfer of {hit['transfer_amount']:,.0f} "
                       f"between accounts linked (via FIR co-occurrence) to the same two phones -- "
                       f"consistent with a phone-solicited fraud pattern.",
            "signals": [
                {"signal": "minutes_between_call_and_transfer", "value": hit["minutes_between"]},
                {"signal": "transfer_amount", "value": hit["transfer_amount"]},
                {"signal": "amount_threshold_used", "value": hit["amount_threshold_used"]},
            ],
            "source_record_ids": [hit["call_record_id"], hit["transfer_record_id"]],
            "created_at": _now(),
        })

    return leads


def build_robbery_theft_physical_leads(conn):
    """Physical-evidence leads for Robbery/Theft: Vahan Samanvay-style
    stolen<->recovered vehicle links, non-vehicle property matches, and
    lingering-property (BNSS 497/503) flags. A vehicle/property match
    genuinely spans two case files (the stolen report's case and the
    recovery memo's case, often different) -- carried in case_ids (plural)
    since a single case_id can't represent that; case_id is set to the
    stolen-side case for any code that only reads the singular field."""
    leads = []
    severity_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    for hit in detect_vehicle_links(conn):
        severity = "HIGH" if hit["tampering_suspected"] else "MEDIUM"
        fields = ", ".join(hit["matched_fields"])
        tamper_note = (
            " Chassis/registration/engine fields disagree in a way consistent with a re-identified "
            "('re-birthed') vehicle, not a simple clerical mismatch."
            if hit["tampering_suspected"] else ""
        )
        leads.append({
            "lead_id": _lead_id("ROBBERY_VEHICLE_LINK", f"{hit['stolen_item_id']}_{hit['recovered_item_id']}"),
            "lead_type": "ROBBERY_VEHICLE_LINK",
            "severity": severity,
            "case_id": hit["stolen_case_id"],
            "case_ids": sorted({hit["stolen_case_id"], hit["recovered_case_id"]}),
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"{hit['vehicle_type']} reported stolen (item {hit['stolen_item_id']}) matches a "
                       f"recovered vehicle (item {hit['recovered_item_id']}) on {fields} -- the same "
                       f"vehicle-type-plus-two-identifiers rule NCRB's Vahan Samanvay system uses, "
                       f"partial-number matches included.{tamper_note}",
            "signals": [{"signal": "matched_fields", "value": hit["matched_fields"]},
                        {"signal": "tampering_suspected", "value": hit["tampering_suspected"]}],
            "source_record_ids": [hit["stolen_item_id"], hit["recovered_item_id"]],
            "created_at": _now(),
        })

    for hit in detect_property_item_matches(conn):
        is_link = hit["match_type"] == "LINK"
        leads.append({
            "lead_id": _lead_id("ROBBERY_PROPERTY_MATCH", f"{hit['stolen_item_id']}_{hit['recovered_item_id']}"),
            "lead_type": "ROBBERY_PROPERTY_MATCH",
            "severity": "HIGH" if is_link else "MEDIUM",
            "case_id": hit["stolen_case_id"],
            "case_ids": sorted({hit["stolen_case_id"], hit["recovered_case_id"]}),
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": (
                f"Item '{hit['description']}' reported stolen (identifier {hit['identifier']}) exactly "
                f"matches a recovered item's identifier -- a direct property link."
                if is_link else
                f"Item '{hit['description']}' reported stolen (value {hit['stolen_value']:,.0f}) matches "
                f"a recovered item by description, with recovered value {hit['recovered_value']:,.0f} "
                f"within the tolerance band -- a candidate match, weaker than an exact identifier link."
            ),
            "signals": [{"signal": "match_basis", "value": hit["match_basis"]}],
            "source_record_ids": [hit["stolen_item_id"], hit["recovered_item_id"]],
            "created_at": _now(),
        })

    for hit in detect_lingering_property(conn):
        leads.append({
            "lead_id": _lead_id("ROBBERY_LINGERING_PROPERTY", hit["property_id"]),
            "lead_type": "ROBBERY_LINGERING_PROPERTY",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Recovered property {hit['property_id']} has sat {hit['days_elapsed']} days since "
                       f"seizure with no court-disposal record -- a BNSS 497/503 (interim custody/"
                       f"disposal of case property) lapse worth checking against the case file.",
            "signals": [{"signal": "days_elapsed", "value": hit["days_elapsed"]}],
            "source_record_ids": [hit["property_id"]],
            "created_at": _now(),
        })

    return leads


def build_robbery_theft_digital_leads(conn):
    """Digital-evidence leads for Robbery/Theft: NCRB IIF-II MO-series
    detection, escalated to a BNS s.112 candidate once enough accused are
    shared across the matched FIRs."""
    leads = []
    for hit in detect_mo_series(conn):
        lead_type = "ROBBERY_MO_SERIES_S112_CANDIDATE" if hit["bns_112_candidate"] else "ROBBERY_MO_SERIES"
        s112_note = (
            f" {len(hit['shared_accused'])} accused are shared across both FIRs, clearing the BNS s.112 "
            f"(petty organised crime) bar -- no charge-sheet-count history required for this section."
            if hit["bns_112_candidate"] else ""
        )
        leads.append({
            "lead_id": _lead_id(lead_type, f"{hit['fir_a']}_{hit['fir_b']}"),
            "lead_type": lead_type,
            "severity": "HIGH" if hit["bns_112_candidate"] else "MEDIUM",
            "case_id": hit["case_a"],
            "case_ids": sorted({hit["case_a"], hit["case_b"]}),
            "entities_involved": list(hit["shared_accused"]),
            "requires_human_verification": True,
            "summary": f"FIRs {hit['fir_a']} and {hit['fir_b']}, {hit['days_apart']} days apart, match on "
                       f"{len(hit['matched_fields'])} of the 6 NCRB IIF-II modus-operandi fields "
                       f"({', '.join(hit['matched_fields'])}) -- a candidate crime series.{s112_note}",
            "signals": [{"signal": "matched_fields", "value": hit["matched_fields"]},
                        {"signal": "days_apart", "value": hit["days_apart"]},
                        {"signal": "shared_accused_count", "value": len(hit["shared_accused"])}],
            "source_record_ids": [hit["fir_a"], hit["fir_b"]],
            "created_at": _now(),
        })
    return leads


def build_narcotics_physical_leads(conn):
    """Physical-evidence leads for the Narcotics case type: NDPS s.52A /
    Test-Memo chain-of-custody compliance flags (see
    app/detectors/narcotics_physical.py). These are record-level leads
    (property_id/case_id), not graph-entity leads -- Physical evidence
    doesn't sit on the entity graph the way Digital evidence does, so each
    lead carries its own case_id for case-scoped filtering instead of
    relying on entities_involved."""
    leads = []
    severity_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    for hit in detect_ndps_compliance_flags(conn):
        top_severity = max((f["severity"] for f in hit["flags"]), key=lambda s: severity_rank.get(s, 0))
        flag_names = ", ".join(f["flag"] for f in hit["flags"])
        leads.append({
            "lead_id": _lead_id("NDPS_COMPLIANCE", hit["memo_id"]),
            "lead_type": "NDPS_COMPLIANCE",
            "severity": top_severity,
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"NDPS Test Memo {hit['memo_id']} (crime no. {hit['crime_no']}, "
                       f"{hit['drug_description']}) has {len(hit['flags'])} chain-of-custody/compliance "
                       f"flag(s): {flag_names}. Per Bharat Aambale v. State of Chhattisgarh, a procedural "
                       f"lapse alone is not fatal -- it must be checked against the actual case file.",
            "signals": [{"signal": f["flag"], "value": f["detail"]} for f in hit["flags"]],
            "source_record_ids": [hit["property_id"], hit["memo_id"]],
            "created_at": _now(),
        })

    return leads


def build_assault_homicide_physical_leads(conn):
    """Physical-evidence leads for Assault/Homicide: inquest/post-mortem
    procedural compliance and forensic cross-exhibit matching. See
    app/detectors/assault_homicide_physical.py for the per-signal legal/
    forensic grounding. A forensic match can span two different case
    files (e.g. a fingerprint tying a current homicide to an unresolved
    cold case), so those leads carry case_ids (plural) the same way the
    Robbery/Theft vehicle/property-match leads do."""
    leads = []

    for hit in detect_inquest_witness_violations(conn):
        leads.append({
            "lead_id": _lead_id("INQUEST_WITNESS_VIOLATION", hit["inquest_id"]),
            "lead_type": "INQUEST_WITNESS_VIOLATION",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Inquest {hit['inquest_id']} recorded only {hit['witness_count']} witness(es), "
                       f"below the BNSS s.194 (<- CrPC s.174) requirement of {hit['required']} 'respectable "
                       f"inhabitants' present at the inquest.",
            "signals": [{"signal": "witness_count", "value": hit["witness_count"]}],
            "source_record_ids": [hit["inquest_id"]],
            "created_at": _now(),
        })

    for hit in detect_injury_list_mismatch(conn):
        leads.append({
            "lead_id": _lead_id("INQUEST_PM_INJURY_MISMATCH", f"{hit['inquest_id']}_{hit['pm_id']}"),
            "lead_type": "INQUEST_PM_INJURY_MISMATCH",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Inquest {hit['inquest_id']} and post-mortem {hit['pm_id']} disagree on the "
                       f"injury list -- missing from inquest: {hit['missing_from_inquest'] or 'none'}; "
                       f"missing from post-mortem: {hit['missing_from_pm'] or 'none'}.",
            "signals": [{"signal": "missing_from_inquest", "value": hit["missing_from_inquest"]},
                        {"signal": "missing_from_pm", "value": hit["missing_from_pm"]}],
            "source_record_ids": [hit["inquest_id"], hit["pm_id"]],
            "created_at": _now(),
        })

    for hit in detect_postmortem_missing_timing_fields(conn):
        leads.append({
            "lead_id": _lead_id("POSTMORTEM_MISSING_TIMING_FIELDS", hit["pm_id"]),
            "lead_type": "POSTMORTEM_MISSING_TIMING_FIELDS",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Post-mortem {hit['pm_id']} is missing {', '.join(hit['missing_fields'])} -- "
                       f"NHRC Model Autopsy Form fields used to estimate time of death.",
            "signals": [{"signal": "missing_fields", "value": hit["missing_fields"]}],
            "source_record_ids": [hit["pm_id"]],
            "created_at": _now(),
        })

    for hit in detect_custodial_death_intimation_violation(conn):
        detail = ("no intimation_ts recorded at all" if hit["violation"] == "INTIMATION_MISSING"
                  else f"intimated {hit['hours_elapsed']} hours after death")
        leads.append({
            "lead_id": _lead_id("CUSTODIAL_DEATH_INTIMATION_VIOLATION", hit["inquest_id"]),
            "lead_type": "CUSTODIAL_DEATH_INTIMATION_VIOLATION",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Custodial death, inquest {hit['inquest_id']}: {detail} -- a BNSS s.196 "
                       f"(<- CrPC s.176) intimation lapse.",
            "signals": [{"signal": "violation", "value": hit["violation"]},
                        {"signal": "hours_elapsed", "value": hit["hours_elapsed"]}],
            "source_record_ids": [hit["inquest_id"]],
            "created_at": _now(),
        })

    for hit in detect_mlc_classification_inconsistency(conn):
        leads.append({
            "lead_id": _lead_id("MLC_CLASSIFICATION_INCONSISTENCY", hit["mlc_id"]),
            "lead_type": "MLC_CLASSIFICATION_INCONSISTENCY",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"MLC {hit['mlc_id']}: {hit['issue']} (follow_up_days={hit['follow_up_days']}) -- "
                       f"worth re-checking the BNS s.116 (<- IPC s.320) classification against the actual "
                       f"injury list, not a reclassification the platform performs itself.",
            "signals": [{"signal": "issue", "value": hit["issue"]},
                        {"signal": "follow_up_days", "value": hit["follow_up_days"]}],
            "source_record_ids": [hit["mlc_id"]],
            "created_at": _now(),
        })

    for hit in detect_forensic_matches(conn):
        case_ids = sorted({hit["case_id_a"], hit["case_id_b"]})
        if hit["finding_type"] == "LINK" and hit["match_type"] == "FINGERPRINT":
            summary = (f"Fingerprint NFN {hit['identifier_value']} links exhibit {hit['exhibit_a']} "
                       f"(case {hit['case_id_a']}) to exhibit {hit['exhibit_b']} (case {hit['case_id_b']}) "
                       f"-- an AFIS/NAFIS database hit.")
            severity = "HIGH"
        elif hit["finding_type"] == "CANDIDATE_EXAMINER_ASSERTED":
            summary = (f"Ballistics examiner {hit.get('examiner_name', 'unknown')} opines exhibit "
                       f"{hit['exhibit_a']} (case {hit['case_id_a']}) matches exhibit {hit['exhibit_b']} "
                       f"(case {hit['case_id_b']}). {hit['note']}")
            severity = "MEDIUM"
        else:
            summary = (f"DNA report {hit.get('fsl_report_no', '')} matches exhibit {hit['exhibit_a']} "
                       f"(case {hit['case_id_a']}) to exhibit {hit['exhibit_b']} (case {hit['case_id_b']}).")
            severity = "HIGH"
        leads.append({
            "lead_id": _lead_id(f"FORENSIC_{hit['match_type']}_MATCH" if hit["match_type"] != "BALLISTICS"
                                 else "FORENSIC_BALLISTICS_EXAMINER_ASSERTED",
                                 f"{hit['exhibit_a']}_{hit['exhibit_b']}"),
            "lead_type": (f"FORENSIC_{hit['match_type']}_MATCH" if hit["match_type"] != "BALLISTICS"
                          else "FORENSIC_BALLISTICS_EXAMINER_ASSERTED"),
            "severity": severity,
            "case_id": hit["case_id_a"],
            "case_ids": case_ids,
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": summary,
            "signals": [{"signal": "finding_type", "value": hit["finding_type"]}],
            "source_record_ids": [hit["exhibit_a"], hit["exhibit_b"]],
            "created_at": _now(),
        })

    for hit in detect_forensic_confidence_misuse(conn):
        leads.append({
            "lead_id": _lead_id("FORENSIC_CONFIDENCE_MISUSE", hit["match_id"]),
            "lead_type": "FORENSIC_CONFIDENCE_MISUSE",
            "severity": "HIGH",
            "case_id": hit["case_id_a"],
            "case_ids": sorted({hit["case_id_a"], hit["case_id_b"]}),
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"{hit['match_type']} match {hit['match_id']} is categorically "
                       f"'{hit['match_confidence_category']}' but the case file treats it as a positive "
                       f"match -- Indian FSL {hit['match_type']} results are categorical, never a numeric "
                       f"likelihood the case file can round up.",
            "signals": [{"signal": "match_confidence_category", "value": hit["match_confidence_category"]}],
            "source_record_ids": [hit["match_id"]],
            "created_at": _now(),
        })

    return leads


def build_assault_homicide_digital_leads(conn):
    """Digital-evidence leads for Assault/Homicide: BSA s.63/Evidence Act
    s.65B(4) certification status of tower/cell-site records, and the
    joint Physical+Digital spatio-temporal correlation signal. See
    app/detectors/assault_homicide_digital.py for the legal grounding."""
    leads = []

    for hit in detect_uncertified_tower_evidence(conn):
        leads.append({
            "lead_id": _lead_id("UNCERTIFIED_TOWER_EVIDENCE", hit["record_id"]),
            "lead_type": "UNCERTIFIED_TOWER_EVIDENCE",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Tower/cell-site record {hit['record_id']} for phone {hit['phone']} at "
                       f"'{hit['locality_name']}' ({hit['timestamp']}) has no BSA s.63/Evidence Act "
                       f"s.65B(4) certificate -- per Rahil v. State (NCT of Delhi), 2025 INSC 858, "
                       f"this is a candidate lead requiring corroboration and certification, never "
                       f"usable proof as it stands.",
            "signals": [{"signal": "is_certified_65b", "value": False}],
            "source_record_ids": [hit["record_id"]],
            "created_at": _now(),
        })

    for hit in detect_spatiotemporal_correlation(conn):
        cert_note = "" if hit["is_certified_65b"] else " (record is NOT yet s.65B(4)-certified)"
        leads.append({
            "lead_id": _lead_id("SPATIOTEMPORAL_TOWER_CORRELATION", f"{hit['inquest_id']}_{hit['record_id']}"),
            "lead_type": "SPATIOTEMPORAL_TOWER_CORRELATION",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Phone {hit['phone']} ping at '{hit['locality_name']}' is within "
                       f"{hit['hours_from_death']} hours of the recorded time of death at "
                       f"'{hit['place_of_occurrence']}' (inquest {hit['inquest_id']}){cert_note}.",
            "signals": [{"signal": "hours_from_death", "value": hit["hours_from_death"]},
                        {"signal": "is_certified_65b", "value": hit["is_certified_65b"]}],
            "source_record_ids": [hit["inquest_id"], hit["record_id"]],
            "created_at": _now(),
        })

    return leads


def build_trafficking_physical_leads(conn):
    """Physical-evidence leads for Trafficking/Missing Person: UIDB<->
    missing-person candidate matching, ZIPNET's own ignored-match signal,
    and DNA-sample-chain compliance. A candidate match and an ignored
    match both genuinely span two case files (the UIDB's case and the
    missing-person report's case, which can differ), so those leads carry
    case_ids (plural) the same way the other cross-case detectors do."""
    leads = []

    for hit in detect_uidb_missing_person_candidates(conn):
        case_ids = sorted({hit["case_id"], hit["missing_person_case_id"]})
        leads.append({
            "lead_id": _lead_id("UIDB_MISSING_PERSON_CANDIDATE_MATCH", f"{hit['uidb_id']}_{hit['missing_person_id']}"),
            "lead_type": "UIDB_MISSING_PERSON_CANDIDATE_MATCH",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "case_ids": case_ids,
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Unidentified body {hit['uidb_id']} matches missing-person report "
                       f"{hit['missing_person_id']} on sex, age range, height, dress colour "
                       f"({', '.join(hit['shared_dress_colours'])}) and district -- a candidate "
                       f"identification, never a confirmed one, per the ZIPNET-modeled matching rule.",
            "signals": [{"signal": "shared_dress_colours", "value": hit["shared_dress_colours"]}],
            "source_record_ids": [hit["uidb_id"], hit["missing_person_id"]],
            "created_at": _now(),
        })

    for hit in detect_ignored_zipnet_match(conn):
        case_ids = sorted({hit["case_id"], hit["missing_person_case_id"]})
        leads.append({
            "lead_id": _lead_id("UIDB_IGNORED_ZIPNET_MATCH", f"{hit['uidb_id']}_{hit['missing_person_id']}"),
            "lead_type": "UIDB_IGNORED_ZIPNET_MATCH",
            "severity": "HIGH",
            "case_id": hit["case_id"],
            "case_ids": case_ids,
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"UIDB {hit['uidb_id']} already carries ZIPNET's own matched_missing_serial_no "
                       f"pointing to missing-person report {hit['missing_person_id']}, but that case is "
                       f"still shown OPEN -- the match exists in the record, the case file just hasn't "
                       f"caught up to it.",
            "signals": [{"signal": "missing_person_status", "value": "OPEN"}],
            "source_record_ids": [hit["uidb_id"], hit["missing_person_id"]],
            "created_at": _now(),
        })

    for hit in detect_unsampled_body(conn):
        leads.append({
            "lead_id": _lead_id("UIDB_UNSAMPLED_BODY", hit["pm_id"]),
            "lead_type": "UIDB_UNSAMPLED_BODY",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"Unidentified body {hit['uidb_id']} has a post-mortem report ({hit['pm_id']}) but "
                       f"no DNA sample record at all -- a one-time, perishable identification opportunity "
                       f"that the Rajasthan HC/Lokniti Foundation preservation logic says should not be lost.",
            "signals": [{"signal": "has_dna_sample", "value": False}],
            "source_record_ids": [hit["uidb_id"], hit["pm_id"]],
            "created_at": _now(),
        })

    for hit in detect_late_dna_dispatch(conn):
        leads.append({
            "lead_id": _lead_id("UIDB_LATE_DNA_DISPATCH", hit["sample_id"]),
            "lead_type": "UIDB_LATE_DNA_DISPATCH",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"DNA sample {hit['sample_id']} was dispatched {hit['hours_elapsed']} hours after "
                       f"collection with no delay reason recorded -- past Kattavellai's own 48-hour "
                       f"dispatch direction.",
            "signals": [{"signal": "hours_elapsed", "value": hit["hours_elapsed"]}],
            "source_record_ids": [hit["sample_id"]],
            "created_at": _now(),
        })

    for hit in detect_weak_dna_conclusion_relied_alone(conn):
        leads.append({
            "lead_id": _lead_id("UIDB_WEAK_DNA_CONCLUSION_RELIED_ALONE", hit["sample_id"]),
            "lead_type": "UIDB_WEAK_DNA_CONCLUSION_RELIED_ALONE",
            "severity": "MEDIUM",
            "case_id": hit["case_id"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"DNA sample {hit['sample_id']} ({hit['conclusion_category']}, expert_examined="
                       f"{hit['expert_examined']}) is the identification basis behind UIDB {hit['uidb_id']}'s "
                       f"ZIPNET match, but per Nantu Nath a weak or unexamined conclusion should never "
                       f"stand alone as identification.",
            "signals": [{"signal": "conclusion_category", "value": hit["conclusion_category"]},
                        {"signal": "expert_examined", "value": hit["expert_examined"]}],
            "source_record_ids": [hit["sample_id"], hit["uidb_id"]],
            "created_at": _now(),
        })

    return leads


def build_organized_crime_digital_leads(conn):
    """Digital-evidence leads for Organized Crime: cross-case identifier
    reuse, shared-infrastructure evidence, and the BNS s.111/MCOCA
    charge-sheet legal gate. See app/detectors/organized_crime_digital.py
    for the full legal grounding. All of these genuinely span multiple
    case files, so every lead here carries case_ids (plural)."""
    leads = []

    for hit in detect_cross_case_identifier_links(conn):
        lead_type = "INTERSTATE_IDENTIFIER_LINKAGE_ALERT" if hit["interstate_alert"] else "CROSS_CASE_IDENTIFIER_LINK"
        alert_note = (
            f" Appearing in {len(hit['fir_nos'])} FIRs across {len(hit['police_stations'])} police "
            f"station(s) clears the interstate-linkage bar -- a Samanvaya-style alert, not just a link."
            if hit["interstate_alert"] else ""
        )
        leads.append({
            "lead_id": _lead_id(lead_type, f"{hit['identifier_type']}_{hit['value']}"),
            "lead_type": lead_type,
            "severity": "HIGH" if hit["interstate_alert"] else "MEDIUM",
            "case_id": hit["case_ids"][0],
            "case_ids": hit["case_ids"],
            "entities_involved": [],
            "requires_human_verification": True,
            "summary": f"{hit['identifier_type']} '{hit['value']}' recurs across {len(hit['fir_nos'])} FIRs "
                       f"({', '.join(hit['fir_nos'])}) spanning {len(hit['case_ids'])} case file(s).{alert_note}",
            "signals": [{"signal": "fir_count", "value": len(hit["fir_nos"])},
                        {"signal": "police_station_count", "value": len(hit["police_stations"])}],
            "source_record_ids": hit["fir_nos"],
            "created_at": _now(),
        })

    for hit in detect_shared_infrastructure(conn):
        leads.append({
            "lead_id": _lead_id("SHARED_INFRASTRUCTURE_LINK", f"{hit['identifier_type']}_{hit['value']}"),
            "lead_type": "SHARED_INFRASTRUCTURE_LINK",
            "severity": "HIGH",
            "case_id": hit["case_ids"][0],
            "case_ids": hit["case_ids"],
            "entities_involved": hit["accused_entity_ids"],
            "requires_human_verification": True,
            "summary": f"{len(hit['accused_entity_ids'])} distinct accused are tied to the same "
                       f"{hit['identifier_type']} '{hit['value']}' across {len(hit['fir_nos'])} FIRs -- "
                       f"same-cell co-membership evidence, independent of whether they were ever "
                       f"co-accused on the same charge-sheet.",
            "signals": [{"signal": "accused_count", "value": len(hit["accused_entity_ids"])}],
            "source_record_ids": hit["fir_nos"],
            "created_at": _now(),
        })

    for hit in detect_syndicate_charge_sheet_threshold(conn):
        if not hit["threshold_met"]:
            continue
        member_labels = [entity_label(conn, m) for m in hit["syndicate_members"]]
        leads.append({
            "lead_id": _lead_id("SYNDICATE_S111_THRESHOLD_MET", "_".join(hit["syndicate_members"])),
            "lead_type": "SYNDICATE_S111_THRESHOLD_MET",
            "severity": "HIGH",
            "case_id": None,
            "entities_involved": hit["syndicate_members"],
            "requires_human_verification": True,
            "summary": f"Syndicate {{{', '.join(member_labels)}}} clears {hit['qualifying_count']} "
                       f"qualifying charge-sheets ({', '.join(hit['qualifying_charge_sheet_ids'])}) within "
                       f"the preceding 10 years -- the BNS s.111/MCOCA 'continuing unlawful activity' "
                       f"threshold, counted per Zakir Abdul Mirajkar v. State of Maharashtra PER SYNDICATE, "
                       f"not per individual accused. A court determination, never an automated one.",
            "signals": [{"signal": "qualifying_charge_sheet_count", "value": hit["qualifying_count"]}],
            "source_record_ids": hit["qualifying_charge_sheet_ids"],
            "created_at": _now(),
        })

    return leads


def build_all_leads(conn):
    return (
        build_leads(conn) + build_narcotics_physical_leads(conn)
        + build_robbery_theft_physical_leads(conn) + build_robbery_theft_digital_leads(conn)
        + build_assault_homicide_physical_leads(conn) + build_assault_homicide_digital_leads(conn)
        + build_trafficking_physical_leads(conn) + build_organized_crime_digital_leads(conn)
    )


if __name__ == "__main__":
    conn = get_connection()
    leads = build_all_leads(conn)
    print(json.dumps(leads, indent=2, default=str))
    print(f"\n\nTotal leads: {len(leads)}")
