"""
Observer agent — silent JSON extraction from every debate turn.

The Observer never speaks in the debate. It receives each turn and extracts
structured metrics: sentiment, behavioral signals, claims, position summaries.

Runs with temperature=0.0 and JSON mode. See PRD §4.5.
"""

import json
import logging
from typing import Optional

from .llm_client import get_completion_json

logger = logging.getLogger(__name__)

MAX_MEMORY_CONTENT_LENGTH = 200  # CR-010: max chars per memory candidate content
MAX_MEMORY_CANDIDATES_PER_TURN = 3  # CR-010: max memories extracted per turn


OBSERVER_SYSTEM_PROMPT = """You are the Observer agent in a stakeholder wargame simulation.

## YOUR ROLE
You are a silent analyst. You NEVER speak in the debate. Your job is to extract
structured data from each stakeholder turn.

## OUTPUT FORMAT
You MUST respond with a single JSON object containing these exact fields:

{
  "position_summary": "1-2 sentence summary of this speaker's current position",
  "sentiment": {
    "overall": <float -1.0 to +1.0>,
    "anxiety": <float 0.0 to 1.0>,
    "trust": <float 0.0 to 1.0>,
    "aggression": <float 0.0 to 1.0>,
    "compliance": <float 0.0 to 1.0>
  },
  "behavioral_signals": {
    "concession_offered": <boolean>,
    "agreement_with": [<list of stakeholder names they agreed with>],
    "disagreement_with": [<list of stakeholder names they disagreed with>],
    "challenge_intensity": <int 1-5>,
    "position_stability": <float 0.0 to 1.0, where 1.0 = hasn't moved from baseline>,
    "escalation": <boolean>
  },
  "claims": [<list of specific factual/logical claims made>],
  "fears_triggered": [<list of fear keywords that were activated>],
  "needs_referenced": [<list of need keywords that were mentioned>],
  "agenda_votes": {
    "<item_key>": {"stance": "agree|oppose|neutral|abstain", "confidence": <float 0.0-1.0>}
  },
  "memory_candidates": [
    {
        "type": "<concession|alliance|escalation|proposal|agreement|disagreement|fear_triggered|belief_update>",
        "content": "<1 sentence describing the memorable event, max 30 words>",
        "salience": <0.0-1.0 importance score>,
        "related_agents": ["<slug of other agents involved, if any>"]
    }
  ]
}

## RULES
- Be precise. Use the exact field names above.
- sentiment.overall: negative = opposing, positive = supportive of the proposal
- position_stability: compare to the speaker's known baseline position
- claims: extract concrete arguments, not vague statements. Max 4 claims, each under 15 words.
- Only include fears/needs that are ACTUALLY referenced in the text. Max 3 items each.
- agenda_votes: only populate if agenda items are provided; otherwise use an empty object {}
- memory_candidates: Extract 0-3 memorable events from this turn. Only include genuinely significant moments: concessions, new alliances, escalations, concrete proposals, fear triggers. Do NOT create memories for routine statements or repetition. If nothing memorable happened, return an empty array [].
- IMPORTANT: Be concise. position_summary must be 1 sentence only (max 25 words). Output ONLY the JSON object, no explanation.
"""


async def extract_turn_data(
    base_url: str,
    api_key: str,
    model: str,
    speaker_name: str,
    speaker_slug: str,
    turn_content: str,
    round_num: int,
    turn_num: int,
    speaker_profile: Optional[dict] = None,
    agenda_items: Optional[list] = None,
) -> dict:
    """
    Run the Observer agent on a single turn to extract structured metrics.

    Returns a dict matching the Observer JSON schema, or a fallback on failure.
    """
    user_content = f"## Turn {turn_num}, Round {round_num}\n"
    user_content += f"**Speaker:** {speaker_name}\n\n"

    if speaker_profile:
        user_content += f"**Known baseline:** {speaker_profile.get('signal_cle', 'Unknown')}\n"
        fears = speaker_profile.get("fears", "[]")
        if isinstance(fears, str):
            fears = json.loads(fears)
        needs = speaker_profile.get("needs", "[]")
        if isinstance(needs, str):
            needs = json.loads(needs)
        user_content += f"**Known fears:** {', '.join(fears)}\n"
        user_content += f"**Known needs:** {', '.join(needs)}\n\n"

    user_content += f"## Statement:\n{turn_content}"

    if agenda_items:
        agenda_json = json.dumps(
            [{"key": a["key"], "label": a["label"]} for a in agenda_items]
        )
        user_content += (
            f"\n\n## Agenda Items\n{agenda_json}\n\n"
            "For EACH agenda item, infer the speaker's current stance based on their statement."
        )

    messages = [
        {"role": "system", "content": OBSERVER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        data = await get_completion_json(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=2000,  # #104: increased from 1200 to avoid truncating memory_candidates
            agent_name=f"observer-{speaker_slug}",
        )

        # Validate required keys exist
        data.setdefault("position_summary", "")
        data.setdefault("sentiment", {"overall": 0.0, "anxiety": 0.0, "trust": 0.0, "aggression": 0.0, "compliance": 0.0})
        data.setdefault("behavioral_signals", {})
        data.setdefault("claims", [])
        data.setdefault("fears_triggered", [])
        data.setdefault("needs_referenced", [])

        # Validate and clamp sentiment values to expected ranges (P2-2)
        sentiment = data.get("sentiment", {})
        if isinstance(sentiment, dict):
            for key in ("overall", "anxiety", "trust", "aggression", "compliance"):
                if key in sentiment:
                    try:
                        val = float(sentiment[key])
                        if key == "overall":
                            sentiment[key] = max(-1.0, min(1.0, val))
                        else:
                            sentiment[key] = max(0.0, min(1.0, val))
                    except (TypeError, ValueError):
                        logger.warning(
                            "Observer: invalid sentiment.%s value %r for %s turn %d — defaulting to 0.0",
                            key, sentiment[key], speaker_name, turn_num,
                        )
                        sentiment[key] = 0.0
            data["sentiment"] = sentiment

        # Validate agenda_votes stances and clamp confidence
        raw_votes = data.get("agenda_votes", {})
        if isinstance(raw_votes, dict) and raw_votes:
            clean_votes: dict = {}
            valid_stances = {"agree", "oppose", "neutral", "abstain"}
            for key, vote in raw_votes.items():
                if isinstance(vote, dict):
                    stance = vote.get("stance", "neutral")
                    if stance not in valid_stances:
                        stance = "neutral"
                    try:
                        conf = max(0.0, min(1.0, float(vote.get("confidence", 0.5))))
                    except (TypeError, ValueError):
                        conf = 0.5
                    clean_votes[key] = {"stance": stance, "confidence": conf}
            data["agenda_votes"] = clean_votes
        else:
            data["agenda_votes"] = {}

        # Validate memory_candidates (CR-010)
        candidates = data.get("memory_candidates", [])
        valid_memory_types = {"concession", "alliance", "escalation", "proposal",
                              "agreement", "disagreement", "fear_triggered", "belief_update"}
        validated = []
        for c in candidates[:MAX_MEMORY_CANDIDATES_PER_TURN]:
            if isinstance(c, dict) and c.get("type") in valid_memory_types and c.get("content"):
                validated.append({
                    "type": c["type"],
                    "content": str(c["content"])[:MAX_MEMORY_CONTENT_LENGTH],
                    "salience": max(0.0, min(1.0, float(c.get("salience", 0.5)))),
                    "related_agents": [str(a) for a in c.get("related_agents", [])][:5],
                })
        data["memory_candidates"] = validated

        # Inject metadata
        data["turn"] = turn_num
        data["round"] = round_num
        data["speaker"] = speaker_slug
        data["speaker_name"] = speaker_name

        return data

    except Exception as e:
        logger.error("Observer extraction failed for turn %d (%s): %s", turn_num, speaker_name, e, exc_info=True)
        return _fallback(speaker_name, speaker_slug, turn_num, round_num)


def _fallback(speaker_name: str, speaker_slug: str, turn_num: int, round_num: int) -> dict:
    """Return a neutral fallback when Observer extraction fails."""
    return {
        "turn": turn_num,
        "round": round_num,
        "speaker": speaker_slug,
        "speaker_name": speaker_name,
        "position_summary": "",
        "sentiment": {"overall": 0.0, "anxiety": 0.0, "trust": 0.0, "aggression": 0.0, "compliance": 0.0},
        "behavioral_signals": {
            "concession_offered": False,
            "agreement_with": [],
            "disagreement_with": [],
            "challenge_intensity": 0,
            "position_stability": 1.0,
            "escalation": False,
        },
        "claims": [],
        "fears_triggered": [],
        "needs_referenced": [],
        "agenda_votes": {},
        "memory_candidates": [],
    }
