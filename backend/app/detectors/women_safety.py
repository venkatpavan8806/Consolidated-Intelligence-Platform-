"""
Women-Safety / trafficking-network detectors.

This is NOT a separate detection model -- it re-labels and filters the SAME
community-detection and broker-scoring machinery used for general financial
"kingpin" analysis (see app/graph/analytics.py), applied to the person/phone
network. The same mechanism that surfaces a financial intermediary surfaces
a trafficking one.

Known limitation (documented, engineered around rather than hidden): Louvain
community detection does not reliably split a single small, sparse
recruiter -> transporter -> receiver chain into separate communities absent
a second, competing dense structure -- it tends to merge the whole
weakly-connected chain into one community. So TWO independent methods are
run and merged, each hit tagged with which method found it:

  1. COMMUNITY_BRIDGE       -- a node whose neighbours span >=2 distinct
                                Louvain communities.
  2. STRUCTURAL_BRIDGE_PATH -- (primary, more reliable for small chains) a
                                low-degree, low-volume node with one foot in
                                a known recruiter's contact set and one foot
                                touching a comparatively high-degree node on
                                the other side.

The recruiter heuristic (fan-out to >=3 low-degree contacts in one
community) is intentionally generic: it will also flag unrelated hub
structures such as a burner-rotation phone. That is expected, not a bug --
every candidate here carries requires_human_verification=True. It is not
narrowed further, to avoid overfitting to this synthetic case at the cost of
being a general detector.
"""
from collections import defaultdict

from app.config import (
    BRIDGE_LOW_DEGREE_MAX, BRIDGE_LOW_VOLUME_MAX, BRIDGE_HIGH_DEGREE_MIN,
    RECRUITER_MIN_FANOUT, RECRUITER_FANOUT_MAX_DEGREE, REPEAT_LOCATION_MIN_SOURCES,
)


def detect_recruiter_candidates(g, membership: dict):
    """Fan-out to >=3 low-degree contacts within the same community.
    Deliberately generic -- will also match e.g. a burner-rotation hub."""
    candidates = {}
    for node in g.nodes:
        if g.nodes[node].get("entity_type") != "PHONE":
            continue
        own_community = membership.get(node)
        low_degree_contacts = [
            nbr for nbr in g.neighbors(node)
            if g.nodes[nbr].get("entity_type") == "PHONE"
            and g.degree(nbr) <= RECRUITER_FANOUT_MAX_DEGREE
            and membership.get(nbr) == own_community
        ]
        if len(low_degree_contacts) >= RECRUITER_MIN_FANOUT:
            candidates[node] = {
                "low_degree_contacts": low_degree_contacts,
                "fanout_count": len(low_degree_contacts),
                "community": own_community,
            }
    return candidates


def detect_community_bridge(g, membership: dict):
    """Method 1: a node whose direct neighbours span >=2 distinct Louvain
    communities."""
    hits = {}
    for node in g.nodes:
        own_community = membership.get(node)
        neighbor_communities = {membership.get(n) for n in g.neighbors(node)}
        neighbor_communities.discard(own_community)
        if len(neighbor_communities) >= 2:
            hits[node] = {
                "method": "COMMUNITY_BRIDGE",
                "neighbor_communities": sorted(c for c in neighbor_communities if c is not None),
                "own_community": own_community,
            }
    return hits


def detect_structural_bridge_path(g, membership: dict, recruiter_candidates: dict):
    """Method 2 (primary, more reliable for small chains): a low-degree,
    low-call-volume node with one neighbour in a known recruiter's contact
    set AND another neighbour whose own degree is comparatively high --
    one foot in the recruiter's contacts, one foot touching a denser
    cluster on the other side.

    Evaluated per-recruiter (not against a global union of every recruiter
    candidate's contacts): the generic recruiter heuristic can itself flag
    an unrelated dense hub (e.g. a receiver-side cluster looks like a
    "recruiter" fanning out to low-degree contacts too). Pooling all
    candidates' contact sets together would let that hub's members silently
    satisfy the "recruiter side" for each other, masking the real bridge.
    Keeping each recruiter's contact set separate avoids that cross-talk."""
    hits = {}
    for node in g.nodes:
        if g.nodes[node].get("entity_type") != "PHONE":
            continue
        degree = g.degree(node)
        call_volume = sum(data.get("call_count", 1) for _, _, data in g.edges(node, data=True))
        if degree > BRIDGE_LOW_DEGREE_MAX or call_volume > BRIDGE_LOW_VOLUME_MAX:
            continue
        neighbors = set(g.neighbors(node))

        matches = []
        for recruiter, info in recruiter_candidates.items():
            recruiter_side_set = set(info["low_degree_contacts"]) | {recruiter}
            recruiter_side = neighbors & recruiter_side_set
            other_side = [
                n for n in neighbors
                if n not in recruiter_side_set and g.degree(n) >= BRIDGE_HIGH_DEGREE_MIN
            ]
            if recruiter_side and other_side:
                matches.append({
                    "recruiter": recruiter,
                    "recruiter_side_neighbor": sorted(recruiter_side)[0],
                    "high_degree_side_neighbor": other_side[0],
                })
        if matches:
            hits[node] = {
                "method": "STRUCTURAL_BRIDGE_PATH",
                "matches": matches,
                "degree": degree,
                "call_volume": call_volume,
            }
    return hits


def detect_transporter_candidates(g, membership: dict):
    """Runs both methods and merges results, skipping duplicates, tagging
    provenance on each hit (a node found by both carries both method tags)."""
    recruiters = detect_recruiter_candidates(g, membership)
    community_hits = detect_community_bridge(g, membership)
    structural_hits = detect_structural_bridge_path(g, membership, recruiters)

    merged = {}
    for node, info in community_hits.items():
        merged.setdefault(node, {"methods": [], "detail": {}})
        merged[node]["methods"].append("COMMUNITY_BRIDGE")
        merged[node]["detail"]["COMMUNITY_BRIDGE"] = info
    for node, info in structural_hits.items():
        merged.setdefault(node, {"methods": [], "detail": {}})
        merged[node]["methods"].append("STRUCTURAL_BRIDGE_PATH")
        merged[node]["detail"]["STRUCTURAL_BRIDGE_PATH"] = info

    return {"recruiters": recruiters, "transporters": merged}


def detect_repeat_locations(conn, min_sources: int = REPEAT_LOCATION_MIN_SOURCES):
    """Same real-world LOCATION named across >=3 independently-sourced FIR
    records. Police-station names are a distinct ORGANIZATION type in the
    gazetteer/extraction pipeline specifically so their expected recurrence
    (one station handling many unrelated FIRs) never enters this signal."""
    rows = conn.execute("SELECT entity_id, canonical_value FROM entities WHERE entity_type='LOCATION'").fetchall()
    results = []
    for row in rows:
        mention_rows = conn.execute(
            """SELECT DISTINCT em.source_record_id, em.mention_id FROM entity_mentions em
               JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
               WHERE mem.entity_id = ?""",
            (row["entity_id"],),
        ).fetchall()
        source_records = {r["source_record_id"] for r in mention_rows}
        if len(source_records) >= min_sources:
            other_entities = set()
            for rec_id in source_records:
                for r in conn.execute(
                    """SELECT DISTINCT mem.entity_id FROM entity_mentions em
                       JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
                       WHERE em.source_record_id = ? AND mem.entity_id != ?""",
                    (rec_id, row["entity_id"]),
                ).fetchall():
                    other_entities.add(r["entity_id"])
            results.append({
                "entity_id": row["entity_id"],
                "location": row["canonical_value"],
                "source_records": sorted(source_records),
                "independent_source_count": len(source_records),
                "linked_entities": sorted(other_entities),
            })
    return results
