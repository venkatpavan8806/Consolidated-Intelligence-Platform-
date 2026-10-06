"""
Assault/Homicide Digital-evidence detector: BSA 2023 s.63 / Evidence Act
s.65B(4) certification status of tower/cell-site location records, plus a
joint Physical+Digital spatio-temporal correlation signal (a suspect
phone's tower ping near the inquest's place_of_occurrence, close in time to
the recorded time of death).

Per *Anvar P.V. v. P.K. Basheer* (2014), *Arjun Panditrao Khotkar v.
Kailash Kushanrao Gorantyal* (2020) 7 SCC 1 ("condition precedent"), and
*Rahil v. State (NCT of Delhi)* (2025 INSC 858) -- where the Supreme Court
set aside a conviction that relied on uncertified CDR/tower evidence --
this module never treats an uncertified location record as usable proof.
Every finding is a candidate lead requiring corroboration and, for any
uncertified record, the missing s.65B(4) certificate -- never a verdict on
a suspect's location or movements.
"""
from datetime import datetime

from app.config import ASSAULT_TOWER_SPATIOTEMPORAL_WINDOW_HOURS

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, FMT)
    except ValueError:
        return datetime.strptime(ts.split("T")[0], "%Y-%m-%d")


def detect_uncertified_tower_evidence(conn):
    """Every tower_location_record lacking a s.65B(4) certificate --
    candidate leads only, requiring corroboration and certification before
    they could ever be relied on per *Rahil*."""
    results = []
    for r in conn.execute("SELECT * FROM tower_location_record WHERE is_certified_65b = 0").fetchall():
        results.append({
            "record_id": r["record_id"], "case_id": r["case_id"], "phone": r["phone"],
            "timestamp": r["timestamp"], "locality_name": r["locality_name"],
        })
    return results


def _place_matches(place_of_occurrence, locality_name):
    if not place_of_occurrence or not locality_name:
        return False
    a, b = place_of_occurrence.strip().lower(), locality_name.strip().lower()
    return a in b or b in a


def detect_spatiotemporal_correlation(conn):
    """Joint Physical+Digital signal: a tower ping whose locality_name
    corresponds to the inquest's place_of_occurrence, within
    ASSAULT_TOWER_SPATIOTEMPORAL_WINDOW_HOURS of the recorded death_ts.
    Case-scoped only (no cross-case attempt here) -- a documented
    simplification, not a silent omission. An uncertified tower record can
    still surface here (the case needs to know the correlation exists to
    decide whether it's worth pursuing certification), but the finding
    itself always carries is_certified_65b so it's never mistaken for
    already-usable proof."""
    results = []
    inquests = conn.execute(
        "SELECT * FROM inquest_report WHERE place_of_occurrence IS NOT NULL AND death_ts IS NOT NULL"
    ).fetchall()
    towers = conn.execute("SELECT * FROM tower_location_record WHERE locality_name IS NOT NULL").fetchall()

    for inq in inquests:
        death_dt = _parse(inq["death_ts"])
        if death_dt is None:
            continue
        for t in towers:
            if t["case_id"] != inq["case_id"]:
                continue
            if not _place_matches(inq["place_of_occurrence"], t["locality_name"]):
                continue
            t_dt = _parse(t["timestamp"])
            if t_dt is None:
                continue
            hours = abs((t_dt - death_dt).total_seconds()) / 3600.0
            if hours <= ASSAULT_TOWER_SPATIOTEMPORAL_WINDOW_HOURS:
                results.append({
                    "inquest_id": inq["inquest_id"], "case_id": inq["case_id"],
                    "phone": t["phone"], "record_id": t["record_id"],
                    "place_of_occurrence": inq["place_of_occurrence"], "locality_name": t["locality_name"],
                    "hours_from_death": round(hours, 2), "is_certified_65b": bool(t["is_certified_65b"]),
                })
    return results
