"""
Missing-link recovery: "verify this relationship may already exist" -- never
framed as a forecast of a future relationship. Score = a normalized (0-1),
documented-weight blend of:

  structural_similarity (weight 0.6) -- Jaccard overlap of the two nodes'
      neighbour sets in the relationship graph.
  cross_source_support  (weight 0.4) -- of their common neighbours, the
      fraction corroborated by more than one distinct source/relationship
      type (e.g. a shared call contact AND a shared transfer counterparty),
      not merely repeated instances of the same source.

Both components are already 0-1, so the weighted sum never needs separate
unit-mixing. Output is HIGH/MEDIUM/LOW tiers via app.config thresholds.

Validation is honest: mask a random 20% of the REAL edges, run recovery
blind to them, and report Recall@10/20/50 against the actual held-out set,
computed at run time -- this project deliberately plants NO hand-crafted
"hidden edge" for this test (that would validate against data made to be
found, not against a genuine masked-edge task).
"""
import random

from app.config import (
    LINK_RECOVERY_MASK_FRACTION, LINK_RECOVERY_WEIGHT_STRUCTURAL, LINK_RECOVERY_WEIGHT_CROSS_SOURCE,
    LINK_RECOVERY_HIGH_THRESHOLD, LINK_RECOVERY_MEDIUM_THRESHOLD,
)
from app.graph.builder import build_analysis_subgraph


def _tier(score: float) -> str:
    if score >= LINK_RECOVERY_HIGH_THRESHOLD:
        return "HIGH"
    if score >= LINK_RECOVERY_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _structural_similarity(g, u, v) -> float:
    nu, nv = set(g.neighbors(u)), set(g.neighbors(v))
    union = nu | nv
    if not union:
        return 0.0
    return len(nu & nv) / len(union)


def _cross_source_support(g, u, v) -> float:
    nu, nv = set(g.neighbors(u)), set(g.neighbors(v))
    common = nu & nv
    if not common:
        return 0.0
    corroborated = 0
    for w in common:
        types_u = g[u][w].get("relationship_types", set())
        types_v = g[v][w].get("relationship_types", set())
        if len(types_u | types_v) >= 2:
            corroborated += 1
    return corroborated / len(common)


def score_candidate_pairs(g, min_common_neighbors: int = 1, top_k: int = None):
    """Score every non-adjacent pair sharing at least one common neighbour."""
    scored = []
    nodes = list(g.nodes)
    seen = set()
    for u in nodes:
        for w in g.neighbors(u):
            for v in g.neighbors(w):
                if v == u or g.has_edge(u, v):
                    continue
                pair = tuple(sorted((u, v)))
                if pair in seen:
                    continue
                seen.add(pair)
                nu, nv = set(g.neighbors(u)), set(g.neighbors(v))
                if len(nu & nv) < min_common_neighbors:
                    continue
                structural = _structural_similarity(g, u, v)
                cross_source = _cross_source_support(g, u, v)
                combined = (LINK_RECOVERY_WEIGHT_STRUCTURAL * structural +
                            LINK_RECOVERY_WEIGHT_CROSS_SOURCE * cross_source)
                scored.append({
                    "pair": pair, "structural_similarity": round(structural, 3),
                    "cross_source_support": round(cross_source, 3),
                    "score": round(combined, 3), "tier": _tier(combined),
                    "common_neighbors": sorted(nu & nv),
                })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k] if top_k else scored


def run_recommendations(conn, top_k: int = 50):
    g = build_analysis_subgraph(conn)
    return score_candidate_pairs(g, top_k=top_k)


def evaluate_recall_at_k(conn, seed: int = 42, ks=(10, 20, 50)):
    g_full = build_analysis_subgraph(conn)
    all_edges = list(g_full.edges())
    rng = random.Random(seed)
    n_mask = max(1, int(len(all_edges) * LINK_RECOVERY_MASK_FRACTION))
    held_out = set(tuple(sorted(e)) for e in rng.sample(all_edges, n_mask))

    g_masked = g_full.copy()
    g_masked.remove_edges_from(held_out)
    # drop isolated nodes created purely by masking, to keep neighbor-based
    # scoring meaningful (an isolated node has no structural signal at all)
    isolates = [n for n in g_masked.nodes if g_masked.degree(n) == 0]
    g_masked.remove_nodes_from(isolates)

    max_k = max(ks)
    scored = score_candidate_pairs(g_masked, top_k=None)
    ranked_pairs = [tuple(r["pair"]) for r in scored]

    results = {}
    for k in ks:
        top_pairs = set(ranked_pairs[:k])
        hits = len(top_pairs & held_out)
        results[f"recall_at_{k}"] = round(hits / len(held_out), 4) if held_out else None

    return {
        "held_out_edge_count": len(held_out),
        "total_candidate_pairs_scored": len(scored),
        **results,
    }
