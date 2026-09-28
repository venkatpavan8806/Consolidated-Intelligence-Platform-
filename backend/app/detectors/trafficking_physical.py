"""
Trafficking/Missing-Person Physical-evidence detector: Unidentified Dead
Body (UIDB) <-> missing-person candidate matching, ZIPNET's own real
cross-case-link field, and DNA-sample-chain compliance -- the post-mortem/
body-identification complement to the live-trafficking Digital signals
(recruiter fan-out, transporter bridge paths -- see app/detectors/
women_safety.py), for cases that end in an unidentified death rather than
a rescue.

Every finding is a candidate for a human investigator to check against the
case file -- a candidate match is never an identification, and an
"ignored match" flag is never itself proof the two records are the same
person, only that ZIPNET's own matching field says so and the case wasn't
closed accordingly.
"""
from datetime import datetime

from app.config import UIDB_AGE_TOLERANCE_YEARS, UIDB_HEIGHT_TOLERANCE_CM, UIDB_DNA_DISPATCH_MAX_HOURS

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, FMT)
    except ValueError:
        return datetime.strptime(ts.split("T")[0], "%Y-%m-%d")


def _dress_tokens(mp_row):
    import json
    try:
        return {t.strip().lower() for t in json.loads(mp_row["dress_colour_tokens_json"] or "[]")}
    except (TypeError, ValueError):
        return set()


def detect_uidb_missing_person_candidates(conn):
    """PE-C's own proposed matching rule: sex equal; age range overlaps
    the missing person's age by +/-UIDB_AGE_TOLERANCE_YEARS; height within
    UIDB_HEIGHT_TOLERANCE_CM; found_date on/after last_seen_date; at least
    one dress-colour token in common; same district. District-adjacency
    (the research's fuller spec) is dropped -- an honest, documented
    simplification, the same pattern used for the Robbery/Theft MO-series
    5 km leg: this system has no adjacency table to test it against."""
    results = []
    uidbs = conn.execute("SELECT * FROM uidb_record").fetchall()
    missing = conn.execute("SELECT * FROM missing_person_report").fetchall()

    for u in uidbs:
        u_found = _parse(u["found_date"])
        for m in missing:
            if u["sex"] and m["sex"] and u["sex"] != m["sex"]:
                continue
            if m["age"] is not None and u["age_from"] is not None and u["age_to"] is not None:
                if not (u["age_from"] - UIDB_AGE_TOLERANCE_YEARS <= m["age"] <= u["age_to"] + UIDB_AGE_TOLERANCE_YEARS):
                    continue
            if u["height_cm"] is not None and m["height_cm"] is not None:
                if abs(u["height_cm"] - m["height_cm"]) > UIDB_HEIGHT_TOLERANCE_CM:
                    continue
            m_last_seen = _parse(m["last_seen_date"])
            if u_found is not None and m_last_seen is not None and u_found < m_last_seen:
                continue
            uidb_colours = {c.strip().lower() for c in (u["dress_upper_colour"], u["dress_lower_colour"]) if c}
            mp_colours = _dress_tokens(m)
            if not (uidb_colours & mp_colours):
                continue
            if u["district"] and m["district"] and u["district"] != m["district"]:
                continue

            results.append({
                "uidb_id": u["uidb_id"], "missing_person_id": m["missing_person_id"],
                "case_id": u["case_id"], "missing_person_case_id": m["case_id"],
                "shared_dress_colours": sorted(uidb_colours & mp_colours),
            })
    return results


def detect_ignored_zipnet_match(conn):
    """A UIDB record with matched_missing_serial_no already populated --
    ZIPNET's own real match field -- whose linked missing-person case is
    STILL shown open. A real, exploitable data-quality/process-failure
    signal: the matching already happened in the source system, nothing
    here needs to be inferred."""
    results = []
    for u in conn.execute("SELECT * FROM uidb_record WHERE matched_missing_serial_no IS NOT NULL").fetchall():
        mp = conn.execute(
            "SELECT * FROM missing_person_report WHERE missing_person_id = ?",
            (u["matched_missing_serial_no"],),
        ).fetchone()
        if mp is not None and mp["status"] == "OPEN":
            results.append({
                "uidb_id": u["uidb_id"], "missing_person_id": mp["missing_person_id"],
                "case_id": u["case_id"], "missing_person_case_id": mp["case_id"],
            })
    return results


def detect_unsampled_body(conn):
    """A post-mortem report referenced by a UIDB record with no
    dna_sample_record at all -- per the Rajasthan HC/*Lokniti Foundation*
    preservation logic, an unidentified body's DNA-sampling opportunity is
    a one-time, perishable window."""
    results = []
    for u in conn.execute("SELECT * FROM uidb_record WHERE pm_id IS NOT NULL").fetchall():
        sample = conn.execute("SELECT 1 FROM dna_sample_record WHERE pm_id = ? LIMIT 1", (u["pm_id"],)).fetchone()
        if sample is None:
            results.append({"uidb_id": u["uidb_id"], "pm_id": u["pm_id"], "case_id": u["case_id"]})
    return results


def detect_late_dna_dispatch(conn):
    """A DNA sample dispatched more than UIDB_DNA_DISPATCH_MAX_HOURS after
    collection with no delay reason recorded -- *Kattavellai*'s own
    48-hour direction, not a design default."""
    results = []
    for s in conn.execute("SELECT * FROM dna_sample_record").fetchall():
        collected, dispatched = _parse(s["collected_ts"]), _parse(s["dispatch_ts"])
        if collected is None or dispatched is None:
            continue
        hours = (dispatched - collected).total_seconds() / 3600.0
        if hours > UIDB_DNA_DISPATCH_MAX_HOURS and not s["dispatch_delay_reason"]:
            results.append({"sample_id": s["sample_id"], "case_id": s["case_id"], "hours_elapsed": round(hours, 1)})
    return results


def detect_weak_dna_conclusion_relied_alone(conn):
    """A DEGRADED_NO_PROFILE/INCONCLUSIVE DNA conclusion, or one with no
    examined expert, being used as the identification basis for a UIDB<->
    missing-person match (i.e. the UIDB's matched_missing_serial_no is
    already populated off the back of this sample) -- per *Nantu Nath*, a
    weak or unexamined conclusion should never stand alone as the basis
    for identification."""
    results = []
    weak_categories = {"DEGRADED_NO_PROFILE", "INCONCLUSIVE"}
    for s in conn.execute("SELECT * FROM dna_sample_record").fetchall():
        is_weak = s["conclusion_category"] in weak_categories or not s["expert_examined"]
        if not is_weak or not s["pm_id"]:
            continue
        uidb = conn.execute(
            "SELECT * FROM uidb_record WHERE pm_id = ? AND matched_missing_serial_no IS NOT NULL LIMIT 1",
            (s["pm_id"],),
        ).fetchone()
        if uidb is not None:
            results.append({
                "sample_id": s["sample_id"], "uidb_id": uidb["uidb_id"], "case_id": s["case_id"],
                "conclusion_category": s["conclusion_category"], "expert_examined": bool(s["expert_examined"]),
            })
    return results
