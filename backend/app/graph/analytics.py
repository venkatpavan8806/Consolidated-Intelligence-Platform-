"""
Network analytics -- degree, betweenness, PageRank, Louvain community
detection, and cross-community broker scoring. Every function here operates
on the graph returned by build_analysis_subgraph(), which has already had
officials and utility nodes removed -- so exclusion is structural and
consistent across all five, by construction (see app/graph/exclusion.py and
gotcha #4).
"""
import networkx as nx
from networkx.algorithms.community import louvain_communities

from app.graph.builder import build_analysis_subgraph


def compute_degree(g: nx.Graph) -> dict:
    return {n: g.degree(n, weight="weight") for n in g.nodes}


def compute_betweenness(g: nx.Graph) -> dict:
    if g.number_of_nodes() < 3:
        return {n: 0.0 for n in g.nodes}
    return nx.betweenness_centrality(g, weight=None, normalized=True)


def compute_pagerank(g: nx.Graph) -> dict:
    if g.number_of_nodes() == 0:
        return {}
    return nx.pagerank(g, weight="weight")


def compute_communities(g: nx.Graph, seed: int = 42) -> dict:
    """Returns {entity_id: community_index}."""
    if g.number_of_edges() == 0:
        return {n: i for i, n in enumerate(g.nodes)}
    communities = louvain_communities(g, weight="weight", seed=seed)
    membership = {}
    for idx, community in enumerate(communities):
        for node in community:
            membership[node] = idx
    return membership


def compute_broker_scores(g: nx.Graph, membership: dict) -> dict:
    """Count of DISTINCT neighbouring communities a node touches, excluding
    its own community. A high score means the node's contacts are spread
    across otherwise-separate clusters -- the "few calls, touches both
    sides" signature of a broker/intermediary, as opposed to a busy node
    that is merely central within a single dense cluster."""
    scores = {}
    for node in g.nodes:
        own_community = membership.get(node)
        neighbor_communities = {membership.get(nbr) for nbr in g.neighbors(node)}
        neighbor_communities.discard(own_community)
        scores[node] = len(neighbor_communities)
    return scores


def run_full_analytics(conn) -> dict:
    g = build_analysis_subgraph(conn)
    membership = compute_communities(g)
    degree = compute_degree(g)
    betweenness = compute_betweenness(g)
    pagerank = compute_pagerank(g)
    broker = compute_broker_scores(g, membership)
    return {
        "graph": g,
        "membership": membership,
        "degree": degree,
        "betweenness": betweenness,
        "pagerank": pagerank,
        "broker": broker,
    }


def top_n(scores: dict, n: int = 10):
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]
