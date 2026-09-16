import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.schema import get_connection
from app.auth.rbac import authenticate, create_token, get_current_user, require_case_access, require_admin
from app.api.schemas import (
    LoginRequest, DispositionRequest, ReviewResolutionRequest, TamperDemoRequest, RestoreDemoRequest,
)
from app.audit import chain as audit_chain
from app.graph.case_view import build_case_graph, get_case_entity_ids
from app.graph.analytics import run_full_analytics, top_n
from app.evidence.engine import build_leads, build_women_safety_leads, build_all_leads
from app.evidence.lookup import get_entity_detail
from app.evaluation.self_eval import run_self_evaluation
from app.pipeline import run_full_pipeline

router = APIRouter()


def _conn():
    return get_connection()


@router.post("/auth/login")
def login(body: LoginRequest):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_token(user["username"], user["role"])
    return {"token": token, "role": user["role"], "username": user["username"], "display_name": user["display_name"]}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/cases")
def list_cases(user: dict = Depends(get_current_user)):
    conn = _conn()
    if user["role"] == "admin":
        rows = conn.execute("SELECT * FROM cases").fetchall()
    else:
        rows = conn.execute(
            "SELECT c.* FROM cases c JOIN case_assignments ca ON c.case_id = ca.case_id WHERE ca.username = ?",
            (user["username"],),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/cases/{case_id}/graph")
def case_graph(case_id: str, reason: str = Query(..., min_length=3), user: dict = Depends(get_current_user)):
    require_case_access(case_id, user)
    conn = _conn()
    graph = build_case_graph(conn, case_id)
    audit_chain.append_entry(conn, user["username"], "QUERY_GRAPH", case_id=case_id, reason=reason)
    conn.close()
    return graph


@router.get("/cases/{case_id}/leads")
def case_leads(case_id: str, reason: str = Query(..., min_length=3), user: dict = Depends(get_current_user)):
    require_case_access(case_id, user)
    conn = _conn()
    case_node_ids = get_case_entity_ids(conn, case_id)
    all_leads = build_all_leads(conn)
    relevant = [l for l in all_leads if case_node_ids.intersection(l["entities_involved"])]

    dispositions = {r["lead_id"]: dict(r) for r in conn.execute("SELECT * FROM lead_dispositions").fetchall()}
    for lead in relevant:
        lead["disposition"] = dispositions.get(lead["lead_id"])

    audit_chain.append_entry(conn, user["username"], "GENERATE_LEADS", case_id=case_id, reason=reason,
                              extra={"lead_count": len(relevant)})
    conn.close()
    return relevant


@router.post("/leads/{lead_id}/disposition")
def set_disposition(lead_id: str, body: DispositionRequest, user: dict = Depends(get_current_user)):
    if body.disposition not in ("USEFUL", "ALREADY_KNOWN", "WRONG_PERSON"):
        raise HTTPException(status_code=400, detail="invalid disposition value")
    conn = _conn()
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT INTO lead_dispositions (lead_id, disposition, actor, timestamp, notes)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(lead_id) DO UPDATE SET disposition=excluded.disposition, actor=excluded.actor,
               timestamp=excluded.timestamp, notes=excluded.notes""",
        (lead_id, body.disposition, user["username"], ts, body.notes),
    )
    conn.commit()
    audit_chain.append_entry(conn, user["username"], "LEAD_DISPOSITION", reason=f"disposition set on {lead_id}",
                              extra={"lead_id": lead_id, "disposition": body.disposition})
    conn.close()
    return {"lead_id": lead_id, "disposition": body.disposition, "timestamp": ts}


@router.get("/review-queue")
def review_queue(user: dict = Depends(get_current_user)):
    conn = _conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM review_queue").fetchall()]
    for r in rows:
        mention_ids = json.loads(r["mention_ids_json"])
        mentions = conn.execute(
            f"SELECT * FROM entity_mentions WHERE mention_id IN ({','.join('?' for _ in mention_ids)})",
            mention_ids,
        ).fetchall()
        r["mentions"] = [dict(m) for m in mentions]
        del r["mention_ids_json"]
    conn.close()
    return rows


@router.post("/review-queue/{cluster_id}/resolve")
def resolve_review_cluster(cluster_id: str, body: ReviewResolutionRequest, user: dict = Depends(get_current_user)):
    if body.decision not in ("MERGE", "KEEP_SEPARATE", "ESCALATE"):
        raise HTTPException(status_code=400, detail="invalid decision")
    conn = _conn()
    row = conn.execute("SELECT * FROM review_queue WHERE cluster_id=?", (cluster_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="cluster not found")
    conn.execute("UPDATE review_queue SET status=? WHERE cluster_id=?", (f"RESOLVED_{body.decision}", cluster_id))
    conn.commit()
    audit_chain.append_entry(conn, user["username"], "REVIEW_QUEUE_RESOLUTION",
                              reason=body.notes or f"resolved {cluster_id} as {body.decision}",
                              extra={"cluster_id": cluster_id, "decision": body.decision})
    conn.close()
    return {"cluster_id": cluster_id, "status": f"RESOLVED_{body.decision}"}


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: str, user: dict = Depends(get_current_user)):
    conn = _conn()
    detail = get_entity_detail(conn, entity_id)
    conn.close()
    if not detail:
        raise HTTPException(status_code=404, detail="entity not found")
    return detail


@router.get("/analytics/summary")
def analytics_summary(reason: str = Query(..., min_length=3), user: dict = Depends(get_current_user)):
    conn = _conn()
    analytics = run_full_analytics(conn)

    def label_scores(scores):
        out = []
        for eid, score in top_n(scores, 15):
            row = conn.execute("SELECT canonical_value, entity_type FROM entities WHERE entity_id=?", (eid,)).fetchone()
            out.append({"entity_id": eid, "label": row["canonical_value"] if row else eid,
                        "entity_type": row["entity_type"] if row else None, "score": score})
        return out

    result = {
        "top_degree": label_scores(analytics["degree"]),
        "top_betweenness": label_scores(analytics["betweenness"]),
        "top_pagerank": label_scores(analytics["pagerank"]),
        "top_broker": label_scores(analytics["broker"]),
        "community_count": len(set(analytics["membership"].values())),
        "analysis_graph_size": {"nodes": analytics["graph"].number_of_nodes(), "edges": analytics["graph"].number_of_edges()},
    }
    audit_chain.append_entry(conn, user["username"], "QUERY_ANALYTICS", reason=reason)
    conn.close()
    return result


@router.get("/women-safety")
def women_safety(reason: str = Query(..., min_length=3), user: dict = Depends(get_current_user)):
    conn = _conn()
    leads = build_women_safety_leads(conn)

    from app.graph.builder import build_analysis_subgraph
    from app.graph.analytics import compute_communities
    from app.detectors.women_safety import detect_transporter_candidates, detect_repeat_locations

    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    result = detect_transporter_candidates(g, membership)

    def label(eid):
        row = conn.execute("SELECT canonical_value, entity_type FROM entities WHERE entity_id=?", (eid,)).fetchone()
        return {"entity_id": eid, "label": row["canonical_value"] if row else eid,
                "entity_type": row["entity_type"] if row else None}

    recruiters = [{**label(eid), "fanout_count": info["fanout_count"]} for eid, info in result["recruiters"].items()]
    transporters = [{**label(eid), "methods": info["methods"], "detail": info["detail"]}
                     for eid, info in result["transporters"].items()]
    repeat_locations = detect_repeat_locations(conn)

    chain_candidates = []
    recruiter_ids = {r["entity_id"] for r in recruiters}
    transporter_ids = {t["entity_id"] for t in transporters}
    for t in transporters:
        matches = t["detail"].get("STRUCTURAL_BRIDGE_PATH", {}).get("matches", [])
        for m in matches:
            if m["recruiter"] in recruiter_ids:
                chain_candidates.append({
                    "recruiter": label(m["recruiter"]),
                    "transporter": label(t["entity_id"]),
                    "receiver_side": label(m["high_degree_side_neighbor"]),
                })

    audit_chain.append_entry(conn, user["username"], "QUERY_WOMEN_SAFETY_VIEW", reason=reason)
    conn.close()
    return {
        "leads": leads, "recruiters": recruiters, "transporters": transporters,
        "repeat_locations": repeat_locations, "chain_candidates": chain_candidates,
    }


@router.get("/evaluation")
def evaluation(user: dict = Depends(get_current_user)):
    conn = _conn()
    result = run_self_evaluation(conn)
    conn.close()
    return result


@router.get("/audit/chain")
def audit_log(user: dict = Depends(get_current_user)):
    conn = _conn()
    entries = audit_chain.get_chain(conn)
    verification = audit_chain.verify_chain(conn)
    conn.close()
    return {"entries": entries, "verification": verification}


@router.post("/audit/tamper-demo")
def tamper_demo(body: TamperDemoRequest, user: dict = Depends(require_admin)):
    conn = _conn()
    try:
        result = audit_chain.tamper_entry(conn, body.seq, body.new_reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    conn.close()
    return result


@router.post("/audit/restore-demo")
def restore_demo(body: RestoreDemoRequest, user: dict = Depends(require_admin)):
    conn = _conn()
    result = audit_chain.restore_entry(conn, body.seq, body.original_reason, body.original_payload_raw)
    conn.close()
    return result


@router.post("/pipeline/run")
def pipeline_run(user: dict = Depends(require_admin)):
    return run_full_pipeline(reset_data=True)
