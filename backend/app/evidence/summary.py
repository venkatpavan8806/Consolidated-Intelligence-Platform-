"""
Per-case evidence inventory: which Digital and Physical records are actually
connected for a case, with live counts straight from the database.

Powers the "Case Demo" page's "what are we connecting?" section, so what the
page says is in the data is always what is in the data -- never a hand-typed
number that can drift from the seed.

Digital = records the platform reads directly (FIRs, call/transaction/tower
records, charge-sheets). Physical = records ABOUT physical evidence (seizure
registers, forensic/post-mortem/inquest reports, DNA chain-of-custody) -- the
platform never ingests a physical object, only the paperwork describing it.
"""
from app.graph.case_view import get_case_entity_ids

DIGITAL = "DIGITAL"
PHYSICAL = "PHYSICAL"


def _count(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _entity_values(conn, case_id: str, entity_type: str) -> list:
    ids = list(get_case_entity_ids(conn, case_id))
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT canonical_value FROM entities WHERE entity_type=? AND entity_id IN ({marks})",
        [entity_type, *ids],
    ).fetchall()
    return [r["canonical_value"] for r in rows]


def _touching(conn, table: str, col_a: str, col_b: str, values: list) -> int:
    if not values:
        return 0
    marks = ",".join("?" * len(values))
    return _count(
        conn,
        f"SELECT COUNT(*) FROM {table} WHERE {col_a} IN ({marks}) OR {col_b} IN ({marks})",
        [*values, *values],
    )


def evidence_summary(conn, case_id: str) -> dict:
    phones = _entity_values(conn, case_id, "PHONE")
    accounts = _entity_values(conn, case_id, "ACCOUNT")

    by_case = lambda table: _count(conn, f"SELECT COUNT(*) FROM {table} WHERE case_id=?", (case_id,))
    via_property = lambda table: _count(
        conn,
        f"SELECT COUNT(*) FROM {table} t JOIN case_property p ON t.property_id = p.property_id WHERE p.case_id=?",
        (case_id,),
    )

    sources = [
        # ---- Digital ----
        ("FIR", "FIRs & police reports", DIGITAL, by_case("fir_records")),
        ("INTEL", "Surveillance & intelligence-agency reports", DIGITAL, by_case("intel_records")),
        ("CDR", "Call records touching this case's phones", DIGITAL,
         _touching(conn, "cdr_records", "caller", "callee", phones)),
        ("TXN", "Bank transfers touching this case's accounts", DIGITAL,
         _touching(conn, "transaction_records", "sender", "receiver", accounts)),
        ("TOWER", "Cell-tower location records", DIGITAL, by_case("tower_location_record")),
        ("MO", "Modus-operandi forms (NCRB IIF-II)", DIGITAL, by_case("crime_mo_record")),
        ("IDINDEX", "Cross-case identifier index (phones, accounts, vehicles)", DIGITAL, by_case("common_identifier_index")),
        ("CHARGESHEET", "Charge-sheets", DIGITAL, by_case("charge_sheet")),
        # ---- Physical (records about physical evidence) ----
        ("PROPERTY", "Seizure & property registers", PHYSICAL, by_case("case_property")),
        ("PROPERTY_ITEM", "Individual seized / recovered items", PHYSICAL, via_property("property_item")),
        ("NDPS", "NDPS Test Memos (Form-6)", PHYSICAL, via_property("ndps_sampling")),
        ("CUSTODY", "Chain-of-custody events", PHYSICAL, via_property("custody_event")),
        ("POSTMORTEM", "Post-mortem reports", PHYSICAL, by_case("post_mortem_report")),
        ("INQUEST", "Inquest reports", PHYSICAL, by_case("inquest_report")),
        ("MLC", "Medico-legal case (MLC) records", PHYSICAL, by_case("mlc_record")),
        ("FORENSIC", "Forensic match records (fingerprint / ballistics / DNA)", PHYSICAL,
         _count(conn, "SELECT COUNT(*) FROM forensic_match WHERE case_id_a=? OR case_id_b=?", (case_id, case_id))),
        ("MISSING", "Missing-person reports", PHYSICAL, by_case("missing_person_report")),
        ("UIDB", "Unidentified dead-body (UIDB) records", PHYSICAL, by_case("uidb_record")),
        ("DNA", "DNA sample chain-of-custody records", PHYSICAL, by_case("dna_sample_record")),
    ]

    items = [{"key": k, "label": label, "branch": branch, "count": n} for k, label, branch, n in sources]
    return {
        "case_id": case_id,
        "sources": items,
        "totals": {
            DIGITAL: sum(i["count"] for i in items if i["branch"] == DIGITAL),
            PHYSICAL: sum(i["count"] for i in items if i["branch"] == PHYSICAL),
        },
    }
