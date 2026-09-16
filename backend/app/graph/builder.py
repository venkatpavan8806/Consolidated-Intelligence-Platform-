"""
Materializes typed, timestamped edges from the structured (CDR, transaction)
and NLP-extracted (FIR co-occurrence) sources into app.graph_edges, then
loads them into a networkx graph for analytics.

Every edge carries relationship_type, source_id/source_type, an optional
timestamp, and a mandatory epistemic_status:
  OBSERVED       -- a structured record (CDR call, bank transfer)
  NLP_EXTRACTED  -- co-occurrence inferred from FIR narrative text
  INFERRED       -- derived from other edges (not produced at ingestion time)
  RECOVERED      -- a missing-link candidate (see app/recovery), never shown
                    as an established fact
"""
import json
import networkx as nx

from app.db.schema import get_connection

# Relationship types considered part of the "analysis" graph used for
# centrality / community / broker scoring. CASE, ORGANIZATION, LOCATION and
# officer/utility-only edges are part of the full evidentiary graph (for the
# investigator's graph explorer) but are deliberately excluded from ranking
# computations -- they are context, not the criminal-activity relationship
# graph a kingpin analysis should run over.
ANALYSIS_RELATIONSHIP_TYPES = {
    "CALL", "TRANSFER", "ASSOCIATED_PHONE", "ASSOCIATED_ACCOUNT",
    "ASSOCIATED_VEHICLE", "CO_MENTIONED_IN_FIR",
}
ANALYSIS_ENTITY_TYPES = {"PERSON", "PHONE", "ACCOUNT", "VEHICLE"}


class EdgeSeq:
    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return f"EDGE{self.n:06d}"


def _entity_for_value(conn, entity_type: str, value: str):
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE entity_type=? AND canonical_value=?",
        (entity_type, value),
    ).fetchone()
    return row["entity_id"] if row else None


def build_edges():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM graph_edges")
    seq = EdgeSeq()
    edges = []

    # --- CASE entities (structured, one per row in `cases`) ---
    for case in cur.execute("SELECT case_id, title FROM cases").fetchall():
        eid = f"ENT_CASE_{case['case_id']}"
        cur.execute(
            """INSERT OR IGNORE INTO entities (entity_id, entity_type, canonical_value, attributes_json)
               VALUES (?, 'CASE', ?, '{}')""",
            (eid, case["title"]),
        )

    # --- OBSERVED: call edges ---
    phone_entity = {}
    for row in cur.execute("SELECT DISTINCT canonical_value, entity_id FROM entities WHERE entity_type='PHONE'"):
        phone_entity[row["canonical_value"]] = row["entity_id"]
    for row in cur.execute("SELECT * FROM cdr_records").fetchall():
        src, tgt = phone_entity.get(row["caller"]), phone_entity.get(row["callee"])
        if not src or not tgt:
            continue
        edges.append({
            "edge_id": seq.next(), "source_entity_id": src, "target_entity_id": tgt,
            "relationship_type": "CALL", "source_record_id": row["record_id"], "source_record_type": "CDR",
            "timestamp": row["timestamp"], "epistemic_status": "OBSERVED", "weight": 1.0,
            "attributes_json": json.dumps({"duration_sec": row["duration_sec"]}),
        })

    # --- OBSERVED: transfer edges ---
    account_entity = {}
    for row in cur.execute("SELECT DISTINCT canonical_value, entity_id FROM entities WHERE entity_type='ACCOUNT'"):
        account_entity[row["canonical_value"]] = row["entity_id"]
    for row in cur.execute("SELECT * FROM transaction_records").fetchall():
        src, tgt = account_entity.get(row["sender"]), account_entity.get(row["receiver"])
        if not src or not tgt:
            continue
        edges.append({
            "edge_id": seq.next(), "source_entity_id": src, "target_entity_id": tgt,
            "relationship_type": "TRANSFER", "source_record_id": row["record_id"], "source_record_type": "TRANSACTION",
            "timestamp": row["timestamp"], "epistemic_status": "OBSERVED", "weight": float(row["amount"]),
            "attributes_json": json.dumps({"amount": row["amount"]}),
        })

    # --- NLP_EXTRACTED: co-occurrence edges from FIRs AND intel reports ---
    # (surveillance reports / intelligence-agency reports go through the
    # identical narrative-text pipeline as FIRs -- see app/extraction -- so
    # they are unioned into one record_meta lookup here rather than special-
    # cased; only source_record_type/provenance differs per record.)
    mentions = [dict(r) for r in cur.execute("SELECT * FROM entity_mentions").fetchall()]
    mention_entity = {r["mention_id"]: r["entity_id"] for r in cur.execute("SELECT * FROM mention_entity_map")}
    record_meta = {
        r["fir_id"]: {"case_id": r["case_id"], "date": r["date"], "record_type": "FIR"}
        for r in cur.execute("SELECT * FROM fir_records")
    }
    record_meta.update({
        r["record_id"]: {"case_id": r["case_id"], "date": r["date"], "record_type": r["source_category"]}
        for r in cur.execute("SELECT * FROM intel_records")
    })

    by_record = {}
    for m in mentions:
        by_record.setdefault(m["source_record_id"], []).append(m)

    REL_FOR_TYPE = {
        "PHONE": "ASSOCIATED_PHONE", "ACCOUNT": "ASSOCIATED_ACCOUNT", "VEHICLE": "ASSOCIATED_VEHICLE",
        "LOCATION": "MENTIONED_AT_LOCATION", "ORGANIZATION": "ASSOCIATED_WITH_ORG",
    }

    for record_id, ms in by_record.items():
        record = record_meta.get(record_id)
        if not record:
            continue
        record_type = record["record_type"]
        persons = [m for m in ms if m["entity_type"] == "PERSON"]
        non_persons = [m for m in ms if m["entity_type"] != "PERSON"]

        for p in persons:
            p_eid = mention_entity.get(p["mention_id"])
            if not p_eid:
                continue
            case_eid = f"ENT_CASE_{record['case_id']}"
            role = p["fir_role"] or "MENTIONED"
            edges.append({
                "edge_id": seq.next(), "source_entity_id": p_eid, "target_entity_id": case_eid,
                "relationship_type": f"{role}_IN_CASE", "source_record_id": record_id, "source_record_type": record_type,
                "timestamp": record["date"], "epistemic_status": "NLP_EXTRACTED", "weight": 1.0,
                "attributes_json": "{}",
            })
            for np in non_persons:
                np_eid = mention_entity.get(np["mention_id"])
                if not np_eid:
                    continue
                edges.append({
                    "edge_id": seq.next(), "source_entity_id": p_eid, "target_entity_id": np_eid,
                    "relationship_type": REL_FOR_TYPE.get(np["entity_type"], "ASSOCIATED_WITH"),
                    "source_record_id": record_id, "source_record_type": record_type,
                    "timestamp": record["date"], "epistemic_status": "NLP_EXTRACTED", "weight": 1.0,
                    "attributes_json": "{}",
                })

        for i in range(len(persons)):
            for j in range(i + 1, len(persons)):
                a_eid, b_eid = mention_entity.get(persons[i]["mention_id"]), mention_entity.get(persons[j]["mention_id"])
                if not a_eid or not b_eid or a_eid == b_eid:
                    continue
                edges.append({
                    "edge_id": seq.next(), "source_entity_id": a_eid, "target_entity_id": b_eid,
                    "relationship_type": "CO_MENTIONED_IN_FIR", "source_record_id": record_id, "source_record_type": record_type,
                    "timestamp": record["date"], "epistemic_status": "NLP_EXTRACTED", "weight": 1.0,
                    "attributes_json": "{}",
                })

    cur.executemany(
        """INSERT INTO graph_edges
           (edge_id, source_entity_id, target_entity_id, relationship_type, source_record_id,
            source_record_type, timestamp, epistemic_status, weight, attributes_json)
           VALUES (:edge_id, :source_entity_id, :target_entity_id, :relationship_type, :source_record_id,
                   :source_record_type, :timestamp, :epistemic_status, :weight, :attributes_json)""",
        edges,
    )
    conn.commit()
    conn.close()
    return {"edges_created": len(edges)}


def load_full_graph(conn) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for row in conn.execute("SELECT * FROM entities").fetchall():
        g.add_node(row["entity_id"], entity_type=row["entity_type"], canonical_value=row["canonical_value"],
                   is_official=bool(row["is_official"]), is_utility=bool(row["is_utility"]))
    for row in conn.execute("SELECT * FROM graph_edges").fetchall():
        g.add_edge(row["source_entity_id"], row["target_entity_id"], key=row["edge_id"],
                   relationship_type=row["relationship_type"], source_record_id=row["source_record_id"],
                   source_record_type=row["source_record_type"], timestamp=row["timestamp"],
                   epistemic_status=row["epistemic_status"], weight=row["weight"])
    return g


def build_analysis_subgraph(conn) -> nx.Graph:
    """The ONE graph every ranking function (degree, betweenness, PageRank,
    Louvain, broker scoring) must build from. Excluded nodes (officials,
    structurally-detected utility numbers) are removed here, structurally --
    not filtered post-hoc by each caller -- so exclusion cannot be missed in
    one function while applied in another (gotcha #4)."""
    full = load_full_graph(conn)
    g = nx.Graph()
    for node, data in full.nodes(data=True):
        if data.get("entity_type") not in ANALYSIS_ENTITY_TYPES:
            continue
        if data.get("is_official") or data.get("is_utility"):
            continue
        g.add_node(node, **data)
    for u, v, data in full.edges(data=True):
        if data.get("relationship_type") not in ANALYSIS_RELATIONSHIP_TYPES:
            continue
        if u not in g or v not in g:
            continue
        if g.has_edge(u, v):
            g[u][v]["weight"] += 1
            g[u][v]["call_count"] = g[u][v].get("call_count", 1) + 1
            g[u][v]["relationship_types"].add(data.get("relationship_type"))
        else:
            g.add_edge(u, v, weight=1, call_count=1, relationship_types={data.get("relationship_type")})
    return g


if __name__ == "__main__":
    print(json.dumps(build_edges(), indent=2))
