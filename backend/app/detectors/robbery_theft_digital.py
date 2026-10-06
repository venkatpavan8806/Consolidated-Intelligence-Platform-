"""
Robbery/Theft Digital-evidence detector: MO-series detection over the
structured NCRB IIF-II Crime Details Form fields (crime_mo_record), per
BNS s.112 (petty organised crime). Unlike s.111/MCOCA (Organized Crime,
not yet built), s.112 has no charge-sheet-count requirement -- a much
lower bar, deliberately easy to invoke once the pattern below is met.

A candidate series is never itself an accusation: it says "these FIRs look
like the same actor(s)," which is exactly the kind of cross-FIR pattern an
investigator cannot spot by reading FIRs one at a time, and exactly the
kind of finding that requires their sign-off before acting on it.
"""
from datetime import datetime
from itertools import combinations

from app.config import MO_SERIES_FIELDS, MO_SERIES_MIN_MATCHING_FIELDS, MO_SERIES_MAX_DAYS_APART, MO_SERIES_MIN_SHARED_ACCUSED_FOR_S112

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, FMT)
    except ValueError:
        return datetime.strptime(ts.split("T")[0], "%Y-%m-%d")


def _accused_entity_ids(conn, fir_id):
    rows = conn.execute(
        """SELECT DISTINCT mem.entity_id FROM entity_mentions em
           JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
           WHERE em.source_record_id = ? AND em.fir_role = 'ACCUSED'""",
        (fir_id,),
    ).fetchall()
    return {r["entity_id"] for r in rows}


def _matching_field_count(a, b):
    matched = []
    for f in MO_SERIES_FIELDS:
        va, vb = a[f], b[f]
        if va is not None and vb is not None and va == vb:
            matched.append(f)
    return matched


def detect_mo_series(conn):
    """Every pair of crime_mo_record rows that clears the MO-similarity
    bar, annotated with whether the shared-accused count also clears the
    BNS s.112 threshold. Pairs are the atomic unit here (not pre-clustered
    into series) so every finding stays traceable to the exact two FIRs
    and exact matching fields that produced it."""
    records = conn.execute("SELECT * FROM crime_mo_record").fetchall()
    results = []

    for a, b in combinations(records, 2):
        if a["case_id"] == b["case_id"] and a["fir_id"] == b["fir_id"]:
            continue
        matched_fields = _matching_field_count(a, b)
        if len(matched_fields) < MO_SERIES_MIN_MATCHING_FIELDS:
            continue

        date_a, date_b = _parse(a["date"]), _parse(b["date"])
        if date_a is None or date_b is None or abs((date_a - date_b).days) > MO_SERIES_MAX_DAYS_APART:
            continue

        shared_accused = _accused_entity_ids(conn, a["fir_id"]) & _accused_entity_ids(conn, b["fir_id"])

        results.append({
            "fir_a": a["fir_id"], "fir_b": b["fir_id"],
            "case_a": a["case_id"], "case_b": b["case_id"],
            "matched_fields": matched_fields,
            "days_apart": abs((date_a - date_b).days),
            "shared_accused": sorted(shared_accused),
            "bns_112_candidate": len(shared_accused) >= MO_SERIES_MIN_SHARED_ACCUSED_FOR_S112,
        })
    return results
