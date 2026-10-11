"""
Case-type gating (only a CONFIRMED case type activates its modules) and the
per-case evidence inventory that powers the Case Demo page.

Every test that changes case_case_types snapshots the rows first and restores
them in a finally block, so tests stay independent of run order.
"""
from app.evidence.engine import build_all_leads
from app.evidence.gating import (
    relevant_leads, split_by_activation, module_status, lead_case_type, CROSS_CUTTING_LEAD_TYPES,
)
from app.evidence.summary import evidence_summary
from app.classification.case_type_classifier import classify_case

FRAUD_TYPES = {"BURNER_ROTATION", "MULE_LAYERING", "CALL_BEFORE_TRANSFER"}
CROSS_CUTTING_ON_C001 = {"BROKER_BRIDGE", "IMEI_MSISDN_MAPPING", "IMEI_CORROBORATED_BURNER_SWAP"}


def _snapshot(conn, case_id):
    return [dict(r) for r in conn.execute("SELECT * FROM case_case_types WHERE case_id=?", (case_id,)).fetchall()]


def _restore(conn, case_id, rows):
    conn.execute("DELETE FROM case_case_types WHERE case_id=?", (case_id,))
    for r in rows:
        cols = list(r.keys())
        conn.execute(
            f"INSERT INTO case_case_types ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [r[c] for c in cols],
        )
    conn.commit()


def _set(conn, case_id, case_type, status):
    if status is None:
        conn.execute("DELETE FROM case_case_types WHERE case_id=? AND case_type=?", (case_id, case_type))
    else:
        conn.execute(
            "INSERT INTO case_case_types (case_id, case_type, status) VALUES (?,?,?) "
            "ON CONFLICT(case_id, case_type) DO UPDATE SET status=excluded.status",
            (case_id, case_type, status),
        )
    conn.commit()


def _active_held(conn, case_id):
    active, held = split_by_activation(conn, case_id, relevant_leads(conn, case_id))
    return {l["lead_type"] for l in active}, {l["lead_type"] for l in held}


def test_leads_are_held_back_until_their_case_type_is_confirmed(conn):
    original = _snapshot(conn, "C001")
    try:
        _set(conn, "C001", "FINANCIAL_FRAUD", "CONFIRMED")
        _set(conn, "C001", "ORGANIZED_CRIME", None)
        active, held = _active_held(conn, "C001")
        assert FRAUD_TYPES <= active, "a confirmed case type's modules must be active"
        assert "CROSS_CASE_IDENTIFIER_LINK" in held and "CROSS_CASE_IDENTIFIER_LINK" not in active, \
            "a case type with no row must hold its leads back"

        _set(conn, "C001", "ORGANIZED_CRIME", "SUGGESTED")
        active, held = _active_held(conn, "C001")
        assert "CROSS_CASE_IDENTIFIER_LINK" in held and "CROSS_CASE_IDENTIFIER_LINK" not in active, \
            "a SUGGESTED case type must NOT activate its modules -- only a human confirm does"

        _set(conn, "C001", "ORGANIZED_CRIME", "CONFIRMED")
        active, held = _active_held(conn, "C001")
        assert "CROSS_CASE_IDENTIFIER_LINK" in active and "CROSS_CASE_IDENTIFIER_LINK" not in held, \
            "confirming the case type must activate its leads"

        _set(conn, "C001", "ORGANIZED_CRIME", "REJECTED")
        active, held = _active_held(conn, "C001")
        assert "CROSS_CASE_IDENTIFIER_LINK" in held and "CROSS_CASE_IDENTIFIER_LINK" not in active, \
            "rejecting a case type must switch its modules off again"
    finally:
        _restore(conn, "C001", original)


def test_rejecting_a_case_type_switches_off_its_modules_but_not_cross_cutting_leads(conn):
    original = _snapshot(conn, "C001")
    try:
        _set(conn, "C001", "FINANCIAL_FRAUD", "REJECTED")
        active, held = _active_held(conn, "C001")
        assert FRAUD_TYPES <= held and not (FRAUD_TYPES & active)
        assert CROSS_CUTTING_ON_C001 <= active, "broker-bridge and IMEI leads apply to any case type and stay on"
    finally:
        _restore(conn, "C001", original)


def test_classifier_still_sees_gated_leads_so_it_can_suggest(conn):
    # If the classifier read gated leads it could never suggest a type it was
    # not already told about -- it must keep reading the raw detector output.
    original = _snapshot(conn, "C001")
    try:
        _set(conn, "C001", "FINANCIAL_FRAUD", None)
        _set(conn, "C001", "ORGANIZED_CRIME", None)
        suggested = {s["case_type"] for s in classify_case(conn, "C001")}
        assert "FINANCIAL_FRAUD" in suggested
        assert "ORGANIZED_CRIME" in suggested
    finally:
        _restore(conn, "C001", original)


def test_module_status_reports_active_and_held_back_counts(conn):
    original = _snapshot(conn, "C004")
    try:
        _set(conn, "C004", "ROBBERY_THEFT", "CONFIRMED")
        _set(conn, "C004", "ORGANIZED_CRIME", "SUGGESTED")
        status = module_status(conn, "C004", relevant_leads(conn, "C004"))
        by_type = {m["case_type"]: m for m in status["modules"]}
        assert len(status["modules"]) == 6
        assert by_type["ROBBERY_THEFT"]["status"] == "CONFIRMED"
        assert by_type["ROBBERY_THEFT"]["active_leads"] > 0 and by_type["ROBBERY_THEFT"]["held_back_leads"] == 0
        assert by_type["ORGANIZED_CRIME"]["status"] == "SUGGESTED"
        assert by_type["ORGANIZED_CRIME"]["active_leads"] == 0 and by_type["ORGANIZED_CRIME"]["held_back_leads"] > 0
        assert by_type["NARCOTICS"]["status"] == "NOT_SUGGESTED"
        assert by_type["NARCOTICS"]["active_leads"] == 0 and by_type["NARCOTICS"]["held_back_leads"] == 0

        # Per-lead-type breakdown must add up to the module totals, and name the held-back types.
        org = by_type["ORGANIZED_CRIME"]["lead_type_counts"]
        assert sum(c["held_back"] for c in org.values()) == by_type["ORGANIZED_CRIME"]["held_back_leads"]
        assert org["SYNDICATE_S111_THRESHOLD_MET"]["held_back"] == 1 and org["SYNDICATE_S111_THRESHOLD_MET"]["active"] == 0
        assert by_type["ROBBERY_THEFT"]["lead_type_counts"]["ROBBERY_VEHICLE_LINK"]["active"] == 2

        _set(conn, "C004", "ORGANIZED_CRIME", "CONFIRMED")
        after = {m["case_type"]: m for m in module_status(conn, "C004", relevant_leads(conn, "C004"))["modules"]}
        assert after["ORGANIZED_CRIME"]["held_back_leads"] == 0
        assert after["ORGANIZED_CRIME"]["active_leads"] == by_type["ORGANIZED_CRIME"]["held_back_leads"], \
            "confirming must move exactly the held-back leads into active"
    finally:
        _restore(conn, "C004", original)


def test_every_lead_type_is_mapped_to_a_case_type_or_declared_cross_cutting(conn):
    # Guards against a newly added detector silently bypassing gating.
    emitted = {l["lead_type"] for l in build_all_leads(conn)}
    unmapped = {t for t in emitted if lead_case_type(t) is None}
    assert unmapped <= CROSS_CUTTING_LEAD_TYPES, \
        f"lead types with no case type and not declared cross-cutting: {unmapped - CROSS_CUTTING_LEAD_TYPES}"


def _counts(conn, case_id):
    return {s["key"]: s["count"] for s in evidence_summary(conn, case_id)["sources"]}


def test_evidence_summary_counts_match_the_database_for_every_case(conn):
    for case_id in [r["case_id"] for r in conn.execute("SELECT case_id FROM cases").fetchall()]:
        counts = _counts(conn, case_id)
        for key, table in (("FIR", "fir_records"), ("PROPERTY", "case_property"), ("POSTMORTEM", "post_mortem_report")):
            expected = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE case_id=?", (case_id,)).fetchone()[0]
            assert counts[key] == expected, f"{case_id} {key}"
        assert sum(counts.values()) > 0, f"{case_id} must have at least one connected record"


def test_evidence_summary_splits_digital_from_physical_correctly(conn):
    fraud = evidence_summary(conn, "C001")
    assert fraud["totals"]["DIGITAL"] > 0 and fraud["totals"]["PHYSICAL"] == 0, \
        "the fraud case is digital-only: FIRs, calls and transfers, no physical-evidence paperwork"
    fraud_counts = {s["key"]: s["count"] for s in fraud["sources"]}
    assert fraud_counts["CDR"] > 0 and fraud_counts["TXN"] > 0

    narcotics = _counts(conn, "C003")
    assert narcotics["NDPS"] > 0 and narcotics["CDR"] == 0 and narcotics["TXN"] == 0

    trafficking = _counts(conn, "C002")
    assert trafficking["UIDB"] > 0 and trafficking["MISSING"] > 0 and trafficking["DNA"] > 0

    assault = _counts(conn, "C006")
    assert assault["INQUEST"] > 0 and assault["POSTMORTEM"] > 0 and assault["TOWER"] > 0
    assert assault["FORENSIC"] > 0, "forensic matches link C006 to C007 via case_id_a/case_id_b"


def test_retired_women_safety_endpoint_returns_empty_shape_for_older_frontends():
    # A frontend build older than the backend still requests this on every case
    # load; it must answer with the old shape (all empty), not 404.
    from app.api.routes import women_safety_retired

    assert women_safety_retired(reason="compat check", user={"username": "admin1", "role": "admin"}) == {
        "leads": [], "recruiters": [], "transporters": [], "repeat_locations": [], "chain_candidates": [],
    }
