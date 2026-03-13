"""
Risk scoring — composite formula from PRD §5.3.

Risk_Score(agent) = Power × |Opposition| × (1 - ConsensusShift) × FearActivation

Levels:
  0-3: LOW (green)    — aligned or willing to move
  3-6: MEDIUM (amber) — concerns but hasn't blocked
  6-10: HIGH (red)    — actively blocking, unlikely to move
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_risk_scores(
    stakeholders: list[dict],
    observer_data: list[dict],
    round_num: int,
    baseline_positions: Optional[dict[str, list[float]]] = None,
    current_positions: Optional[dict[str, list[float]]] = None,
) -> list[dict]:
    """
    Compute risk score for each stakeholder.

    Args:
        stakeholders: stakeholder dicts
        observer_data: all observer extractions (will be filtered to current round)
        round_num: current round number
        baseline_positions: {slug: embedding} from round 1
        current_positions: {slug: embedding} from current round

    Returns:
        [{agent, name, score, level, drivers}] sorted by score descending.
    """
    import numpy as np

    # Get this round's observer data
    round_obs = [o for o in observer_data if o.get("round") == round_num]

    # Build per-agent observer lookup
    agent_obs = {}
    for o in round_obs:
        slug = o.get("speaker")
        if slug:
            agent_obs.setdefault(slug, []).append(o)

    results = []
    for s in stakeholders:
        slug = s["slug"]
        name = s["name"]

        # Power = influence × 10 (0-10)
        power = s.get("influence", 0.5) * 10

        # Opposition = abs(sentiment.overall) if negative, else 0
        obs_list = agent_obs.get(slug, [])
        if obs_list:
            sentiments = [o.get("sentiment", {}).get("overall", 0.0) for o in obs_list]
            avg_sentiment = sum(sentiments) / len(sentiments)
            opposition = abs(avg_sentiment) if avg_sentiment < 0 else 0.0
        else:
            opposition = 0.0

        # ConsensusShift = cosine_sim(baseline, current). 1.0 = hasn't moved.
        consensus_shift = 1.0
        if baseline_positions and current_positions:
            base_vec = baseline_positions.get(slug)
            curr_vec = current_positions.get(slug)
            if base_vec and curr_vec:
                base_arr = np.array(base_vec)
                curr_arr = np.array(curr_vec)
                norm_b = np.linalg.norm(base_arr)
                norm_c = np.linalg.norm(curr_arr)
                if norm_b > 0 and norm_c > 0:
                    consensus_shift = float(np.dot(base_arr, curr_arr) / (norm_b * norm_c))

        willingness_to_move = 1.0 - consensus_shift

        # FearActivation = count(fears_triggered) / count(total_fears)
        total_fears = _parse_list(s.get("fears", "[]"))
        fears_triggered = set()
        for o in obs_list:
            for f in o.get("fears_triggered", []):
                fears_triggered.add(f)

        fear_activation = len(fears_triggered) / max(len(total_fears), 1)

        # Composite risk score
        raw_score = power * opposition * (1.0 - consensus_shift + 0.1) * (fear_activation + 0.1)

        # Normalize to 0-10 range (power is already 0-10, others are 0-1ish)
        score = min(10.0, raw_score)

        # Determine level
        if score >= 6:
            level = "HIGH"
        elif score >= 3:
            level = "MEDIUM"
        else:
            level = "LOW"

        # Drivers
        drivers = []
        if opposition > 0.3:
            drivers.append("actively opposing")
        if fear_activation > 0.3:
            drivers.append(f"{len(fears_triggered)} fears triggered")
        if willingness_to_move < 0.1:
            drivers.append("position unchanged")
        if power >= 7:
            drivers.append("high power")

        results.append({
            "agent": slug,
            "name": name,
            "score": round(score, 1),
            "level": level,
            "drivers": drivers,
            "components": {
                "power": round(power, 1),
                "opposition": round(opposition, 2),
                "willingness_to_move": round(willingness_to_move, 2),
                "fear_activation": round(fear_activation, 2),
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _parse_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return []
