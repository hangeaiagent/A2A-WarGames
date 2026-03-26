"""
AgentPit match reporter — sends session summary to AgentPit platform
after a wargame session completes.
"""

import logging
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


async def report_match_to_agentpit(
    session,
    engine,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Report a completed wargame session to AgentPit's report-match API.

    Args:
        session: SQLAlchemy Session object (with id, question, created_at, updated_at)
        engine: A2AEngine instance (with stakeholders, turns_spoken, token counters, default_model)
        user_id: Optional AgentPit user ID for billing

    Returns:
        Response dict from AgentPit, or None on failure.
    """
    api_secret = settings.agentpit_game_api_secret
    if not api_secret:
        logger.debug("AgentPit reporting skipped: no AGENTPIT_GAME_API_SECRET configured")
        return None

    api_base = settings.agentpit_base_url
    game_type = settings.agentpit_game_type

    participants = []
    for s in engine.stakeholders:
        participants.append({
            "name": s["name"],
            "isAI": True,
            "speeches": engine.turns_spoken.get(s["slug"], 0),
        })

    duration = 0
    if session.created_at and session.updated_at:
        duration = int((session.updated_at - session.created_at).total_seconds())

    payload = {
        "api_secret": api_secret,
        "session_id": str(session.id),
        "topic": session.question or session.title or "",
        "participants": participants,
        "duration_seconds": duration,
        "input_tokens": engine._total_prompt_tokens,
        "output_tokens": engine._total_completion_tokens,
        "model_name": engine.default_model,
        "started_at": session.created_at.isoformat() if session.created_at else None,
        "finished_at": session.updated_at.isoformat() if session.updated_at else None,
    }

    if user_id:
        payload["user_id"] = user_id

    url = f"{api_base}/api/v1/games/{game_type}/report-match"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)

        if resp.status_code == 200:
            data = resp.json()
            logger.info(
                "AgentPit report OK for session %s: match_id=%s, tokens=%d, cost=%s",
                session.id,
                data.get("match_id", "?"),
                data.get("tokens_used", 0),
                data.get("cost", 0),
            )
            return data
        else:
            logger.error(
                "AgentPit report failed for session %s: HTTP %d — %s",
                session.id, resp.status_code, resp.text[:500],
            )
            return None
    except Exception as e:
        logger.error("AgentPit report error for session %s: %s", session.id, e)
        return None
