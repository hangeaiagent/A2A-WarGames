"""
Coalition detection — HDBSCAN clustering on position embeddings.

Detects organic coalition formation without predefined k.
Handles noise (agents not in any cluster) gracefully.
Falls back to pairwise comparison when N < 5.
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


def detect_coalitions(
    embeddings: dict[str, list[float]],
    min_cluster_size: int = 2,
) -> dict:
    """
    Cluster agents by position similarity.

    Args:
        embeddings: {slug: [384 floats]}
        min_cluster_size: minimum agents to form a coalition

    Returns:
        {
            "clusters": [
                {"id": 0, "members": ["julien", "marc"], "intra_similarity": 0.82},
                ...
            ],
            "noise": ["sarah"],  # agents not in any cluster
            "num_clusters": 2,
        }
    """
    slugs = list(embeddings.keys())

    if len(slugs) < 2:
        return {"clusters": [], "noise": slugs, "num_clusters": 0}

    vectors = np.array([embeddings[s] for s in slugs])

    # Fallback for small N: pairwise grouping
    if len(slugs) < 5:
        return _pairwise_fallback(slugs, vectors)

    try:
        import hdbscan
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(vectors)
    except Exception as e:
        logger.warning("HDBSCAN failed, using pairwise fallback: %s", e)
        return _pairwise_fallback(slugs, vectors)

    # Group results
    clusters = {}
    noise = []

    for slug, label in zip(slugs, labels):
        if label == -1:
            noise.append(slug)
        else:
            clusters.setdefault(label, []).append(slug)

    result_clusters = []
    for cluster_id, members in sorted(clusters.items()):
        member_vecs = np.array([embeddings[s] for s in members])
        if len(member_vecs) >= 2:
            sim_matrix = member_vecs @ member_vecs.T
            n = len(member_vecs)
            upper = sim_matrix[np.triu_indices(n, k=1)]
            intra_sim = float(np.mean(upper))
        else:
            intra_sim = 1.0

        result_clusters.append({
            "id": int(cluster_id),
            "members": members,
            "intra_similarity": round(intra_sim, 3),
        })

    return {
        "clusters": result_clusters,
        "noise": noise,
        "num_clusters": len(result_clusters),
    }


def compute_polarization(
    embeddings: dict[str, list[float]],
    coalitions: dict,
) -> float:
    """
    Polarization index: 1 - inter-cluster similarity.
    Only meaningful when >= 2 clusters exist.
    Returns 0.0-1.0 where 1.0 = maximum polarization.
    """
    clusters = coalitions.get("clusters", [])
    if len(clusters) < 2:
        return 0.0

    # Compute centroids per cluster
    centroids = []
    for c in clusters:
        vecs = np.array([embeddings[s] for s in c["members"]])
        centroids.append(np.mean(vecs, axis=0))

    # Mean inter-cluster cosine similarity
    sims = []
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            norm_i = centroids[i] / (np.linalg.norm(centroids[i]) + 1e-8)
            norm_j = centroids[j] / (np.linalg.norm(centroids[j]) + 1e-8)
            sim = float(np.dot(norm_i, norm_j))
            sims.append(sim)

    inter_sim = np.mean(sims) if sims else 0.0
    return float(max(0.0, 1.0 - inter_sim))


def compute_stability(
    current_coalitions: dict,
    prior_coalitions: Optional[dict],
) -> float:
    """
    Coalition stability: % of agents who stayed in the same cluster.
    Returns 0-100%.
    """
    if not prior_coalitions or not prior_coalitions.get("clusters"):
        return 100.0  # first round, nothing to compare

    # Build slug→cluster_id maps
    current_map = {}
    for c in current_coalitions.get("clusters", []):
        for member in c["members"]:
            current_map[member] = c["id"]

    prior_map = {}
    for c in prior_coalitions.get("clusters", []):
        for member in c["members"]:
            prior_map[member] = c["id"]

    # Check how many agents are in the same group as their prior cluster-mates
    common_agents = set(current_map.keys()) & set(prior_map.keys())
    if not common_agents:
        return 100.0

    stable = 0
    for agent in common_agents:
        # Find prior cluster-mates
        prior_cluster = prior_map[agent]
        prior_mates = {a for a, c in prior_map.items() if c == prior_cluster}
        # Check if they're still together
        current_cluster = current_map.get(agent)
        current_mates = {a for a, c in current_map.items() if c == current_cluster}
        if prior_mates & current_mates == prior_mates:
            stable += 1

    return round(100.0 * stable / len(common_agents), 1)


def _pairwise_fallback(slugs: list[str], vectors: np.ndarray) -> dict:
    """Simple pairwise grouping when N < 5."""
    # Normalize
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    normed = vectors / norms

    sim_matrix = normed @ normed.T
    threshold = 0.6

    # Greedy grouping
    assigned = set()
    clusters = []
    cluster_id = 0

    for i in range(len(slugs)):
        if slugs[i] in assigned:
            continue
        group = [slugs[i]]
        assigned.add(slugs[i])
        for j in range(i + 1, len(slugs)):
            if slugs[j] not in assigned and sim_matrix[i, j] > threshold:
                group.append(slugs[j])
                assigned.add(slugs[j])
        if len(group) >= 2:
            clusters.append({"id": cluster_id, "members": group, "intra_similarity": float(np.mean([sim_matrix[slugs.index(a), slugs.index(b)] for a in group for b in group if a != b])) if len(group) > 1 else 1.0})
            cluster_id += 1

    noise = [s for s in slugs if s not in assigned]

    return {"clusters": clusters, "noise": noise, "num_clusters": len(clusters)}
