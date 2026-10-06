"""
Robbery/Theft Physical-evidence detector: stolen<->recovered property
matching, modeled on two real NCRB/state systems the research pass found --
Vahan Samanvay (the national stolen/recovered *vehicle* coordination
system) and the IIF-I/IIF-IV stolen-vs-recovered *property* matching it
generalizes to non-vehicle items. Everything here reads case_property /
property_item rows tagged case_type='ROBBERY_THEFT' -- the same generic
Physical-evidence spine the Narcotics module uses, per Part C's shared
seizure/exhibit schema.

Every finding is a candidate cross-case link for a human investigator to
verify against the case file -- never an automated finding of possession
or guilt. A LINK found here does not by itself prove the person in custody
of recovered property is the thief; it says the property matches, which is
exactly the kind of fact an investigator needs surfaced, not decided.
"""
from datetime import datetime

from app.config import (
    ROBBERY_VEHICLE_MATCH_MIN_FIELDS, ROBBERY_VEHICLE_PARTIAL_MATCH_SUFFIX_LEN,
    ROBBERY_PROPERTY_VALUE_MATCH_TOLERANCE_FRACTION, ROBBERY_LINGERING_PROPERTY_MAX_DAYS,
)

FMT = "%Y-%m-%dT%H:%M:%S"
VEHICLE_FIELDS = ("registration", "chassis", "engine")


def _parse(ts):
    if not ts:
        return None
    return datetime.strptime(ts, FMT)


def _field_matches(a, b):
    """Exact match, or last-N-characters match ("partial Nos.", per the
    Vahan Samanvay FAQ's own published matching rule)."""
    if not a or not b:
        return False
    if a == b:
        return True
    n = ROBBERY_VEHICLE_PARTIAL_MATCH_SUFFIX_LEN
    return len(a) >= n and len(b) >= n and a[-n:] == b[-n:]


def _load_items(conn):
    """Every property_item under a ROBBERY_THEFT case_property row, split
    by whether it was reported stolen or recovered -- inferred from the
    parent case_property.form_type, not guessed from item content."""
    rows = conn.execute(
        """SELECT pi.*, cp.case_id, cp.form_type, cp.seizure_datetime, cp.property_id AS parent_property_id
           FROM property_item pi JOIN case_property cp ON pi.property_id = cp.property_id
           WHERE cp.case_type = 'ROBBERY_THEFT'"""
    ).fetchall()
    stolen, recovered = [], []
    for r in rows:
        (stolen if r["form_type"] == "STOLEN_PROPERTY_REPORT" else recovered).append(r)
    return stolen, recovered


def _identifiers(row):
    import json
    try:
        return json.loads(row["identifiers_json"] or "{}")
    except (TypeError, ValueError):
        return {}


def detect_vehicle_links(conn):
    """Vahan Samanvay-style matching: same vehicle_type AND at least
    ROBBERY_VEHICLE_MATCH_MIN_FIELDS of {registration, chassis, engine}
    matching (exact or partial-suffix) between a stolen report and a
    recovery memo. A chassis match with a differing engine (or vice versa)
    is flagged separately and more severely as a likely "re-birthed"
    (identity-swapped) vehicle."""
    stolen, recovered = _load_items(conn)
    results = []

    for s in stolen:
        s_ids = _identifiers(s)
        if s_ids.get("vehicle_type") is None:
            continue
        for r in recovered:
            r_ids = _identifiers(r)
            if r_ids.get("vehicle_type") is None or r_ids["vehicle_type"] != s_ids["vehicle_type"]:
                continue

            matched_fields = [f for f in VEHICLE_FIELDS if _field_matches(s_ids.get(f), r_ids.get(f))]
            chassis_match = _field_matches(s_ids.get("chassis"), r_ids.get("chassis"))
            engine_match = _field_matches(s_ids.get("engine"), r_ids.get("engine"))
            reg_match = _field_matches(s_ids.get("registration"), r_ids.get("registration"))
            # Chassis is the anchor identifier: chassis matching while
            # either of the other two does not is exactly the re-birth
            # signature (a swapped registration/engine on the same
            # physical frame), and it fires on chassis matching ALONE --
            # gating it behind the >=2-field ordinary-LINK threshold below
            # would systematically miss it, since a re-birthed vehicle by
            # definition has fewer matching fields, not more.
            tampering = chassis_match and (not engine_match or not reg_match)

            if not tampering and len(matched_fields) < ROBBERY_VEHICLE_MATCH_MIN_FIELDS:
                continue

            results.append({
                "stolen_item_id": s["item_id"], "stolen_property_id": s["parent_property_id"], "stolen_case_id": s["case_id"],
                "recovered_item_id": r["item_id"], "recovered_property_id": r["parent_property_id"], "recovered_case_id": r["case_id"],
                "vehicle_type": s_ids["vehicle_type"],
                "matched_fields": matched_fields,
                "tampering_suspected": tampering,
                "stolen_identifiers": s_ids, "recovered_identifiers": r_ids,
            })
    return results


def detect_property_item_matches(conn):
    """Non-vehicle IIF-I (stolen) vs IIF-IV (recovered) property matching:
    an exact serial/IMEI match is a LINK; absent a hard identifier, a
    matching description with recovered value within
    ROBBERY_PROPERTY_VALUE_MATCH_TOLERANCE_FRACTION of the reported stolen
    value is a weaker CANDIDATE match."""
    stolen, recovered = _load_items(conn)
    results = []

    for s in stolen:
        s_ids = _identifiers(s)
        if s_ids.get("vehicle_type") is not None:
            continue  # vehicles are handled by detect_vehicle_links
        s_identifier = s_ids.get("serial") or s_ids.get("imei")

        for r in recovered:
            r_ids = _identifiers(r)
            if r_ids.get("vehicle_type") is not None:
                continue
            r_identifier = r_ids.get("serial") or r_ids.get("imei")

            if s_identifier and r_identifier and s_identifier == r_identifier:
                results.append({
                    "match_type": "LINK", "match_basis": "exact_identifier",
                    "stolen_item_id": s["item_id"], "stolen_case_id": s["case_id"],
                    "recovered_item_id": r["item_id"], "recovered_case_id": r["case_id"],
                    "identifier": s_identifier, "description": s["description"],
                })
                continue

            if s_identifier or r_identifier:
                continue  # both/either had a hard identifier that didn't match -- not a description-level candidate

            if s["description"].strip().lower() != r["description"].strip().lower():
                continue
            if s["estimated_value"] is None or r["estimated_value"] is None:
                continue
            tolerance = s["estimated_value"] * ROBBERY_PROPERTY_VALUE_MATCH_TOLERANCE_FRACTION
            if abs(s["estimated_value"] - r["estimated_value"]) <= tolerance:
                results.append({
                    "match_type": "CANDIDATE", "match_basis": "description_and_value",
                    "stolen_item_id": s["item_id"], "stolen_case_id": s["case_id"],
                    "recovered_item_id": r["item_id"], "recovered_case_id": r["case_id"],
                    "description": s["description"],
                    "stolen_value": s["estimated_value"], "recovered_value": r["estimated_value"],
                })
    return results


def detect_lingering_property(conn):
    """Recovered property with no COURT_DISPOSAL custody_event recorded
    within ROBBERY_LINGERING_PROPERTY_MAX_DAYS of seizure -- a BNSS 497/503
    (interim custody/disposal of case property) lapse."""
    results = []
    recovered_props = conn.execute(
        "SELECT * FROM case_property WHERE case_type='ROBBERY_THEFT' AND form_type='RECOVERY_MEMO'"
    ).fetchall()

    for prop in recovered_props:
        disposal = conn.execute(
            "SELECT 1 FROM custody_event WHERE property_id=? AND event_type='COURT_DISPOSAL' LIMIT 1",
            (prop["property_id"],),
        ).fetchone()
        if disposal:
            continue
        seized = _parse(prop["seizure_datetime"])
        if seized is None:
            continue
        # "Now" is intentionally the latest event on this property (or the
        # seizure itself if none), not wall-clock time, so the check is
        # reproducible against a fixed synthetic dataset rather than
        # depending on when the pipeline happens to run.
        latest_event = conn.execute(
            "SELECT MAX(event_ts) AS ts FROM custody_event WHERE property_id=?", (prop["property_id"],)
        ).fetchone()
        as_of = _parse(latest_event["ts"]) if latest_event and latest_event["ts"] else seized
        if as_of is None:
            continue
        days_elapsed = (as_of - seized).days
        if days_elapsed > ROBBERY_LINGERING_PROPERTY_MAX_DAYS:
            results.append({
                "property_id": prop["property_id"], "case_id": prop["case_id"],
                "days_elapsed": days_elapsed, "seizure_datetime": prop["seizure_datetime"],
            })
    return results
