"""Builds a case-scoped view of the graph for the investigator's graph
explorer: FIR-linked entities plus the call/transaction network they touch,
expanded two hops so structural patterns (burner rotation, mule layering,
broker bridges) are visible even though those nodes aren't directly named in
a case's FIR text."""
from app.graph.builder import load_full_graph


def _fir_mentioned_entity_ids(conn, case_id: str) -> set:
    """Entities named in ANY of this case's narrative-text records -- FIRs,
    surveillance reports, or intelligence-agency reports alike, since all
    three are extracted through the same pipeline and mentions carry a
    source-agnostic source_record_id."""
    record_ids = [r["fir_id"] for r in conn.execute("SELECT fir_id FROM fir_records WHERE case_id=?", (case_id,)).fetchall()]
    record_ids += [r["record_id"] for r in conn.execute("SELECT record_id FROM intel_records WHERE case_id=?", (case_id,)).fetchall()]
    if not record_ids:
        return set()
    placeholders = ",".join("?" for _ in record_ids)
    rows = conn.execute(
        f"""SELECT DISTINCT mem.entity_id FROM entity_mentions em
            JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
            WHERE em.source_record_id IN ({placeholders})""",
        record_ids,
    ).fetchall()
    return {r["entity_id"] for r in rows}


def build_case_graph(conn, case_id: str) -> dict:
    g = load_full_graph(conn)
    case_eid = f"ENT_CASE_{case_id}"
    if case_eid not in g:
        return {"nodes": [], "links": []}

    seed_persons = {u for u, v, d in g.in_edges(case_eid, data=True) if d.get("relationship_type", "").endswith("_IN_CASE")}

    nodes = set(seed_persons)
    for p in seed_persons:
        nodes.update(g.successors(p))
        nodes.update(g.predecessors(p))
    # Any entity directly named in one of this case's FIRs is part of the
    # case even if no role-labeled PERSON co-occurs in that same sentence
    # (e.g. a purely numeric intelligence note: "phone X was flagged...").
    nodes |= {eid for eid in _fir_mentioned_entity_ids(conn, case_id) if eid in g}
    nodes.discard(case_eid)

    # Fully expand through the CALL/TRANSFER network reachable from any
    # phone/account pulled in so far (BFS to a fixed point, not just one
    # hop) -- once a suspect's account is linked into a financial network,
    # an investigator needs the whole connected funnel, not a single hop
    # of it (e.g. a mule-layering chain is several hops of fan-in/fan-out).
    frontier = {n for n in nodes if g.nodes[n].get("entity_type") in ("PHONE", "ACCOUNT")}
    visited = set(frontier)
    while frontier:
        next_frontier = set()
        for n in frontier:
            for _, v, d in g.out_edges(n, data=True):
                if d.get("relationship_type") in ("CALL", "TRANSFER") and v not in visited:
                    next_frontier.add(v)
            for u, _, d in g.in_edges(n, data=True):
                if d.get("relationship_type") in ("CALL", "TRANSFER") and u not in visited:
                    next_frontier.add(u)
        visited |= next_frontier
        frontier = next_frontier
    nodes |= visited

    nodes.discard(case_eid)

    node_list = []
    for n in nodes:
        data = g.nodes[n]
        node_list.append({
            "id": n,
            "label": data.get("canonical_value", n),
            "entity_type": data.get("entity_type"),
            "is_official": bool(data.get("is_official")),
            "is_utility": bool(data.get("is_utility")),
        })

    link_list = []
    seen_edges = set()
    for u, v, k, d in g.edges(keys=True, data=True):
        if u not in nodes or v not in nodes:
            continue
        edge_key = (u, v, d.get("relationship_type"), d.get("source_record_id"))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        link_list.append({
            "source": u, "target": v,
            "relationship_type": d.get("relationship_type"),
            "epistemic_status": d.get("epistemic_status"),
            "source_record_id": d.get("source_record_id"),
            "source_record_type": d.get("source_record_type"),
            "timestamp": d.get("timestamp"),
        })

    return {"nodes": node_list, "links": link_list}


def get_case_entity_ids(conn, case_id: str) -> set:
    """Every entity relevant to a case: anything directly mentioned in one of
    its FIRs, unioned with the case graph's multi-hop expansion into the
    call/transaction network (structural patterns like a burner rotation or
    mule layering chain are often introduced by a single contextual FIR
    sentence with no role-labeled person, so a pure person-centric traversal
    alone would miss them)."""
    graph_view = build_case_graph(conn, case_id)
    graph_entity_ids = {n["id"] for n in graph_view["nodes"]}
    return _fir_mentioned_entity_ids(conn, case_id) | graph_entity_ids
