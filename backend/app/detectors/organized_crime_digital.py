"""
Organized Crime detector: cross-case identifier reuse (the mechanism
common_identifier_index exists for), shared-infrastructure evidence, and
the BNS s.111 (<- MCOCA s.2(1)(d)) "continuing unlawful activity"
charge-sheet legal gate -- the single most legally precise, directly
codable rule in the whole research pass.

Per *Zakir Abdul Mirajkar v. State of Maharashtra* (2022 LiveLaw (SC) 707)
and *Kavitha Lankesh v. State of Karnataka* (2022) 12 SCC 753, the more-
than-one-charge-sheet count is taken PER SYNDICATE, not per individual
accused -- a syndicate can clear the s.111 threshold even when no single
member has more than one charge-sheet of their own, as long as the
syndicate's members collectively do. This module builds syndicates as
connected components of accused entities (co-accusal on a charge-sheet, or
sharing a non-accused identifier such as a phone/account/vehicle across
FIRs) before counting.

Every finding here is a candidate for a human investigator to check
against the case file -- a syndicate finding is never itself a charge, and
a charge-sheet-threshold finding is never itself a determination that
BNS s.111/MCOCA applies; only a court can decide that.
"""
from datetime import datetime, timedelta

from app.config import (
    ORGANIZED_CRIME_CROSS_CASE_LINK_MIN_FIRS, ORGANIZED_CRIME_INTERSTATE_ALERT_MIN_FIRS,
    ORGANIZED_CRIME_CHARGE_SHEET_LOOKBACK_YEARS, ORGANIZED_CRIME_MIN_PUNISHMENT_YEARS,
    ORGANIZED_CRIME_MIN_QUALIFYING_CHARGE_SHEETS,
)

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, FMT)
    except ValueError:
        return datetime.strptime(ts.split("T")[0], "%Y-%m-%d")


def detect_cross_case_identifier_links(conn):
    """Groups common_identifier_index rows by (identifier_type, value).
    A value appearing in >=ORGANIZED_CRIME_CROSS_CASE_LINK_MIN_FIRS distinct
    FIRs is a candidate link, with full provenance; clearing
    ORGANIZED_CRIME_INTERSTATE_ALERT_MIN_FIRS escalates it to an interstate-
    style linkage alert, per the research's own Samanvaya-modeled rule.
    ACCUSED_ID is excluded here -- an accused person naturally recurs
    across their own FIRs, which is not a cross-case *infrastructure*
    signal; that is what detect_shared_infrastructure is for."""
    rows = conn.execute(
        "SELECT * FROM common_identifier_index WHERE identifier_type != 'ACCUSED_ID' ORDER BY identifier_type, value"
    ).fetchall()

    groups = {}
    for r in rows:
        key = (r["identifier_type"], r["value"])
        groups.setdefault(key, []).append(r)

    results = []
    for (identifier_type, value), occurrences in groups.items():
        fir_nos = sorted({o["fir_no"] for o in occurrences if o["fir_no"]})
        case_ids = sorted({o["case_id"] for o in occurrences})
        if len(fir_nos) < ORGANIZED_CRIME_CROSS_CASE_LINK_MIN_FIRS:
            continue
        results.append({
            "identifier_type": identifier_type, "value": value,
            "fir_nos": fir_nos, "case_ids": case_ids,
            "police_stations": sorted({o["police_station"] for o in occurrences if o["police_station"]}),
            "interstate_alert": len(fir_nos) >= ORGANIZED_CRIME_INTERSTATE_ALERT_MIN_FIRS,
        })
    return results


def _accused_for_fir_nos(conn, fir_nos):
    if not fir_nos:
        return set()
    placeholders = ",".join("?" * len(fir_nos))
    rows = conn.execute(
        f"SELECT DISTINCT value FROM common_identifier_index WHERE identifier_type='ACCUSED_ID' "
        f"AND fir_no IN ({placeholders})",
        tuple(fir_nos),
    ).fetchall()
    return {r["value"] for r in rows}


def detect_shared_infrastructure(conn):
    """A non-accused identifier (phone/account/vehicle) shared across
    >=2 FIRs that name >=2 DISTINCT accused between them -- "same-cell
    co-membership evidence" per the research: two people who both used
    the same phone/account/vehicle across separate incidents are
    structurally linked whether or not they were ever co-accused on the
    same charge-sheet."""
    results = []
    for hit in detect_cross_case_identifier_links(conn):
        accused = _accused_for_fir_nos(conn, hit["fir_nos"])
        if len(accused) >= 2:
            results.append({**hit, "accused_entity_ids": sorted(accused)})
    return results


def _build_syndicates(conn):
    """Union-find over accused entity_ids, connected by co-accusal on the
    same charge-sheet OR by shared-infrastructure (see module docstring).
    Returns {entity_id: syndicate_members (frozenset, only for components
    of size >= 2 -- a syndicate is, by definition, two or more persons)}."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    cs_accused = {}
    for r in conn.execute("SELECT charge_sheet_id, entity_id FROM charge_sheet_accused").fetchall():
        cs_accused.setdefault(r["charge_sheet_id"], []).append(r["entity_id"])
    for members in cs_accused.values():
        for i in range(len(members)):
            find(members[i])
            for j in range(i + 1, len(members)):
                union(members[i], members[j])

    for hit in detect_shared_infrastructure(conn):
        members = hit["accused_entity_ids"]
        for i in range(len(members)):
            find(members[i])
            for j in range(i + 1, len(members)):
                union(members[i], members[j])

    components = {}
    for entity_id in list(parent):
        root = find(entity_id)
        components.setdefault(root, set()).add(entity_id)

    membership = {}
    for members in components.values():
        if len(members) < 2:
            continue
        frozen = frozenset(members)
        for m in members:
            membership[m] = frozen
    return membership


def detect_syndicate_charge_sheet_threshold(conn):
    """The BNS s.111/MCOCA legal gate. For every syndicate (>=2 accused,
    connected component from _build_syndicates), counts charge-sheets
    across ALL its members -- not per accused -- filed by a competent
    Court (cognizance_date not null) within the lookback window of the
    LATEST qualifying charge-sheet's own cognizance_date used as the
    reference "current offence" date, for a cognizable offence carrying
    >= ORGANIZED_CRIME_MIN_PUNISHMENT_YEARS. Clearing
    ORGANIZED_CRIME_MIN_QUALIFYING_CHARGE_SHEETS means the s.111/MCOCA
    threshold is met; a lone accused (no syndicate) never reaches this
    function at all, since s.2(1)(f)/BNS s.111 define a syndicate as two
    or more persons in the first place."""
    membership = _build_syndicates(conn)
    if not membership:
        return []

    charge_sheets = conn.execute("SELECT * FROM charge_sheet").fetchall()
    cs_accused = {}
    for r in conn.execute("SELECT charge_sheet_id, entity_id FROM charge_sheet_accused").fetchall():
        cs_accused.setdefault(r["charge_sheet_id"], set()).add(r["entity_id"])

    results = []
    seen_syndicates = set()
    for syndicate in set(membership.values()):
        if syndicate in seen_syndicates:
            continue
        seen_syndicates.add(syndicate)

        syndicate_charge_sheets = [
            cs for cs in charge_sheets if cs_accused.get(cs["charge_sheet_id"], set()) & syndicate
        ]
        cognizance_dates = [
            _parse(cs["cognizance_date"]) for cs in syndicate_charge_sheets if cs["cognizance_date"]
        ]
        if not cognizance_dates:
            continue
        reference_date = max(cognizance_dates)
        lookback_start = reference_date - timedelta(days=365 * ORGANIZED_CRIME_CHARGE_SHEET_LOOKBACK_YEARS)

        qualifying = [
            cs for cs in syndicate_charge_sheets
            if cs["cognizance_date"] and cs["offence_cognizable"]
            and cs["max_punishment_years"] is not None
            and cs["max_punishment_years"] >= ORGANIZED_CRIME_MIN_PUNISHMENT_YEARS
            and lookback_start <= _parse(cs["cognizance_date"]) <= reference_date
        ]
        results.append({
            "syndicate_members": sorted(syndicate),
            "qualifying_charge_sheet_ids": sorted(cs["charge_sheet_id"] for cs in qualifying),
            "qualifying_count": len(qualifying),
            "threshold_met": len(qualifying) >= ORGANIZED_CRIME_MIN_QUALIFYING_CHARGE_SHEETS,
        })
    return results
