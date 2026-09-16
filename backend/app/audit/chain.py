"""
Tamper-evident SHA-256 hash-chain audit log. Every analytical action (query,
graph snapshot, lead generation, disposition) is appended here. Each entry's
raw string is stored verbatim (payload_raw) so the browser can independently
recompute hash = SHA256(prev_hash + "|" + payload_raw) via Web Crypto
SubtleCrypto WITHOUT having to reimplement Python's JSON/dict serialization
to get a byte-identical string -- see app/api/routes_audit.py.
"""
import hashlib
import json
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _build_payload_raw(seq, timestamp, actor, action, case_id, reason, extra):
    parts = [str(seq), timestamp, actor, action, case_id or "", reason or ""]
    if extra:
        parts.append(json.dumps(extra, sort_keys=True, separators=(",", ":")))
    return "|".join(parts)


def _hash(prev_hash: str, payload_raw: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{payload_raw}".encode("utf-8")).hexdigest()


def append_entry(conn, actor: str, action: str, case_id: str = None, reason: str = None, extra: dict = None) -> dict:
    # BEGIN IMMEDIATE takes the write lock up front so concurrent requests
    # (the dashboard fires several audit-logged queries in parallel) can't
    # interleave their read-max-seq-then-insert steps and collide on seq.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()
    last = cur.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = last["hash"] if last else GENESIS_HASH
    next_seq = cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM audit_log").fetchone()["n"]
    timestamp = _now()
    payload_raw = _build_payload_raw(next_seq, timestamp, actor, action, case_id, reason, extra)
    entry_hash = _hash(prev_hash, payload_raw)
    cur.execute(
        """INSERT INTO audit_log (seq, timestamp, actor, action, case_id, reason, payload_raw, prev_hash, hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (next_seq, timestamp, actor, action, case_id, reason, payload_raw, prev_hash, entry_hash),
    )
    conn.commit()
    return {"seq": next_seq, "timestamp": timestamp, "hash": entry_hash}


def get_chain(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY seq ASC").fetchall()]


def verify_chain(conn) -> dict:
    entries = get_chain(conn)
    broken_at = []
    expected_prev = GENESIS_HASH
    for e in entries:
        recomputed = _hash(e["prev_hash"], e["payload_raw"])
        if e["prev_hash"] != expected_prev or recomputed != e["hash"]:
            broken_at.append(e["seq"])
        expected_prev = e["hash"]
    return {"valid": len(broken_at) == 0, "entry_count": len(entries), "broken_at_seq": broken_at}


def tamper_entry(conn, seq: int, new_reason: str) -> dict:
    """Demo-only: mutate a stored entry's reason field directly (bypassing
    append_entry, i.e. not recomputing the hash) to demonstrate detection."""
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM audit_log WHERE seq = ?", (seq,)).fetchone()
    if not row:
        raise ValueError(f"no audit entry with seq={seq}")
    original = dict(row)
    new_payload_raw = _build_payload_raw(row["seq"], row["timestamp"], row["actor"], row["action"],
                                          row["case_id"], new_reason, None)
    cur.execute("UPDATE audit_log SET reason = ?, payload_raw = ? WHERE seq = ?",
                (new_reason, new_payload_raw, seq))
    conn.commit()
    return {"seq": seq, "original": original, "tampered_reason": new_reason}


def restore_entry(conn, seq: int, original_reason: str, original_payload_raw: str):
    cur = conn.cursor()
    cur.execute("UPDATE audit_log SET reason = ?, payload_raw = ? WHERE seq = ?",
                (original_reason, original_payload_raw, seq))
    conn.commit()
    return {"seq": seq, "restored": True}
