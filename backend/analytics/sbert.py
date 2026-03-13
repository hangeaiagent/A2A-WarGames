"""
S-BERT Harmony/Discord Meter — semantic similarity between agent positions.

Uses sentence-transformers (all-MiniLM-L6-v2) for fast embedding comparison.
Distinct from consensus.py (which operates on pre-computed embeddings stored in
AnalyticsSnapshot). This module works directly on raw message dicts, making it
useful for on-demand harmony queries during or after a session.
"""

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# Lazy-load model to avoid import-time GPU allocation
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("S-BERT model loaded (all-MiniLM-L6-v2)")
        except ImportError:
            logger.warning("sentence-transformers not installed — S-BERT disabled")
            return None
    return _model


def compute_sbert_harmony(messages: list[dict], stakeholders: list[dict]) -> Optional[dict]:
    """
    Compute pairwise semantic similarity between the latest statements of each agent.

    Args:
        messages:     List of message dicts with at least "speaker" and "content" keys.
                      Typically the full messages list for a session or a single round.
        stakeholders: List of stakeholder dicts (used for validation / future enrichment).
                      May be empty — only "speaker" slugs from messages are required.

    Returns:
        {
            "harmony_score": float (0-1, 1 = all agents saying the same thing),
            "discord_score": float (0-1, inverse of harmony),
            "pairwise": [{"a": slug, "b": slug, "similarity": float}, ...],
            "most_aligned": (slug_a, slug_b, score) | None,
            "most_opposed": (slug_a, slug_b, score) | None,
        }
        Returns None if the model is unavailable or fewer than 2 speakers are found.
    """
    model = _get_model()
    if model is None:
        return None

    # Get latest message per speaker (exclude moderator and chairman)
    latest: dict[str, str] = {}
    for m in messages:
        speaker = m.get("speaker", "")
        if speaker and speaker not in ("moderator", "chairman"):
            latest[speaker] = m.get("content", "")

    if len(latest) < 2:
        logger.debug("compute_sbert_harmony: fewer than 2 speakers — skipping")
        return None

    slugs = list(latest.keys())
    texts = [latest[s] for s in slugs]

    # Encode all statements; normalize_embeddings=True enables dot-product as cosine similarity
    embeddings = model.encode(texts, normalize_embeddings=True)

    # Pairwise cosine similarity via matrix multiply (vectors already unit-normalized)
    sim_matrix = np.dot(embeddings, embeddings.T)

    # Extract upper triangle (unique pairs only)
    pairwise: list[dict] = []
    scores: list[float] = []
    for i in range(len(slugs)):
        for j in range(i + 1, len(slugs)):
            score = float(sim_matrix[i][j])
            pairwise.append({
                "a": slugs[i],
                "b": slugs[j],
                "similarity": round(score, 3),
            })
            scores.append(score)

    avg_sim = float(np.mean(scores)) if scores else 0.0

    # Find extremes
    sorted_pairs = sorted(pairwise, key=lambda p: p["similarity"])
    most_opposed = sorted_pairs[0] if sorted_pairs else None
    most_aligned = sorted_pairs[-1] if sorted_pairs else None

    return {
        "harmony_score": round(avg_sim, 3),
        "discord_score": round(1.0 - avg_sim, 3),
        "pairwise": pairwise,
        "most_aligned": (
            most_aligned["a"],
            most_aligned["b"],
            most_aligned["similarity"],
        ) if most_aligned else None,
        "most_opposed": (
            most_opposed["a"],
            most_opposed["b"],
            most_opposed["similarity"],
        ) if most_opposed else None,
    }


def compute_sbert_harmony_by_round(
    messages: list[dict],
    stakeholders: list[dict],
    round_field: str = "round_num",
) -> dict[int, Optional[dict]]:
    """
    Compute harmony per round using the latest message per speaker within each round.

    Args:
        messages:    Full messages list. Each dict must have a round number field.
        stakeholders: Stakeholder dicts (passed through to compute_sbert_harmony).
        round_field: The key on each message dict that holds the round number.
                     Defaults to "round_num"; use "stage" for the Message ORM model.

    Returns:
        {round_number: harmony_result_or_None, ...}
    """
    # Group messages by round
    rounds: dict[int, list[dict]] = {}
    for m in messages:
        rnum = m.get(round_field) or 0
        rounds.setdefault(rnum, []).append(m)

    return {
        rnum: compute_sbert_harmony(round_messages, stakeholders)
        for rnum, round_messages in sorted(rounds.items())
    }


def embed_text(text: str) -> Optional[list[float]]:
    """Encode a single text string into a 384-dim embedding vector.

    Returns None if S-BERT model is unavailable.
    Reuses the lazy-loaded singleton model from _get_model().
    """
    model = _get_model()
    if model is None:
        return None
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Batch-encode multiple texts. Returns None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
