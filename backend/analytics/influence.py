"""
Influence analysis — NetworkX centrality on the agreement/disagreement graph.

Builds a directed graph from Observer behavioral signals:
  - agreement_with → positive edge
  - disagreement_with → negative edge

Computes:
  - Eigenvector centrality (who has influence)
  - Betweenness centrality (who bridges groups)
"""

import logging
import networkx as nx

logger = logging.getLogger(__name__)


def build_influence_graph(
    observer_data: list[dict],
    stakeholders: list[dict],
) -> nx.DiGraph:
    """
    Build a directed influence graph from Observer extraction data.

    Nodes = stakeholders (with base influence as attribute).
    Edges = agreement (+weight) and disagreement (-weight) interactions.
    """
    G = nx.DiGraph()

    # Add all stakeholders as nodes
    for s in stakeholders:
        G.add_node(s["slug"], name=s["name"], base_influence=s.get("influence", 0.5))

    # Add edges from observer data
    for obs in observer_data:
        speaker = obs.get("speaker")
        if not speaker:
            continue

        signals = obs.get("behavioral_signals", {})

        for target in signals.get("agreement_with", []):
            target_slug = _name_to_slug(target, stakeholders)
            if target_slug and target_slug != speaker:
                if G.has_edge(speaker, target_slug):
                    G[speaker][target_slug]["weight"] += 0.5
                else:
                    G.add_edge(speaker, target_slug, weight=0.5, type="agreement")

        for target in signals.get("disagreement_with", []):
            target_slug = _name_to_slug(target, stakeholders)
            if target_slug and target_slug != speaker:
                if G.has_edge(speaker, target_slug):
                    G[speaker][target_slug]["weight"] += 0.3
                else:
                    G.add_edge(speaker, target_slug, weight=0.3, type="disagreement")

    return G


def compute_influence(
    observer_data: list[dict],
    stakeholders: list[dict],
) -> list[dict]:
    """
    Compute influence rankings from debate interactions.

    Returns sorted list: [{agent, name, eigenvector, betweenness, combined}]
    """
    G = build_influence_graph(observer_data, stakeholders)

    if G.number_of_edges() == 0:
        # No interactions yet — return base influence
        return [
            {
                "agent": s["slug"],
                "name": s["name"],
                "eigenvector": s.get("influence", 0.5),
                "betweenness": 0.0,
                "combined": s.get("influence", 0.5),
            }
            for s in stakeholders
        ]

    # Eigenvector centrality
    try:
        eigen = nx.eigenvector_centrality(G, max_iter=500, weight="weight")
    except nx.NetworkXError:
        eigen = {s["slug"]: s.get("influence", 0.5) for s in stakeholders}

    # Betweenness centrality
    between = nx.betweenness_centrality(G, weight="weight")

    results = []
    for s in stakeholders:
        slug = s["slug"]
        e = eigen.get(slug, 0.0)
        b = between.get(slug, 0.0)
        # Combined: weighted blend of base influence + graph centrality
        base = s.get("influence", 0.5)
        combined = 0.4 * base + 0.4 * e + 0.2 * b

        results.append({
            "agent": slug,
            "name": s["name"],
            "eigenvector": round(e, 3),
            "betweenness": round(b, 3),
            "combined": round(combined, 3),
        })

    results.sort(key=lambda x: x["combined"], reverse=True)
    return results


def get_bridge_agents(
    observer_data: list[dict],
    stakeholders: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """Return top N agents by betweenness centrality (bridge builders)."""
    influence = compute_influence(observer_data, stakeholders)
    sorted_by_between = sorted(influence, key=lambda x: x["betweenness"], reverse=True)
    return sorted_by_between[:top_n]


def _name_to_slug(name: str, stakeholders: list[dict]) -> str | None:
    """Resolve a stakeholder name to its slug (case-insensitive)."""
    name_lower = name.lower().strip()
    for s in stakeholders:
        if s["name"].lower() == name_lower or s["slug"].lower() == name_lower:
            return s["slug"]
    return None
