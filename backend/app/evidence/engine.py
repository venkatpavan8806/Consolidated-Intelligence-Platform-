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
from app.detectors.women_safety import detect_transporter_candidates, detect_repeat_locations


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


def build_women_safety_leads(conn):
    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    result = detect_transporter_candidates(g, membership)
    leads = []

    for eid, info in result["recruiters"].items():
        leads.append({
            "lead_id": _lead_id("WOMEN_SAFETY_RECRUITER", eid),
            "lead_type": "WOMEN_SAFETY_RECRUITER",
            "severity": "HIGH",
            "entities_involved": [eid] + info["low_degree_contacts"],
            "requires_human_verification": True,
            "summary": f"{entity_label(conn, eid)} fans out to {info['fanout_count']} low-degree contacts "
                       f"within one community -- matches the recruiter fan-out pattern. This heuristic is "
                       f"intentionally generic and may also match unrelated hub structures (e.g. a "
                       f"burner-rotation phone); human verification is required before any action.",
            "signals": [{"signal": "low_degree_fanout_count", "value": info["fanout_count"]}],
            "source_record_ids": [],
            "created_at": _now(),
        })

    for eid, info in result["transporters"].items():
        matches = info["detail"].get("STRUCTURAL_BRIDGE_PATH", {}).get("matches", [])
        community_info = info["detail"].get("COMMUNITY_BRIDGE")
        summary_parts = []
        if matches:
            summary_parts.append(
                f"low-degree/low-volume node bridging {len(matches)} recruiter contact set(s) to a "
                f"comparatively high-degree node on the other side"
            )
        if community_info:
            summary_parts.append(
                f"neighbours span {len(community_info['neighbor_communities'])} separate communities"
            )
        leads.append({
            "lead_id": _lead_id("WOMEN_SAFETY_TRANSPORTER", eid),
            "lead_type": "WOMEN_SAFETY_TRANSPORTER",
            "severity": "HIGH",
            "entities_involved": [eid],
            "requires_human_verification": True,
            "method_provenance": info["methods"],
            "summary": f"{entity_label(conn, eid)} flagged as a possible transporter/intermediary: " +
                       "; ".join(summary_parts) + ".",
            "signals": [{"signal": "method", "value": m} for m in info["methods"]],
            "source_record_ids": [],
            "created_at": _now(),
        })

    for loc in detect_repeat_locations(conn):
        leads.append({
            "lead_id": _lead_id("REPEAT_LOCATION", loc["entity_id"]),
            "lead_type": "REPEAT_LOCATION",
            "severity": "MEDIUM",
            "entities_involved": [loc["entity_id"]] + loc["linked_entities"],
            "requires_human_verification": True,
            "summary": f"Location '{loc['location']}' is named across {loc['independent_source_count']} "
                       f"independently-sourced records tied to different entities -- worth cross-checking "
                       f"as a shared operational location.",
            "signals": [{"signal": "independent_source_count", "value": loc["independent_source_count"]}],
            "source_record_ids": loc["source_records"],
            "created_at": _now(),
        })

    return leads


def build_all_leads(conn):
    return build_leads(conn) + build_women_safety_leads(conn)


if __name__ == "__main__":
    conn = get_connection()
    leads = build_all_leads(conn)
    print(json.dumps(leads, indent=2, default=str))
    print(f"\n\nTotal leads: {len(leads)}")
