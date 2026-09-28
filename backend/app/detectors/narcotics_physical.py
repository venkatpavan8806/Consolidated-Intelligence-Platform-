"""
Narcotics Physical-evidence detector: NDPS s.52A / Test-Memo (Form-6)
chain-of-custody compliance checks.

Every rule here compares fields the platform actually stores against the
research-verified NDPS Rules 2022 (GSR 899(E)) sampling requirements and the
Supreme Court's s.52A case law -- never a person score. Per *Bharat Aambale
v. State of Chhattisgarh* (2025 INSC 78), a bare procedural lapse is a risk
indicator; it becomes outcome-determinative only when combined with an
actual discrepancy in the physical evidence -- which is exactly what
comparing the Test Memo against the lab-receipt record detects. Per
*Yusuf @ Asif v. State* (2023 INSC 912), a missing magistrate certification
is independently fatal on its own.

Every finding here is a candidate compliance flag for a human investigator
to verify against the case file -- never an automated finding of guilt or
of case dismissal.
"""
from datetime import datetime

from app.config import (
    NDPS_SAMPLE_MIN_GRAMS, NDPS_SAMPLE_MIN_GRAMS_DEFAULT,
    NDPS_LOT_SIZE_MAX_DEFAULT, NDPS_LOT_SIZE_MAX_BULK,
    NDPS_WEIGHT_MISMATCH_TOLERANCE_FRACTION, NDPS_WEIGHT_MISMATCH_TOLERANCE_GRAMS,
)

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    if not ts:
        return None
    return datetime.strptime(ts, FMT)


def _sample_min_grams(drug_description: str) -> float:
    key = (drug_description or "").strip().lower()
    return NDPS_SAMPLE_MIN_GRAMS.get(key, NDPS_SAMPLE_MIN_GRAMS_DEFAULT)


def _lot_size_max(drug_description: str) -> int:
    key = (drug_description or "").strip().lower()
    return NDPS_LOT_SIZE_MAX_BULK.get(key, NDPS_LOT_SIZE_MAX_DEFAULT)


def detect_ndps_compliance_flags(conn):
    """Returns one result dict per ndps_sampling record that has at least
    one compliance flag. Each flag is independently explainable and traces
    to the exact stored fields that triggered it."""
    results = []

    memos = conn.execute(
        "SELECT ns.*, cp.case_id, cp.seizure_datetime, cp.property_id "
        "FROM ndps_sampling ns JOIN case_property cp ON ns.property_id = cp.property_id"
    ).fetchall()

    for memo in memos:
        flags = []

        # Signal 1: magistrate certification missing (Yusuf @ Asif) -- HIGH
        if not memo["magistrate_certification_ts"]:
            flags.append({
                "flag": "MAGISTRATE_CERTIFICATION_MISSING",
                "severity": "HIGH",
                "detail": "No magistrate_certification_ts recorded under NDPS s.52A(2); a gazetted "
                          "officer's presence alone is not sufficient compliance (Yusuf @ Asif v. State, "
                          "2023 INSC 912).",
            })

        # Signal 2: weight mismatch between seizure and lab-received weight (Bharat Aambale) -- HIGH
        if memo["net_weight_lab_received"] is not None:
            seized = memo["net_weight_seized"]
            received = memo["net_weight_lab_received"]
            tolerance = max(seized * NDPS_WEIGHT_MISMATCH_TOLERANCE_FRACTION,
                             NDPS_WEIGHT_MISMATCH_TOLERANCE_GRAMS)
            diff = abs(seized - received)
            if diff > tolerance:
                flags.append({
                    "flag": "WEIGHT_MISMATCH",
                    "severity": "HIGH",
                    "detail": f"Test Memo net weight {seized}g vs lab-received weight {received}g "
                              f"differs by {diff:.2f}g, exceeding the {tolerance:.2f}g tolerance -- a "
                              f"'discrepancy in physical evidence' under Bharat Aambale v. State of "
                              f"Chhattisgarh (2025 INSC 78).",
                })

        # Signal 3: seal not intact/tallied at lab receipt -- HIGH
        lab_receipt = conn.execute(
            "SELECT * FROM custody_event WHERE property_id=? AND event_type='LAB_RECEIPT' "
            "ORDER BY event_ts DESC LIMIT 1",
            (memo["property_id"],),
        ).fetchone()
        if lab_receipt is not None and lab_receipt["seals_intact_and_tallied"] == 0:
            flags.append({
                "flag": "SEAL_MISMATCH",
                "severity": "HIGH",
                "detail": "Lab-receipt record marks seals as NOT intact/tallied against the forwarding "
                          "authority's specimen seal -- a chain-of-custody break.",
            })

        # Signal 4: sample quantity below the GSR 899(E) rule minimum -- MEDIUM
        if memo["sample_weight_each"] is not None:
            min_required = _sample_min_grams(memo["drug_description"])
            if memo["sample_weight_each"] < min_required:
                flags.append({
                    "flag": "SAMPLE_BELOW_RULE_MINIMUM",
                    "severity": "MEDIUM",
                    "detail": f"Sample drawn ({memo['sample_weight_each']}g) is below the GSR 899(E) "
                              f"minimum of {min_required}g for {memo['drug_description']}.",
                })

        # Signal 5: lot size exceeds the bunching limit -- MEDIUM
        if memo["lot_size"] is not None:
            max_lot = _lot_size_max(memo["drug_description"])
            if memo["lot_size"] > max_lot:
                flags.append({
                    "flag": "LOT_SIZE_EXCEEDED",
                    "severity": "MEDIUM",
                    "detail": f"Lot of {memo['lot_size']} packages exceeds the GSR 899(E) bunching limit "
                              f"of {max_lot} for {memo['drug_description']}.",
                })

        # Signal 6: not prepared in triplicate, or sample drawn before seizure -- HIGH
        if memo["prepared_in_triplicate"] == 0:
            flags.append({
                "flag": "TEST_MEMO_NOT_TRIPLICATE",
                "severity": "HIGH",
                "detail": "Test Memo (Form-6) not recorded as prepared in triplicate per NCB procedure.",
            })
        draw_dt = _parse(memo["date_of_draw_of_sample"])
        seizure_dt = _parse(memo["seizure_datetime"])
        if draw_dt is not None and seizure_dt is not None and draw_dt < seizure_dt:
            flags.append({
                "flag": "SAMPLE_DRAWN_BEFORE_SEIZURE",
                "severity": "HIGH",
                "detail": f"date_of_draw_of_sample ({memo['date_of_draw_of_sample']}) is earlier than "
                          f"seizure_datetime ({memo['seizure_datetime']}) -- a date-sequence impossibility.",
            })

        # Signal 7: disposal certificate chain incomplete -- HIGH
        has_form7 = bool(memo["disposal_form7_ref"])
        has_form10 = bool(memo["disposal_form10_ref"])
        if has_form7 != has_form10:
            flags.append({
                "flag": "DISPOSAL_CERTIFICATE_INCOMPLETE",
                "severity": "HIGH",
                "detail": "Disposal recorded with only one of Form-7 (certificate of destruction) / "
                          "Form-10 (certificate of disposal) present, not both.",
            })

        if flags:
            results.append({
                "memo_id": memo["memo_id"],
                "property_id": memo["property_id"],
                "case_id": memo["case_id"],
                "crime_no": memo["crime_no"],
                "drug_description": memo["drug_description"],
                "flags": flags,
            })

    return results
