"""
Session pre-warming — background LLM pre-computation on session creation.

When a session is created (topic + stakeholders chosen), this module kicks off
a background task that pre-computes expensive setup work so the first turn
arrives faster when the user clicks "Start Wargame":

  1. Agenda extraction  — LLM call that breaks the question into 2-4 sub-items
  2. Moderator opening  — Round-1 moderator intro pre-generated

Results are cached on the Session row (pre_warm_data JSON blob) and in the
SessionAgenda table.  The engine's run() path checks for pre-warmed data and
skips re-doing the work if it is still valid.

Invalidation:
  - If the user changes config (moderator style, participants, question) after
    pre-warming, call invalidate_pre_warm() to mark the cache stale.
  - The engine always re-extracts if pre_warm_status != "ready".

Race conditions:
  - If run() starts while pre-warming is still in progress ("warming"), the
    engine falls through to the normal extraction path (safe — idempotent).
  - _persist_agenda() in the engine is already idempotent (skips if rows
    already exist), so concurrent writes are safe.
"""

import asyncio
import datetime
import json
import logging
from typing import Optional

from .llm_client import get_completion_json, get_completion_content
from .moderator import build_moderator_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB session factory (overridable in tests)
# ---------------------------------------------------------------------------
# Tests can patch this to return their test DB session instead of the global one.
def _get_db_session(user_id: Optional[str] = None):
    """Return a standalone DB session. Thin wrapper to allow test overrides."""
    from ..database import get_db_session_with_user
    return get_db_session_with_user(user_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def trigger_pre_warm(
    session_id: int,
    question: str,
    stakeholders: list[dict],
    project: dict,
    llm_base_url: str,
    llm_api_key: str,
    chairman_model: str,
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
    user_id: Optional[str] = None,
) -> None:
    """
    Fire-and-forget: schedule pre-warm as a background asyncio task.

    Safe to call multiple times — if a pre-warm task is already running or
    the session is already "ready", the DB write is idempotent.
    """
    asyncio.create_task(
        _run_pre_warm(
            session_id=session_id,
            question=question,
            stakeholders=stakeholders,
            project=project,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            chairman_model=chairman_model,
            moderator_style=moderator_style,
            moderator_name=moderator_name,
            moderator_title=moderator_title,
            moderator_mandate=moderator_mandate,
            moderator_persona_prompt=moderator_persona_prompt,
            user_id=user_id,
        ),
        name=f"pre_warm_session_{session_id}",
    )


def invalidate_pre_warm(session_id: int, user_id: Optional[str] = None) -> None:
    """
    Mark a session's pre-warm cache as invalidated (config changed after warm).

    Call this synchronously whenever the user changes moderator settings,
    participants, or topic after creation but before starting the session.
    """
    from ..models import Session
    db = _get_db_session(user_id)
    try:
        sess = db.query(Session).filter_by(id=session_id).first()
        if sess and sess.pre_warm_status in ("warming", "ready"):
            sess.pre_warm_status = "invalidated"
            sess.config_changed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            logger.info("Pre-warm invalidated for session %s", session_id)
    except Exception as e:
        logger.warning("Failed to invalidate pre-warm for session %s: %s", session_id, e)
    finally:
        db.close()


_PRE_WARM_TIMEOUT_SECS = 300  # treat "warming" sessions older than 5 min as failed (#193)


def get_pre_warm_data(session_id: int, user_id: Optional[str] = None) -> Optional[dict]:
    """
    Return the cached pre-warm blob for a session if status == "ready", else None.

    Used by the engine's run() to check if pre-warmed data is available.
    Returns: {"agenda": [...], "moderator_opening": "...", "warmed_at": "ISO8601"}
    or None if not available / invalidated.

    #193: sessions stuck in "warming" for >5 min are treated as timed-out and
    return None so the engine does a fresh extraction instead of waiting forever.
    """
    from ..models import Session
    db = _get_db_session(user_id)
    try:
        sess = db.query(Session).filter_by(id=session_id).first()
        if not sess:
            return None
        if sess.pre_warm_status == "warming":
            # #210: use config_changed_at if set (invalidated sessions), otherwise fall back
            # to created_at so the timeout fires for sessions that never had config changes.
            now = datetime.datetime.now(datetime.timezone.utc)
            ts = sess.config_changed_at or sess.created_at
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                age = (now - ts).total_seconds()
                if age > _PRE_WARM_TIMEOUT_SECS:
                    logger.warning(
                        "Pre-warm timeout for session %s (warming for %.0fs) — falling back",
                        session_id, age,
                    )
                    return None
            return None  # still warming (within timeout window)
        if sess.pre_warm_status != "ready":
            return None
        if not sess.pre_warm_data:
            return None
        return json.loads(sess.pre_warm_data)
    except Exception as e:
        logger.warning("Failed to read pre-warm data for session %s: %s", session_id, e)
        return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Internal background task
# ---------------------------------------------------------------------------

async def _run_pre_warm(
    session_id: int,
    question: str,
    stakeholders: list[dict],
    project: dict,
    llm_base_url: str,
    llm_api_key: str,
    chairman_model: str,
    moderator_style: str,
    moderator_name: str,
    moderator_title: str,
    moderator_mandate: str,
    moderator_persona_prompt: str,
    user_id: Optional[str],
) -> None:
    """
    Background coroutine: run agenda extraction + moderator opening pre-generation.

    Steps:
      1. Mark session pre_warm_status = "warming"
      2. Extract agenda items via LLM (same prompt as engine._extract_agenda)
      3. Generate round-1 moderator opening (no prior synthesis, no analytics)
      4. Persist agenda to SessionAgenda table (idempotent)
      5. Cache full result in Session.pre_warm_data
      6. Mark session pre_warm_status = "ready"

    On any failure: mark status = null (engine will re-do work at start time).
    """
    logger.info("Pre-warm started for session %s", session_id)

    # Step 1 — mark warming
    if not _set_warm_status(session_id, "warming", user_id):
        logger.warning("Pre-warm aborted — could not mark session %s as warming", session_id)
        return

    try:
        # Step 2 — agenda extraction (mirror of engine._extract_agenda)
        agenda_items = await _extract_agenda(
            question=question,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            chairman_model=chairman_model,
        )

        # Step 3 — moderator opening (round 1, no prior context)
        moderator_opening = await _generate_moderator_opening(
            question=question,
            stakeholders=stakeholders,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            chairman_model=chairman_model,
            moderator_style=moderator_style,
            moderator_name=moderator_name,
            moderator_title=moderator_title,
            moderator_mandate=moderator_mandate,
            moderator_persona_prompt=moderator_persona_prompt,
        )

        # Step 4 — persist agenda to SessionAgenda table (idempotent)
        if agenda_items:
            await _persist_agenda_items(session_id, agenda_items, user_id)

        # Step 5 — store full blob + mark ready
        warm_data = {
            "agenda": agenda_items,
            "moderator_opening": moderator_opening,
            "warmed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "moderator_style": moderator_style,
        }
        _store_warm_data(session_id, warm_data, user_id)
        logger.info(
            "Pre-warm complete for session %s — %d agenda items, opening: %d chars",
            session_id,
            len(agenda_items),
            len(moderator_opening),
        )

    except Exception as exc:
        logger.error("Pre-warm failed for session %s: %s", session_id, exc, exc_info=True)
        # Reset to null so engine re-does the work at start time
        _set_warm_status(session_id, None, user_id)


# ---------------------------------------------------------------------------
# LLM helpers (mirror engine internals but standalone, no engine instance)
# ---------------------------------------------------------------------------

async def _extract_agenda(
    question: str,
    llm_base_url: str,
    llm_api_key: str,
    chairman_model: str,
) -> list[dict]:
    """Extract agenda items — same logic as A2AEngine._extract_agenda."""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a debate facilitator. Given a discussion question, break it into "
                    "2 to 4 specific sub-questions that stakeholders must vote on. "
                    'Respond ONLY with JSON: '
                    '{"items": [{"key": "item_1", "label": "...", "description": "..."}]}'
                ),
            },
            {"role": "user", "content": f"Question: {question}"},
        ]
        result = await get_completion_json(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=chairman_model,
            messages=messages,
            temperature=0.0,
            max_tokens=1200,
            agent_name="pre-warm-agenda-extractor",
        )
        items = result.get("items", [])
        return [
            {
                "key": item.get("key", f"item_{i + 1}"),
                "label": item.get("label", ""),
                "description": item.get("description", ""),
            }
            for i, item in enumerate(items[:4])
            if item.get("label")
        ]
    except Exception as e:
        logger.warning("Pre-warm agenda extraction failed: %s", e)
        return []


async def _generate_moderator_opening(
    question: str,
    stakeholders: list[dict],
    llm_base_url: str,
    llm_api_key: str,
    chairman_model: str,
    moderator_style: str,
    moderator_name: str,
    moderator_title: str,
    moderator_mandate: str,
    moderator_persona_prompt: str,
) -> str:
    """Pre-generate the round-1 moderator intro (no prior synthesis, no analytics)."""
    try:
        system = build_moderator_prompt(
            stakeholders,
            moderator_style,
            moderator_name=moderator_name,
            moderator_title=moderator_title,
            moderator_mandate=moderator_mandate,
            moderator_persona_prompt=moderator_persona_prompt,
        )
        names = ", ".join(s["name"] for s in stakeholders)
        user_content = (
            f"## ROUND 1\n\nStrategic question: {question}\n\n"
            f"This is the opening round. Participants: {names}.\n"
            "Frame the question, set the stakes, and select 2-3 stakeholders to respond first."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        return await get_completion_content(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=chairman_model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            agent_name="pre-warm-moderator",
        )
    except Exception as e:
        logger.warning("Pre-warm moderator opening failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# DB helpers (synchronous — called from async context via direct call)
# ---------------------------------------------------------------------------

def _set_warm_status(session_id: int, status: Optional[str], user_id: Optional[str]) -> bool:
    """Set Session.pre_warm_status. Returns True on success.

    When status='warming', also stamps config_changed_at with the current UTC time
    so get_pre_warm_data() can detect stuck sessions via timeout (#210).
    """
    from ..models import Session
    db = _get_db_session(user_id)
    try:
        sess = db.query(Session).filter_by(id=session_id).first()
        if not sess:
            return False
        sess.pre_warm_status = status
        # #210: stamp when warming started so timeout detection works even for
        # sessions that never had invalidate_pre_warm() called (config_changed_at=None)
        if status == "warming":
            sess.config_changed_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        return True
    except Exception as e:
        logger.error("Failed to set pre_warm_status for session %s: %s", session_id, e)
        return False
    finally:
        db.close()


def _store_warm_data(session_id: int, data: dict, user_id: Optional[str]) -> None:
    """Write the warm data blob and set status = 'ready'."""
    from ..models import Session
    db = _get_db_session(user_id)
    try:
        sess = db.query(Session).filter_by(id=session_id).first()
        if not sess:
            return
        # Only write if not invalidated between start and finish
        if sess.pre_warm_status == "invalidated":
            logger.info(
                "Pre-warm data discarded for session %s — invalidated while warming",
                session_id,
            )
            return
        sess.pre_warm_data = json.dumps(data)
        sess.pre_warm_status = "ready"
        db.commit()
    except Exception as e:
        logger.error("Failed to store pre-warm data for session %s: %s", session_id, e)
    finally:
        db.close()


async def _persist_agenda_items(
    session_id: int,
    items: list[dict],
    user_id: Optional[str],
) -> None:
    """Persist pre-warmed agenda items to SessionAgenda (idempotent)."""
    from ..models import SessionAgenda
    db = _get_db_session(user_id)
    try:
        existing = db.query(SessionAgenda).filter_by(session_id=session_id).count()
        if existing == 0:
            for item in items:
                db.add(SessionAgenda(
                    session_id=session_id,
                    item_key=item["key"],
                    label=item["label"],
                    description=item.get("description", ""),
                ))
            db.commit()
            logger.debug("Pre-warm: persisted %d agenda items for session %s", len(items), session_id)
        else:
            logger.debug(
                "Pre-warm: agenda already exists for session %s (%d rows) — skipping persist",
                session_id,
                existing,
            )
    except Exception as e:
        logger.error("Pre-warm: failed to persist agenda for session %s: %s", session_id, e)
    finally:
        db.close()
