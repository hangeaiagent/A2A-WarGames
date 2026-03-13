"""
Consensus scoring — Sentence-BERT cosine similarity.

Embeds position summaries using all-MiniLM-L6-v2 (384-dim),
computes pairwise cosine similarity, and derives:
  - consensus_score: mean pairwise similarity (0-1)
  - consensus_velocity: delta from prior round
  - funneling_effect: StdDev of distances from centroid
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    """Lazy-load the Sentence-BERT model (~90MB first download)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded Sentence-BERT model: all-MiniLM-L6-v2")
    return _model


def embed_positions(position_summaries: dict[str, str]) -> dict[str, list[float]]:
    """
    Embed position summaries for all agents.

    Args:
        position_summaries: {slug: "position text"}

    Returns:
        {slug: [384 floats]}
    """
    if not position_summaries:
        return {}

    model = _get_model()
    slugs = list(position_summaries.keys())
    texts = [position_summaries[s] for s in slugs]

    embeddings = model.encode(texts, normalize_embeddings=True)

    return {slug: emb.tolist() for slug, emb in zip(slugs, embeddings)}


def compute_consensus(embeddings: dict[str, list[float]]) -> float:
    """
    Compute consensus score as mean pairwise cosine similarity.

    Returns 0.0-1.0 where 1.0 = perfect agreement.
    """
    if len(embeddings) < 2:
        return 0.0

    vectors = np.array(list(embeddings.values()))  # (N, 384)
    # Cosine similarity matrix (vectors are already normalized)
    sim_matrix = vectors @ vectors.T

    n = len(vectors)
    # Extract upper triangle (exclude diagonal)
    upper_indices = np.triu_indices(n, k=1)
    pairwise_sims = sim_matrix[upper_indices]

    return float(np.mean(pairwise_sims))


def compute_velocity(current_score: float, prior_score: Optional[float]) -> float:
    """Consensus velocity = delta from prior round."""
    if prior_score is None:
        return 0.0
    return current_score - prior_score


def compute_funneling(embeddings: dict[str, list[float]]) -> float:
    """
    Funneling effect: StdDev of embedding distances from centroid.
    Decreasing value = convergence.
    """
    if len(embeddings) < 2:
        return 0.0

    vectors = np.array(list(embeddings.values()))
    centroid = np.mean(vectors, axis=0)

    distances = np.linalg.norm(vectors - centroid, axis=1)
    return float(np.std(distances))


def compute_position_distances(embeddings: dict[str, list[float]]) -> dict[str, float]:
    """
    Distance of each agent from the centroid.
    Used by anti-groupthink to find the most dissenting agent.
    """
    if len(embeddings) < 2:
        return {slug: 0.0 for slug in embeddings}

    vectors = np.array(list(embeddings.values()))
    centroid = np.mean(vectors, axis=0)

    result = {}
    for slug, vec in embeddings.items():
        dist = float(np.linalg.norm(np.array(vec) - centroid))
        result[slug] = dist

    return result
