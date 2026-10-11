"""
Case-type gating: a detector module only produces leads for a case once an
investigator has CONFIRMED the case type that module belongs to.

The classifier only ever SUGGESTS (see classification/case_type_classifier.py);
without this layer a SUGGESTED or REJECTED case type would have no effect on
anything, so "human confirms before modules activate" would be a docstring,
not behaviour. Every lead_type is mapped to the case type it is evidence for
by CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE -- the same registry the classifier uses,
so "the classifier suggested it" and "the Leads tab shows it" cannot drift.

Lead types with no entry in that registry (BROKER_BRIDGE and the two IMEI
device-continuity leads) are cross-cutting: they apply to any case type, so
they are always active.

The classifier itself deliberately keeps reading UNGATED leads -- it has to
see what the detectors found in order to suggest anything at all.
"""
from collections import defaultdict

from app.config import CASE_TYPES, CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE
from app.graph.case_view import get_case_entity_ids
from app.evidence.engine import build_all_leads

# Lead types that apply to every case type, so they are never gated.
CROSS_CUTTING_LEAD_TYPES = {"BROKER_BRIDGE", "IMEI_MSISDN_MAPPING", "IMEI_CORROBORATED_BURNER_SWAP"}


def relevant_leads(conn, case_id: str) -> list:
    """Every lead (ungated) that touches this case: via the case's entities,
    or a record-level lead carrying the case's own id. Same scoping the
    classifier uses, so both always agree on what "this case's leads" means."""
    case_node_ids = get_case_entity_ids(conn, case_id)
    return [
        l for l in build_all_leads(conn)
        if case_node_ids.intersection(l["entities_involved"]) or l.get("case_id") == case_id
        or case_id in l.get("case_ids", ())
    ]


def lead_case_type(lead_type: str):
    """The case type a lead is evidence for, or None if it is cross-cutting."""
    return CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE.get(lead_type)


def case_type_statuses(conn, case_id: str) -> dict:
    """{case_type: status} for every case_case_types row on this case."""
    return {
        r["case_type"]: r["status"]
        for r in conn.execute("SELECT case_type, status FROM case_case_types WHERE case_id=?", (case_id,)).fetchall()
    }


def split_by_activation(conn, case_id: str, leads: list):
    """Partitions a case's relevant leads into (active, held_back).

    active    -- cross-cutting leads, plus leads whose case type is CONFIRMED
                 on this case.
    held_back -- leads whose case type is SUGGESTED, REJECTED, or has no row
                 at all. Each held-back lead is returned unchanged; callers
                 that need to say *why* use lead_case_type().
    """
    statuses = case_type_statuses(conn, case_id)
    active, held_back = [], []
    for lead in leads:
        case_type = lead_case_type(lead["lead_type"])
        if case_type is None or statuses.get(case_type) == "CONFIRMED":
            active.append(lead)
        else:
            held_back.append(lead)
    return active, held_back


def module_status(conn, case_id: str, relevant_leads: list) -> dict:
    """Read model for the UI: for each of the 6 case types, its status on this
    case and how many of this case's leads it is currently showing versus
    holding back (in total and per lead type), plus the always-on
    cross-cutting leads per lead type."""
    statuses = case_type_statuses(conn, case_id)
    per_type = {ct: defaultdict(lambda: {"active": 0, "held_back": 0}) for ct in CASE_TYPES}
    cross_cutting = defaultdict(int)

    for lead in relevant_leads:
        case_type = lead_case_type(lead["lead_type"])
        if case_type is None:
            cross_cutting[lead["lead_type"]] += 1
            continue
        bucket = "active" if statuses.get(case_type) == "CONFIRMED" else "held_back"
        per_type[case_type][lead["lead_type"]][bucket] += 1

    modules = []
    for case_type in CASE_TYPES:
        counts = {lt: dict(c) for lt, c in sorted(per_type[case_type].items())}
        modules.append({
            "case_type": case_type,
            "status": statuses.get(case_type, "NOT_SUGGESTED"),
            "active_leads": sum(c["active"] for c in counts.values()),
            "held_back_leads": sum(c["held_back"] for c in counts.values()),
            "lead_type_counts": counts,
        })
    return {
        "case_id": case_id,
        "modules": modules,
        "cross_cutting_leads": sum(cross_cutting.values()),
        "cross_cutting_lead_type_counts": dict(sorted(cross_cutting.items())),
    }
