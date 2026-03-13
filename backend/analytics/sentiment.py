"""
Sentiment analysis — dual approach.

1. VADER (fast, lexicon-based) for real-time sentiment scoring
2. Observer agent extraction (deep, LLM-based) for nuanced axes

VADER provides a cross-check on the Observer's sentiment extraction.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_vader: Optional[object] = None


def _get_vader():
    """Lazy-load VADER to avoid import cost at startup."""
    global _vader
    if _vader is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
    return _vader


def analyze_sentiment(text: str) -> dict:
    """
    Analyze sentiment using VADER.

    Returns: {compound, positive, negative, neutral}
    compound is -1.0 to +1.0
    """
    analyzer = _get_vader()
    scores = analyzer.polarity_scores(text)

    return {
        "compound": scores["compound"],
        "positive": scores["pos"],
        "negative": scores["neg"],
        "neutral": scores["neu"],
    }


def cross_check_sentiment(vader_score: float, observer_score: float, threshold: float = 0.4) -> dict:
    """
    Cross-check VADER compound vs Observer overall sentiment.

    If they disagree by more than threshold, flag for review.
    """
    delta = abs(vader_score - observer_score)
    agreement = delta < threshold

    return {
        "vader": vader_score,
        "observer": observer_score,
        "delta": delta,
        "agreement": agreement,
        "recommended": observer_score if agreement else (vader_score + observer_score) / 2,
    }


def aggregate_sentiment(sentiments: list[dict]) -> dict:
    """
    Aggregate sentiment across multiple turns for a round summary.

    Args:
        sentiments: list of Observer sentiment dicts {overall, anxiety, trust, aggression, compliance}

    Returns:
        Aggregated dict with means for each axis.
    """
    if not sentiments:
        return {"overall": 0.0, "anxiety": 0.0, "trust": 0.0, "aggression": 0.0, "compliance": 0.0}

    axes = ["overall", "anxiety", "trust", "aggression", "compliance"]
    result = {}
    for axis in axes:
        values = [s.get(axis, 0.0) for s in sentiments if isinstance(s.get(axis), (int, float))]
        result[axis] = sum(values) / len(values) if values else 0.0

    return result
