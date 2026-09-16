"""
Cross-source temporal motif detector: a call between two phones followed by
a large transfer between the accounts those phones are linked to (via FIR
co-occurrence: PERSON <-ASSOCIATED_PHONE-> PHONE and PERSON <-ASSOCIATED_ACCOUNT->
ACCOUNT), within a short window.

"Large" is not a hard-coded number: it is derived from this run's own
transaction amount distribution (mean + 3 standard deviations), so the
threshold adapts to whatever data is actually loaded rather than being
tuned to this one synthetic dataset.
"""
import statistics
from datetime import datetime
from collections import defaultdict

from app.config import MOTIF_CALL_BEFORE_TRANSFER_MIN_MINUTES, MOTIF_CALL_BEFORE_TRANSFER_MAX_MINUTES

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def _phone_to_accounts_via_person(conn):
    person_to_phones = defaultdict(set)
    person_to_accounts = defaultdict(set)
    for row in conn.execute(
        "SELECT source_entity_id, target_entity_id, relationship_type FROM graph_edges "
        "WHERE relationship_type IN ('ASSOCIATED_PHONE','ASSOCIATED_ACCOUNT')"
    ).fetchall():
        if row["relationship_type"] == "ASSOCIATED_PHONE":
            person_to_phones[row["source_entity_id"]].add(row["target_entity_id"])
        else:
            person_to_accounts[row["source_entity_id"]].add(row["target_entity_id"])

    phone_to_accounts = defaultdict(set)
    for person, phones in person_to_phones.items():
        accounts = person_to_accounts.get(person, set())
        if not accounts:
            continue
        for phone in phones:
            phone_to_accounts[phone] |= accounts
    return phone_to_accounts


def _large_amount_threshold(conn):
    amounts = [r["amount"] for r in conn.execute("SELECT amount FROM transaction_records").fetchall()]
    if len(amounts) < 2:
        return float("inf")
    return statistics.mean(amounts) + 3 * statistics.pstdev(amounts)


def detect_call_before_transfer(conn):
    phone_to_accounts = _phone_to_accounts_via_person(conn)
    threshold = _large_amount_threshold(conn)

    calls = conn.execute(
        "SELECT source_entity_id AS a, target_entity_id AS b, timestamp, source_record_id "
        "FROM graph_edges WHERE relationship_type='CALL'"
    ).fetchall()
    transfers = [dict(r) for r in conn.execute(
        "SELECT source_entity_id AS a, target_entity_id AS b, timestamp, weight AS amount, source_record_id "
        "FROM graph_edges WHERE relationship_type='TRANSFER'"
    ).fetchall()]

    hits = []
    for call in calls:
        accs_a = phone_to_accounts.get(call["a"], set())
        accs_b = phone_to_accounts.get(call["b"], set())
        if not accs_a or not accs_b:
            continue
        call_ts = _parse(call["timestamp"])
        for t in transfers:
            if t["amount"] < threshold:
                continue
            pair_match = (t["a"] in accs_a and t["b"] in accs_b) or (t["a"] in accs_b and t["b"] in accs_a)
            if not pair_match:
                continue
            transfer_ts = _parse(t["timestamp"])
            delta_minutes = (transfer_ts - call_ts).total_seconds() / 60
            if MOTIF_CALL_BEFORE_TRANSFER_MIN_MINUTES <= delta_minutes <= MOTIF_CALL_BEFORE_TRANSFER_MAX_MINUTES:
                hits.append({
                    "call_phones": [call["a"], call["b"]],
                    "call_record_id": call["source_record_id"],
                    "call_timestamp": call["timestamp"],
                    "transfer_accounts": [t["a"], t["b"]],
                    "transfer_record_id": t["source_record_id"],
                    "transfer_timestamp": t["timestamp"],
                    "transfer_amount": t["amount"],
                    "minutes_between": round(delta_minutes, 1),
                    "amount_threshold_used": round(threshold, 2),
                })
    return hits
