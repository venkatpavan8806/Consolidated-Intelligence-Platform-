"""
Assault/Homicide Physical-evidence detector: inquest/post-mortem procedural
compliance (BNSS s.194 <- CrPC s.174, BNSS s.196 <- CrPC s.176, NHRC Model
Autopsy Form), BNS s.116 (<- IPC s.320) MLC-classification consistency, and
forensic cross-exhibit matching across fingerprint (AFIS/NAFIS -- a real,
searchable, networked database), ballistics (NO verified networked Indian
database, per the research pass -- so every ballistics link here is an
examiner's own opinion comparing two named exhibits, never an automated
database hit) and DNA (categorical match_confidence, never a numeric score
or percentage in an Indian FSL report).

Every finding is a candidate for a human investigator to check against the
case file -- never an automated finding of cause of death, guilt, or
injury reclassification. A BALLISTICS finding in particular must never be
presented as equivalent in certainty to a FINGERPRINT database hit; the two
are kept distinguishable via `examiner_asserted` and the finding's own
wording, not just internally.
"""
import json
from datetime import datetime

from app.config import (
    ASSAULT_INQUEST_MIN_WITNESSES, ASSAULT_CUSTODIAL_INTIMATION_MAX_HOURS,
    ASSAULT_MLC_GRIEVOUS_MIN_FOLLOWUP_DAYS, ASSAULT_MLC_SIMPLE_MAX_FOLLOWUP_DAYS,
)

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, FMT)
    except ValueError:
        return datetime.strptime(ts.split("T")[0], "%Y-%m-%d")


def _injuries(row_json):
    try:
        return set(json.loads(row_json or "[]"))
    except (TypeError, ValueError):
        return set()


def detect_inquest_witness_violations(conn):
    """BNSS s.194's "two or more respectable inhabitants" requirement,
    checked against the stored witness_count -- an explicit statutory
    figure, not a design threshold."""
    results = []
    for r in conn.execute("SELECT * FROM inquest_report").fetchall():
        if r["witness_count"] is not None and r["witness_count"] < ASSAULT_INQUEST_MIN_WITNESSES:
            results.append({
                "inquest_id": r["inquest_id"], "case_id": r["case_id"],
                "witness_count": r["witness_count"],
                "required": ASSAULT_INQUEST_MIN_WITNESSES,
            })
    return results


def detect_injury_list_mismatch(conn):
    """Compares the injury_list_json recorded on the inquest report against
    the post-mortem report for the same case/FIR -- a mismatch means one of
    the two records is incomplete or the two examinations disagree, either
    of which an investigator needs to see, not have silently reconciled."""
    results = []
    rows = conn.execute(
        """SELECT ir.inquest_id, ir.case_id AS case_id, ir.fir_id AS ir_fir_id,
                  ir.injury_list_json AS inquest_injuries,
                  pm.pm_id, pm.injury_list_json AS pm_injuries, pm.fir_id AS pm_fir_id
           FROM inquest_report ir
           JOIN post_mortem_report pm ON ir.case_id = pm.case_id
           WHERE (ir.fir_id = pm.fir_id) OR (ir.fir_id IS NULL AND pm.fir_id IS NULL)"""
    ).fetchall()
    for r in rows:
        inquest_set = _injuries(r["inquest_injuries"])
        pm_set = _injuries(r["pm_injuries"])
        missing_from_inquest = pm_set - inquest_set
        missing_from_pm = inquest_set - pm_set
        if missing_from_inquest or missing_from_pm:
            results.append({
                "inquest_id": r["inquest_id"], "pm_id": r["pm_id"], "case_id": r["case_id"],
                "missing_from_inquest": sorted(missing_from_inquest),
                "missing_from_pm": sorted(missing_from_pm),
            })
    return results


def detect_postmortem_missing_timing_fields(conn):
    """rectal_temperature and rigor_mortis timing are the two fields the
    research pass identified as most commonly missing/incomplete in
    practice, despite being on the NHRC Model Autopsy Form itself -- both
    matter for estimating time of death, which downstream feeds the
    spatio-temporal correlation signal."""
    results = []
    for r in conn.execute("SELECT * FROM post_mortem_report").fetchall():
        missing = []
        if r["rectal_temperature"] is None:
            missing.append("rectal_temperature")
        if not r["rigor_mortis_state"] or not r["rigor_mortis_time_estimate"]:
            missing.append("rigor_mortis_timing")
        if missing:
            results.append({"pm_id": r["pm_id"], "case_id": r["case_id"], "missing_fields": missing})
    return results


def detect_custodial_death_intimation_violation(conn):
    """BNSS s.196: a custodial death must be intimated 'forthwith'. Flags
    either a wholly missing intimation_ts, or one recorded more than
    ASSAULT_CUSTODIAL_INTIMATION_MAX_HOURS after death_ts."""
    results = []
    for r in conn.execute("SELECT * FROM inquest_report WHERE is_custodial_death = 1").fetchall():
        death_dt = _parse(r["death_ts"])
        if not r["intimation_ts"]:
            results.append({
                "inquest_id": r["inquest_id"], "case_id": r["case_id"],
                "violation": "INTIMATION_MISSING", "hours_elapsed": None,
            })
            continue
        intimation_dt = _parse(r["intimation_ts"])
        if death_dt is None or intimation_dt is None:
            continue
        hours = (intimation_dt - death_dt).total_seconds() / 3600.0
        if hours > ASSAULT_CUSTODIAL_INTIMATION_MAX_HOURS:
            results.append({
                "inquest_id": r["inquest_id"], "case_id": r["case_id"],
                "violation": "INTIMATION_DELAYED", "hours_elapsed": round(hours, 1),
            })
    return results


def detect_mlc_classification_inconsistency(conn):
    """Flags an MLC record whose stated injury_classification sits far
    outside what its own recorded follow_up_days would suggest -- a
    candidate for human re-check against the actual injury list, never an
    automated reclassification."""
    results = []
    for r in conn.execute("SELECT * FROM mlc_record").fetchall():
        days = r["follow_up_days"] if r["follow_up_days"] is not None else 0
        if r["injury_classification"] == "GRIEVOUS" and days < ASSAULT_MLC_GRIEVOUS_MIN_FOLLOWUP_DAYS:
            results.append({
                "mlc_id": r["mlc_id"], "case_id": r["case_id"],
                "issue": "GRIEVOUS_WITH_LOW_FOLLOWUP", "follow_up_days": days,
            })
        elif r["injury_classification"] == "SIMPLE" and days > ASSAULT_MLC_SIMPLE_MAX_FOLLOWUP_DAYS:
            results.append({
                "mlc_id": r["mlc_id"], "case_id": r["case_id"],
                "issue": "SIMPLE_WITH_HIGH_FOLLOWUP", "follow_up_days": days,
            })
    return results


def detect_forensic_matches(conn):
    """Per-match-type handling, because the three forensic disciplines are
    NOT interchangeable evidentiary strength:
      - FINGERPRINT: AFIS/NAFIS is a real, searchable, networked national
        database -- a matching identifier_value (NFN) across two exhibits
        is treated as a genuine automated LINK.
      - BALLISTICS: India has NO verified networked national ballistics
        database. A match is only ever surfaced when examiner_asserted=1,
        and even then as a CANDIDATE labelled "examiner-asserted", never a
        LINK -- surfacing it as a database hit would overstate what the
        record actually is.
      - DNA: match_confidence_category is categorical (Indian FSL reports
        never give a numeric likelihood ratio/percentage) -- MATCHES is a
        LINK; EXCLUDES/DEGRADED/INCONCLUSIVE are never treated as positive
        here (see detect_forensic_confidence_misuse for the case where the
        case file itself mis-treats one as positive)."""
    results = []
    for r in conn.execute("SELECT * FROM forensic_match").fetchall():
        base = {
            "match_id": r["match_id"], "case_id_a": r["case_id_a"], "case_id_b": r["case_id_b"],
            "exhibit_a": r["exhibit_a"], "exhibit_b": r["exhibit_b"], "match_type": r["match_type"],
        }
        if r["match_type"] == "FINGERPRINT":
            if r["identifier_value"]:
                results.append({**base, "finding_type": "LINK", "identifier_value": r["identifier_value"],
                                 "match_confidence_numeric": r["match_confidence_numeric"]})
        elif r["match_type"] == "BALLISTICS":
            if r["examiner_asserted"] and r["match_confidence_category"] == "MATCHES":
                results.append({**base, "finding_type": "CANDIDATE_EXAMINER_ASSERTED",
                                 "examiner_name": r["examiner_name"],
                                 "note": "Examiner-asserted exhibit-to-exhibit opinion -- India has no "
                                         "verified networked ballistics database, so this is NOT a "
                                         "database hit and must be independently verified."})
        elif r["match_type"] == "DNA":
            if r["match_confidence_category"] == "MATCHES":
                results.append({**base, "finding_type": "LINK",
                                 "fsl_report_no": r["fsl_report_no"]})
    return results


def detect_forensic_confidence_misuse(conn):
    """Flags a forensic_match record whose category is DEGRADED or
    INCONCLUSIVE but whose own attributes_json shows the case file treating
    it as a positive match anyway -- exactly the categorical-vs-numeric
    confusion the research pass warned Indian DNA/ballistics reports are
    prone to being misread as."""
    results = []
    rows = conn.execute(
        "SELECT * FROM forensic_match WHERE match_confidence_category IN ('DEGRADED', 'INCONCLUSIVE')"
    ).fetchall()
    for r in rows:
        try:
            attrs = json.loads(r["attributes_json"] or "{}")
        except (TypeError, ValueError):
            attrs = {}
        if attrs.get("treated_as_positive_in_case_file"):
            results.append({
                "match_id": r["match_id"], "case_id_a": r["case_id_a"], "case_id_b": r["case_id_b"],
                "match_type": r["match_type"], "match_confidence_category": r["match_confidence_category"],
            })
    return results
