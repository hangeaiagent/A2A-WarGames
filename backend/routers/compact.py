"""
Context compaction — summarize old rounds to free context window space.

This router provides two endpoints:
  GET  /api/sessions/{id}/context-usage  — estimate current context window usage
  POST /api/sessions/{id}/compact        — summarize old rounds, mark them compacted

Round discrimination uses Message.round_num (populated since CR-004). Falls back
to Message.stage for legacy sessions where round_num was not persisted.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import Optional

from ..auth import get_db_with_rls, get_current_user, require_user
from ..models import Session as SessionModel, Message, AgentMemory
from ..a2a.llm_client import get_completion_content
from ..models import LLMSettings
from ..analytics.sbert import compute_sbert_harmony

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["compact"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CompactRequest(BaseModel):
    rounds_to_keep: int = 2


class ContextUsageResponse(BaseModel):
    used_chars: int
    estimated_tokens: int
    max_tokens: int
    pct: float


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/context-usage
# ---------------------------------------------------------------------------

@router.get("/{session_id}/context-usage", response_model=ContextUsageResponse)
def get_context_usage(
    session_id: int,
    db: DBSession = Depends(get_db_with_rls),
):
    """
    Estimate context window usage for a session.

    Token count is approximated as total_chars / 4 (a standard rough estimate).
    The max_tokens value reflects a 128k-token context window (typical for modern
    frontier models); this is not read from LLM settings to keep the endpoint fast.
    """
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .all()
    )

    total_chars = sum(len(m.content or "") for m in messages)
    estimated_tokens = total_chars // 4

    # #122: derive context window from the active LLM profile's model name
    # rather than hardcoding 128k (wrong for small-context models like gpt-3.5).
    _CONTEXT_WINDOWS = {
        "gpt-3.5":          16_384,
        "gpt-4-turbo":      128_000,
        "gpt-4o":           128_000,
        "gpt-4o-mini":       128_000,
        "o1":               200_000,
        "o3":               200_000,
        "gemini-2.5-pro":   1_048_576,
        "gemini-2.5-flash":   1_048_576,
        "gemini-2.0-flash":   1_048_576,
        "claude":           200_000,
        "llama-3":          128_000,
        "mistral":           32_000,
    }
    max_tokens = 128_000  # safe default
    active_llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if active_llm and active_llm.default_model:
        model_lower = active_llm.default_model.lower()
        for prefix, window in _CONTEXT_WINDOWS.items():
            if model_lower.startswith(prefix):
                max_tokens = window
                break

    pct = round(estimated_tokens / max_tokens * 100, 1) if max_tokens else 0.0

    return ContextUsageResponse(
        used_chars=total_chars,
        estimated_tokens=estimated_tokens,
        max_tokens=max_tokens,
        pct=pct,
    )


# ---------------------------------------------------------------------------
# POST /api/sessions/{session_id}/compact
# ---------------------------------------------------------------------------

@router.post("/{session_id}/compact")
async def compact_session(
    session_id: int,
    body: CompactRequest,
    user: dict = Depends(require_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """
    Summarize old rounds to reduce context window usage.

    Strategy:
      1. Find all messages ordered by turn index.
      2. Determine the max round_num (falls back to stage for legacy sessions).
      3. Leave the most recent `rounds_to_keep` rounds untouched.
      4. Call the active LLM profile to summarize the older messages.
      5. Mark old messages with compacted=True so the engine can skip them.
      6. Return the summary preview.

    The original messages are NOT deleted — only flagged. The engine should
    check the `compacted` flag and substitute the summary when building context.

    NOTE: This endpoint mutates session state. It is intentionally blocked while
    status == "running" to avoid race conditions with the A2A engine.
    """
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot compact while session is running — wait for it to complete.",
        )

    # Fetch all messages ordered by turn
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.turn)
        .all()
    )

    if not messages:
        raise HTTPException(status_code=400, detail="No messages to compact")

    # Use round_num as the round discriminator (populated by _persist_message since CR-004).
    # Fall back to stage-based grouping only if round_num is absent on all messages.
    has_round_num = any((m.round_num or 0) > 0 for m in messages)
    if has_round_num:
        max_round = max((m.round_num or 0) for m in messages)
        discriminator_name = "round"
    else:
        # Legacy fallback: stage values (1=initial, 2=challenge, 3=synthesis)
        max_round = max((m.stage or 0) for m in messages)
        discriminator_name = "stage"

    if max_round <= 0 or max_round <= body.rounds_to_keep:
        return {
            "status": "nothing_to_compact",
            "reason": (
                f"Only {max_round} {discriminator_name}(s) found; "
                f"rounds_to_keep={body.rounds_to_keep} — nothing to compact."
            ),
        }

    # Compact everything older than the last N rounds
    compact_cutoff = max_round - body.rounds_to_keep
    if has_round_num:
        old_messages = [m for m in messages if (m.round_num or 0) <= compact_cutoff]
    else:
        old_messages = [m for m in messages if (m.stage or 0) <= compact_cutoff]

    if not old_messages:
        return {"status": "nothing_to_compact", "reason": "No messages fall below the cutoff stage."}

    # Build transcript for summarization
    transcript_text = "\n\n".join(
        f"**{m.speaker_name or m.speaker}** (stage {m.stage}, turn {m.turn}): {m.content}"
        for m in old_messages
    )

    # Load active LLM profile
    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if not llm:
        raise HTTPException(
            status_code=400,
            detail="No active LLM profile configured — cannot summarize.",
        )

    logger.info(
        "compact_session: session=%d, compacting %d messages (%ss 1-%d), keeping last %d %ss",
        session_id,
        len(old_messages),
        discriminator_name,
        compact_cutoff,
        body.rounds_to_keep,
        discriminator_name,
    )

    # Call LLM to produce a concise summary
    try:
        summary = await get_completion_content(
            base_url=llm.base_url,
            api_key=llm.api_key,
            model=llm.default_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a debate summarizer. Produce a concise but thorough summary "
                        "that preserves: key positions per stakeholder, areas of agreement, "
                        "areas of disagreement, and unresolved tensions. "
                        "Use stakeholder names. Be factual — do not editorialize."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Summarize these debate {discriminator_name}s (1-{compact_cutoff}) "
                        f"from session {session_id}:\n\n{transcript_text}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=2048,
        )
    except Exception as exc:
        logger.error("compact_session: LLM summarization failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"LLM summarization failed: {exc}",
        )

    # Mark old messages as compacted (Message.compacted column present since initial migration).
    compacted_count = 0
    for m in old_messages:
        m.compacted = True
        compacted_count += 1

    # Persist summary so engine can use it as prior context on next continue/recover (#118)
    session.compact_summary = summary

    db.commit()

    logger.info(
        "compact_session: session=%d compacted successfully — %d messages summarized",
        session_id,
        compacted_count,
    )

    return {
        "status": "compacted",
        "session_id": session_id,
        "rounds_compacted": compact_cutoff,
        "rounds_kept": body.rounds_to_keep,
        "messages_compacted": compacted_count,
        "summary_length": len(summary),
        "summary_preview": summary[:500],
        "note": (
            "Original messages are retained in DB but flagged as compacted. "
            "The A2A engine should substitute this summary as prior context on the next run."
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/sbert-harmony
# ---------------------------------------------------------------------------

@router.get("/{session_id}/sbert-harmony")
def get_sbert_harmony(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Return pairwise S-BERT cosine similarity scores for the latest round messages."""
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(20)
        .all()
    )
    if not messages:
        return {"harmony_score": None, "pairs": []}

    msg_dicts = [{"speaker": m.speaker, "content": m.content} for m in messages]
    result = compute_sbert_harmony(msg_dicts, stakeholders=[])
    if result is None:
        return {"harmony_score": None, "pairs": []}
    return result


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/memories (CR-010)
# ---------------------------------------------------------------------------

@router.get("/{session_id}/memories")
def get_session_memories(
    session_id: int,
    speaker: Optional[str] = None,
    scope: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Return agent memories for a session, optionally filtered by speaker or scope."""
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    query = db.query(AgentMemory).filter_by(session_id=session_id)
    if speaker:
        query = query.filter_by(speaker_slug=speaker)
    if scope:
        query = query.filter_by(scope=scope)
    memories = query.order_by(AgentMemory.salience.desc()).limit(100).all()
    return [
        {
            "id": m.id,
            "speaker": m.speaker_slug,
            "type": m.memory_type,
            "content": m.content,
            "salience": m.salience,
            "scope": m.scope,
            "round": m.round_num,
            "turn": m.turn,
            "decay_factor": m.decay_factor,
            "access_count": m.access_count,
        }
        for m in memories
    ]
