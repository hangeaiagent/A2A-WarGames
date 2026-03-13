"""
Speaker selection algorithm.

P(speak_next) ∝ influence × topic_relevance × turn_equity × diversity_bonus

Anti-groupthink override: if consensus > 0.75, force the most dissenting agent.
See PRD §4.3.
"""

import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SpeakerSelector:
    """Manages speaker ordering with support for @mention bumping."""

    def __init__(self, stakeholders: list[dict]):
        self.stakeholders = stakeholders
        self._mention_queue: list[str] = []
        self._bumped_this_round: dict = {}
        # Runtime mute set — slugs here are excluded from selection (#115)
        self.muted_agents: set = set()

    def select_speakers(
        self,
        num_speakers: int = 3,
        turns_spoken: Optional[dict[str, int]] = None,
        last_speaker_attitude: Optional[str] = None,
        consensus_score: Optional[float] = None,
        position_distances: Optional[dict[str, float]] = None,
    ) -> list[dict]:
        """
        Select the next speakers for a debate turn.

        If @mention bumps are queued, they are consumed first before
        falling back to weighted selection.  Muted agents are excluded.
        """
        if not self.stakeholders:
            return []

        turns_spoken = turns_spoken or {}
        result = []

        # Consume mention queue first (skip muted agents)
        while self._mention_queue and len(result) < num_speakers:
            slug = self._mention_queue.pop(0)
            if slug in self.muted_agents:
                logger.debug("Skipping muted agent %s from mention queue", slug)
                continue
            match = [s for s in self.stakeholders if s["slug"] == slug]
            if match and match[0] not in result:
                result.append(match[0])

        remaining_needed = num_speakers - len(result)
        if remaining_needed <= 0:
            return result

        # Filter out already-selected and muted agents from weighted pool
        selected_slugs = {s["slug"] for s in result}
        pool = [
            s for s in self.stakeholders
            if s["slug"] not in selected_slugs and s["slug"] not in self.muted_agents
        ]

        # Anti-groupthink override (skip muted agents)
        if consensus_score is not None and consensus_score > 0.75 and position_distances:
            most_distant = max(
                (
                    s for s in position_distances
                    if s not in selected_slugs and s not in self.muted_agents
                ),
                key=position_distances.get,
                default=None,
            )
            if most_distant:
                forced = [s for s in pool if s["slug"] == most_distant]
                if forced:
                    logger.info("Anti-groupthink: forcing %s (distance=%.2f)", most_distant, position_distances[most_distant])
                    result.append(forced[0])
                    pool = [s for s in pool if s["slug"] != most_distant]
                    remaining_needed -= 1

        if remaining_needed > 0:
            result.extend(_weighted_select(pool, remaining_needed, turns_spoken, last_speaker_attitude))

        return result

    def prepend_mentions(self, slugs: list[str], current_round: int):
        """Bump mentioned agents to front of next-speaker queue.

        Anti-loop guard: each agent can be bumped at most once per round.
        If the same agent is mentioned again in the same round, ignore.
        """
        if self._bumped_this_round.get('round') != current_round:
            self._bumped_this_round = {'round': current_round, 'slugs': set()}

        for slug in reversed(slugs):  # reversed so first mention ends up first
            if slug not in self._bumped_this_round['slugs']:
                self._bump_to_front(slug)
                self._bumped_this_round['slugs'].add(slug)

    def _bump_to_front(self, slug: str):
        """Insert agent at position 0 of the mention queue without duplicating."""
        self._mention_queue = [s for s in self._mention_queue if s != slug]
        self._mention_queue.insert(0, slug)


# Legacy function-based API (used by existing callers)
def select_speakers(
    stakeholders: list[dict],
    num_speakers: int = 3,
    turns_spoken: Optional[dict[str, int]] = None,
    last_speaker_attitude: Optional[str] = None,
    consensus_score: Optional[float] = None,
    position_distances: Optional[dict[str, float]] = None,
) -> list[dict]:
    """
    Select the next speakers for a debate turn.

    Args:
        stakeholders: list of stakeholder dicts (must have slug, influence, attitude)
        num_speakers: how many to select
        turns_spoken: {slug: count} of turns spoken this round
        last_speaker_attitude: attitude of the last speaker (for diversity bonus)
        consensus_score: current consensus (0-1), triggers anti-groupthink if > 0.75
        position_distances: {slug: distance_from_centroid} for contrarian forcing

    Returns:
        List of selected stakeholder dicts, ordered by priority.
    """
    if not stakeholders:
        return []

    turns_spoken = turns_spoken or {}

    # Anti-groupthink override
    if consensus_score is not None and consensus_score > 0.75 and position_distances:
        # Force the most dissenting agent
        most_distant = max(position_distances, key=position_distances.get)
        forced = [s for s in stakeholders if s["slug"] == most_distant]
        if forced:
            logger.info("Anti-groupthink: forcing %s (distance=%.2f)", most_distant, position_distances[most_distant])
            remaining = [s for s in stakeholders if s["slug"] != most_distant]
            others = _weighted_select(remaining, num_speakers - 1, turns_spoken, last_speaker_attitude)
            return forced + others

    return _weighted_select(stakeholders, num_speakers, turns_spoken, last_speaker_attitude)


def _weighted_select(
    stakeholders: list[dict],
    num_speakers: int,
    turns_spoken: dict[str, int],
    last_speaker_attitude: Optional[str],
) -> list[dict]:
    """Weighted random selection based on the P(speak) formula."""
    if not stakeholders:
        return []

    num_speakers = min(num_speakers, len(stakeholders))

    scores = []
    for s in stakeholders:
        influence = s.get("influence", 0.5)
        # Turn equity: boost agents who haven't spoken much
        spoken = turns_spoken.get(s["slug"], 0)
        turn_equity = 1.0 / (1.0 + spoken)
        # Diversity bonus: boost agents with different attitude from last speaker
        diversity = 1.5 if (last_speaker_attitude and s.get("attitude") != last_speaker_attitude) else 1.0

        score = influence * turn_equity * diversity
        scores.append((s, score))

    # Weighted random sample
    selected = []
    remaining = list(scores)

    for _ in range(num_speakers):
        if not remaining:
            break

        total = sum(score for _, score in remaining)
        if total <= 0:
            # Fallback: uniform random
            pick = random.choice(remaining)
        else:
            r = random.random() * total
            cumulative = 0
            pick = remaining[0]
            for item in remaining:
                cumulative += item[1]
                if cumulative >= r:
                    pick = item
                    break

        selected.append(pick[0])
        remaining = [(s, sc) for s, sc in remaining if s["slug"] != pick[0]["slug"]]

    return selected
