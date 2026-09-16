"""
Role typing and utility-node exclusion. Runs AFTER entity resolution and
BEFORE any graph/analytics stage, and its output (is_official / is_utility on
the entities table) is the single source of truth every ranking function
must consult -- see gotcha #4: it is easy to apply an exclusion rule in two
of three analytics functions and let a utility hub silently top the one you
missed. Here the exclusion set is computed ONCE and every analytics function
in app/graph/analytics.py builds its working graph via
build_analysis_subgraph(), which removes excluded nodes structurally rather
than relying on each function to remember to filter.
"""
import json
from collections import defaultdict

from app.db.schema import get_connection
from app.config import UTILITY_MIN_IN_DEGREE, UTILITY_MAX_OUT_DEGREE


def apply_role_exclusion(conn):
    """Flag PERSON entities as official using their extracted FIR ROLE field
    (never by matching a keyword against the entity's own NAME string --
    a person's name will never literally contain the word "inspector",
    see gotcha #3), then propagate the flag to any PHONE/ACCOUNT/VEHICLE
    entity that was mentioned in the SAME FIR record as an official mention
    (that identifier is that official's own contact, not a suspect's)."""
    cur = conn.cursor()
    persons = cur.execute("SELECT entity_id, attributes_json FROM entities WHERE entity_type='PERSON'").fetchall()
    official_entity_ids = []
    for p in persons:
        attrs = json.loads(p["attributes_json"])
        if "OFFICIAL" in attrs.get("fir_roles", []):
            official_entity_ids.append(p["entity_id"])
    if official_entity_ids:
        cur.executemany("UPDATE entities SET is_official = 1 WHERE entity_id = ?",
                         [(eid,) for eid in official_entity_ids])

    if not official_entity_ids:
        return {"official_persons": 0, "official_linked_identifiers": 0}

    placeholders = ",".join("?" for _ in official_entity_ids)
    official_mention_ids = [
        row["mention_id"] for row in cur.execute(
            f"SELECT mention_id FROM mention_entity_map WHERE entity_id IN ({placeholders})",
            official_entity_ids,
        ).fetchall()
    ]
    if not official_mention_ids:
        return {"official_persons": len(official_entity_ids), "official_linked_identifiers": 0}

    mp = ",".join("?" for _ in official_mention_ids)
    official_records = {
        row["source_record_id"] for row in cur.execute(
            f"SELECT DISTINCT source_record_id FROM entity_mentions WHERE mention_id IN ({mp})",
            official_mention_ids,
        ).fetchall()
    }
    if not official_records:
        return {"official_persons": len(official_entity_ids), "official_linked_identifiers": 0}

    rp = ",".join("?" for _ in official_records)
    identifier_mentions = cur.execute(
        f"""SELECT mention_id FROM entity_mentions
            WHERE source_record_id IN ({rp}) AND entity_type IN ('PHONE','ACCOUNT','VEHICLE')""",
        list(official_records),
    ).fetchall()
    identifier_mention_ids = [r["mention_id"] for r in identifier_mentions]
    linked_entity_ids = set()
    if identifier_mention_ids:
        imp = ",".join("?" for _ in identifier_mention_ids)
        for row in cur.execute(
            f"SELECT DISTINCT entity_id FROM mention_entity_map WHERE mention_id IN ({imp})",
            identifier_mention_ids,
        ).fetchall():
            linked_entity_ids.add(row["entity_id"])

    if linked_entity_ids:
        cur.executemany("UPDATE entities SET is_official = 1 WHERE entity_id = ?",
                         [(eid,) for eid in linked_entity_ids])

    return {"official_persons": len(official_entity_ids), "official_linked_identifiers": len(linked_entity_ids)}


def apply_utility_exclusion(conn):
    """Structural detection: a node with high in-degree and near-zero
    out-degree in the call graph behaves like a customer-care / utility
    line, not a person of interest -- regardless of call volume."""
    cur = conn.cursor()
    in_callers = defaultdict(set)
    out_callees = defaultdict(set)
    for row in cur.execute("SELECT caller, callee FROM cdr_records").fetchall():
        in_callers[row["callee"]].add(row["caller"])
        out_callees[row["caller"]].add(row["callee"])

    utility_numbers = []
    all_numbers = set(in_callers) | set(out_callees)
    for number in all_numbers:
        in_deg = len(in_callers.get(number, set()))
        out_deg = len(out_callees.get(number, set()))
        if in_deg >= UTILITY_MIN_IN_DEGREE and out_deg <= UTILITY_MAX_OUT_DEGREE:
            utility_numbers.append(number)

    if utility_numbers:
        eids = []
        for number in utility_numbers:
            row = cur.execute(
                "SELECT entity_id FROM entities WHERE entity_type='PHONE' AND canonical_value=?",
                (number,),
            ).fetchone()
            if row:
                eids.append(row["entity_id"])
        cur.executemany("UPDATE entities SET is_utility = 1 WHERE entity_id = ?", [(e,) for e in eids])

    return {"utility_numbers_flagged": len(utility_numbers)}


def run_exclusion():
    conn = get_connection()
    role_stats = apply_role_exclusion(conn)
    utility_stats = apply_utility_exclusion(conn)
    conn.commit()
    conn.close()
    return {**role_stats, **utility_stats}


def get_exclusion_set(conn) -> set:
    """The single source of truth for which entity_ids must never appear in
    a ranking. Every analytics function should call build_analysis_subgraph
    (see app/graph/analytics.py) rather than re-implementing this filter."""
    rows = conn.execute("SELECT entity_id FROM entities WHERE is_official = 1 OR is_utility = 1").fetchall()
    return {r["entity_id"] for r in rows}


if __name__ == "__main__":
    print(json.dumps(run_exclusion(), indent=2))
