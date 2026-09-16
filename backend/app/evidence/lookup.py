import json


def get_entity_detail(conn, entity_id: str) -> dict:
    entity = conn.execute("SELECT * FROM entities WHERE entity_id=?", (entity_id,)).fetchone()
    if not entity:
        return None
    entity = dict(entity)
    entity["attributes"] = json.loads(entity.pop("attributes_json") or "{}")

    mentions = conn.execute(
        """SELECT em.* FROM entity_mentions em
           JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
           WHERE mem.entity_id = ?""",
        (entity_id,),
    ).fetchall()
    mentions = [dict(m) for m in mentions]

    fir_ids = sorted({m["source_record_id"] for m in mentions if m["source_type"] == "FIR"})
    firs = [dict(r) for r in conn.execute(
        f"SELECT * FROM fir_records WHERE fir_id IN ({','.join('?' for _ in fir_ids)})", fir_ids
    ).fetchall()] if fir_ids else []

    intel_ids = sorted({m["source_record_id"] for m in mentions if m["source_type"] in ("SURVEILLANCE_REPORT", "INTELLIGENCE_AGENCY_REPORT")})
    intel_reports = [dict(r) for r in conn.execute(
        f"SELECT * FROM intel_records WHERE record_id IN ({','.join('?' for _ in intel_ids)})", intel_ids
    ).fetchall()] if intel_ids else []

    edges = conn.execute(
        "SELECT * FROM graph_edges WHERE source_entity_id=? OR target_entity_id=?",
        (entity_id, entity_id),
    ).fetchall()
    edges = [dict(e) for e in edges]

    cdr_ids = sorted({e["source_record_id"] for e in edges if e["source_record_type"] == "CDR"})
    txn_ids = sorted({e["source_record_id"] for e in edges if e["source_record_type"] == "TRANSACTION"})
    cdrs = [dict(r) for r in conn.execute(
        f"SELECT * FROM cdr_records WHERE record_id IN ({','.join('?' for _ in cdr_ids)})", cdr_ids
    ).fetchall()] if cdr_ids else []
    txns = [dict(r) for r in conn.execute(
        f"SELECT * FROM transaction_records WHERE record_id IN ({','.join('?' for _ in txn_ids)})", txn_ids
    ).fetchall()] if txn_ids else []

    return {
        "entity": entity,
        "mentions": mentions,
        "fir_records": firs,
        "intel_records": intel_reports,
        "cdr_records": cdrs,
        "transaction_records": txns,
        "edges": edges,
    }
