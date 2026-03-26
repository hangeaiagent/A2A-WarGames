"""
Session management — CRUD + wargame execution endpoints.

Endpoints:
  GET/POST/DELETE  /api/sessions/           — CRUD
  POST             /api/sessions/{id}/run   — start wargame
  GET              /api/sessions/{id}/stream — SSE event stream
  POST             /api/sessions/{id}/stop  — graceful stop
  POST             /api/sessions/{id}/inject — consultant injection
  GET              /api/sessions/{id}/analytics — post-session data
"""

import asyncio
import datetime
import json
import logging
import secrets
from typing import Optional

try:
    import networkx as nx  # #107: influence graph (betweenness / eigenvector centrality)
    _NX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NX_AVAILABLE = False

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from pydantic import BaseModel, Field

import uuid as _uuid

from ..auth import get_db_with_rls, get_current_user, require_user, decode_supabase_jwt, security
from ..database import get_db_session_with_user
from ..models import (
    Session, Message, Project, Stakeholder, LLMSettings,
    AnalyticsSnapshot, SessionConfig, TurnAnalytics,
    SessionAgenda, AgendaVote, PrivateThread, PrivateMessage,
    ProviderKey, UserModelPreference,
)
from ..a2a.engine import A2AEngine
from ..a2a.pre_warm import trigger_pre_warm, invalidate_pre_warm, get_pre_warm_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# In-memory registry of running engines (session_id → A2AEngine)
_running_engines: dict[int, A2AEngine] = {}

# #130: short-lived stream tickets so EventSource can auth without exposing JWTs in URLs.
# ticket → {"user": <decoded JWT dict or None>, "expires_at": <datetime UTC>, "session_id": int}
_stream_tickets: dict[str, dict] = {}
_TICKET_TTL_SECS = 30  # tickets expire after 30 seconds


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SessionIn(BaseModel):
    project_id: int
    question: str
    title: str = ""
    participants: list[str] = []

class RunIn(BaseModel):
    num_rounds: int = Field(default=5, ge=1, le=50)
    moderator_style: str = "neutral"
    agents_per_turn: int = Field(default=3, ge=1, le=20)
    moderator_name: str = "Moderator"
    moderator_title: str = ""
    moderator_mandate: str = ""
    moderator_persona_prompt: str = ""
    # Session-level overrides (BUG-004: were silently dropped before)
    anti_groupthink: bool = True          # False disables challenge/contrarian forcing
    devil_advocate_round: int = 0         # reserved — wired in CR-009
    temperature_override: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    # CR-011: private thread config
    private_thread_limit: int = Field(default=3, ge=0, le=20)
    private_thread_depth: int = Field(default=2, ge=1, le=10)
    private_thread_quota_mode: str = "fixed"
    # #200/#97: context window strategy for agent turns
    context_window_strategy: str = "last_2_rounds"  # "last_2_rounds" | "full" | "synthesis_only"
    # Locale for prompt language
    locale: str = "en"  # "en" | "zh"

class InjectIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)  # #159: prevent context overflow
    as_moderator: bool = False

class ContinueIn(BaseModel):
    additional_rounds: int = Field(default=3, ge=1, le=20)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def _safe_json(value: str, default=None):
    """Parse JSON string, returning default on any error (including corrupted data)."""
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _session_out(s: Session, msg_count: int = None) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "title": s.title,
        "question": s.question,
        "status": s.status,
        "participants": _safe_json(s.participants, []),
        "synthesis": s.synthesis,
        "consensus_score": s.consensus_score,
        "moderator_name": s.moderator_name or "Moderator",
        "moderator_title": s.moderator_title or "",
        "moderator_mandate": s.moderator_mandate or "",
        "moderator_persona_prompt": s.moderator_persona_prompt or "",
        "message_count": msg_count if msg_count is not None else len(s.messages),
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "checkpoint": _safe_json(s.checkpoint),
    }


def _message_out(m: Message) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "turn": m.turn,
        "stage": m.stage,
        "speaker": m.speaker,
        "speaker_name": m.speaker_name,
        "content": m.content,
        "sentiment": json.loads(m.sentiment) if m.sentiment else None,
        "cosine_similarity": m.cosine_similarity,
        "created_at": m.created_at.isoformat(),
    }


def _stakeholder_to_dict(s: Stakeholder) -> dict:
    return {
        "slug": s.slug, "name": s.name, "role": s.role,
        "department": s.department, "attitude": s.attitude,
        "attitude_label": s.attitude_label, "influence": s.influence,
        "interest": s.interest, "needs": s.needs, "fears": s.fears,
        "preconditions": s.preconditions, "quote": s.quote,
        "signal_cle": s.signal_cle, "adkar": s.adkar,
        "color": s.color, "llm_model": s.llm_model,
        "llm_provider": s.llm_provider,
        "llm_model_display": s.llm_model_display,
        "system_prompt": s.system_prompt,
        # Rich profile fields — used by prompt_compiler for persona generation
        "hard_constraints": s.hard_constraints,
        "key_concerns": s.key_concerns,
        "cognitive_biases": s.cognitive_biases,
        "batna": s.batna,
        "anti_sycophancy": s.anti_sycophancy,
        "grounding_quotes": s.grounding_quotes,
        "communication_style": s.communication_style,
        "success_criteria": s.success_criteria,
    }


def _stage_to_int(stage: str) -> int:
    return {"intro": 0, "response": 1, "challenge": 2, "synthesis": 3, "inject": 4}.get(stage, 1)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------
def _parse_uid(sub: Optional[str]) -> Optional[_uuid.UUID]:
    """Convert a JWT 'sub' string to uuid.UUID. Returns None on failure."""
    if not sub:
        return None
    try:
        return _uuid.UUID(sub)
    except (ValueError, AttributeError):
        return None


def _check_project_access(project: Project, uid: Optional[_uuid.UUID]) -> bool:
    """Return True if the user (identified by uid UUID) may read this project."""
    if project is None:
        return False
    if project.is_public:
        return True
    return uid is not None and project.user_id == uid


@router.get("/")
def list_sessions(
    project_id: Optional[int] = None,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    uid = _parse_uid(user.get("sub") if user else None)
    # Build message counts in a single query to avoid N+1
    count_sq = (
        db.query(Message.session_id, func.count(Message.id).label("cnt"))
        .group_by(Message.session_id)
        .subquery()
    )
    q = db.query(Session, func.coalesce(count_sq.c.cnt, 0).label("msg_count"))
    q = q.outerjoin(count_sq, Session.id == count_sq.c.session_id)
    q = q.join(Project, Project.id == Session.project_id)
    if uid:
        q = q.filter((Project.user_id == uid) | (Project.is_public == True))  # noqa: E712
    else:
        q = q.filter(Project.is_public == True)  # noqa: E712
    if project_id:
        q = q.filter(Session.project_id == project_id)
    rows = q.order_by(Session.created_at.desc()).all()
    return [_session_out(s, msg_count=cnt) for s, cnt in rows]


@router.get("/{session_id}")
def get_session(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    s = db.query(Session).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    project = db.query(Project).filter_by(id=s.project_id).first()
    uid = _parse_uid(user.get("sub") if user else None)
    if not _check_project_access(project, uid):
        raise HTTPException(404, "Session not found")
    return _session_out(s)


@router.get("/{session_id}/pre-warm-status")
def get_pre_warm_status(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """
    Return the pre-warm status for a session.

    Response:
      {
        "session_id": int,
        "pre_warm_status": "warming" | "ready" | "invalidated" | null,
        "has_agenda": bool,
        "has_moderator_opening": bool,
        "warmed_at": "ISO8601" | null
      }

    The frontend can poll this after session creation to show a readiness indicator.
    Once status == "ready", the first turn will be noticeably faster.
    """
    s = db.query(Session).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    project = db.query(Project).filter_by(id=s.project_id).first()
    uid = _parse_uid(user.get("sub") if user else None)
    if not _check_project_access(project, uid):
        raise HTTPException(404, "Session not found")

    warm_data: dict = {}
    if s.pre_warm_data:
        try:
            warm_data = json.loads(s.pre_warm_data)
        except Exception:
            warm_data = {}

    return {
        "session_id": session_id,
        "pre_warm_status": s.pre_warm_status,
        "has_agenda": bool(warm_data.get("agenda")),
        "has_moderator_opening": bool(warm_data.get("moderator_opening")),
        "warmed_at": warm_data.get("warmed_at"),
    }


@router.get("/{session_id}/messages")
def get_messages(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    s = db.query(Session).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    project = db.query(Project).filter_by(id=s.project_id).first()
    uid = _parse_uid(user.get("sub") if user else None)
    if not _check_project_access(project, uid):
        raise HTTPException(404, "Session not found")
    msgs = db.query(Message).filter_by(session_id=session_id).order_by(Message.turn).all()
    return [_message_out(m) for m in msgs]


@router.post("/", status_code=201)
async def create_session(
    payload: SessionIn,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    project = db.query(Project).filter_by(id=payload.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    participants = payload.participants
    if not participants:
        active = db.query(Stakeholder).filter_by(project_id=payload.project_id, is_active=True).all()
        participants = [s.slug for s in active]

    session = Session(
        project_id=payload.project_id,
        question=payload.question,
        title=payload.title or payload.question[:80],
        participants=json.dumps(participants),
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # --- Trigger background pre-warming (non-blocking) ---
    # Requires LLM settings to be configured; skip silently if not.
    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if llm:
        # Build stakeholder list for pre-warm (same shape as engine expects)
        stk_q = db.query(Stakeholder).filter_by(project_id=payload.project_id, is_active=True)
        if participants:
            stk_q = stk_q.filter(Stakeholder.slug.in_(participants))
        warm_stakeholders = [_stakeholder_to_dict(s) for s in stk_q.all()]
        warm_project = {
            "name": project.name,
            "organization": project.organization,
            "context": project.context,
            "description": project.description,
        }
        user_id = _parse_uid(user.get("sub") if user else None)
        await trigger_pre_warm(
            session_id=session.id,
            question=payload.question,
            stakeholders=warm_stakeholders,
            project=warm_project,
            llm_base_url=llm.base_url,
            llm_api_key=llm.api_key,
            chairman_model=llm.chairman_model,
            user_id=user_id,
        )

    return _session_out(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: int, user: dict = Depends(require_user), db: DBSession = Depends(get_db_with_rls)):
    s = db.query(Session).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    if session_id in _running_engines:
        _running_engines[session_id].request_stop()
        del _running_engines[session_id]
    # Manually delete child rows whose FK lacks ondelete="CASCADE".
    # (AnalyticsSnapshot, SessionConfig, TurnAnalytics were defined without
    #  DB-level cascade, so SQLAlchemy ORM cascade cannot handle them.)
    db.query(TurnAnalytics).filter_by(session_id=session_id).delete(synchronize_session=False)
    db.query(SessionConfig).filter_by(session_id=session_id).delete(synchronize_session=False)
    db.query(AnalyticsSnapshot).filter_by(session_id=session_id).delete(synchronize_session=False)
    db.delete(s)
    db.commit()


# ---------------------------------------------------------------------------
# CR-019 — Per-agent model resolution
# ---------------------------------------------------------------------------

def resolve_model_for_agent(
    stakeholder_dict: dict,
    user_id: str | None,
    llm_settings: LLMSettings,
    db: DBSession | None = None,
) -> tuple | None:
    """Resolve (base_url, api_key, model_id) override for an agent.

    Resolution order:
    1. Stakeholder-level override (llm_provider + llm_model) with ProviderKey lookup
    2. Stakeholder-level override with preset base_url fallback (global API key)
    3. Return None — engine uses its defaults

    Returns (base_url, api_key, model_id) or None if no override applies.
    """
    from ..provider_presets import get_preset_by_id

    provider_id = stakeholder_dict.get("llm_provider")
    model_id = stakeholder_dict.get("llm_model")

    # 1. Per-stakeholder override with encrypted ProviderKey
    if provider_id and model_id and user_id and db:
        pk = (
            db.query(ProviderKey)
            .filter_by(user_id=user_id, provider_id=provider_id)
            .first()
        )
        if pk:
            api_key = pk.get_api_key()
            base_url = pk.base_url
            if not base_url:
                preset = get_preset_by_id(provider_id)
                base_url = preset["base_url"] if preset else None
            if base_url:
                return base_url.rstrip("/"), api_key, model_id

    # 2. Stakeholder override with preset base_url + global API key
    if provider_id and model_id:
        preset = get_preset_by_id(provider_id)
        if preset and preset.get("base_url"):
            return preset["base_url"], llm_settings.api_key, model_id

    # 3. No override — engine default
    return None


def _build_agent_model_overrides(
    stakeholder_dicts: list[dict],
    llm_settings: LLMSettings,
    user_id: str | None = None,
    db: DBSession | None = None,
) -> dict:
    """Build a dict of per-agent model overrides for the engine.

    Returns: {slug: (base_url, api_key, model_id)} for stakeholders with provider overrides.
    """
    overrides = {}
    for stk_dict in stakeholder_dicts:
        resolved = resolve_model_for_agent(stk_dict, user_id, llm_settings, db)
        if resolved:
            overrides[stk_dict["slug"]] = resolved
    return overrides


# ---------------------------------------------------------------------------
# Wargame execution endpoints (Phase 1)
# ---------------------------------------------------------------------------
@router.post("/{session_id}/run")
def run_session(
    session_id: int, payload: RunIn,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Start the wargame council loop. Returns immediately; events via SSE."""
    session = db.query(Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status == "running":
        raise HTTPException(409, "Session is already running")
    if session_id in _running_engines:
        raise HTTPException(409, "Engine already active for this session")

    project = db.query(Project).filter_by(id=session.project_id).first()
    participants = json.loads(session.participants or "[]")
    stk_q = db.query(Stakeholder).filter_by(project_id=session.project_id, is_active=True)
    if participants:
        stk_q = stk_q.filter(Stakeholder.slug.in_(participants))
    stakeholders = stk_q.all()

    if not stakeholders:
        raise HTTPException(400, "No active stakeholders found")

    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if not llm:
        raise HTTPException(400, "No active LLM settings. Configure one in Settings.")

    # --- Task 3: Build prior session context ---
    prior_session_context = _build_prior_session_context(session.project_id, session_id, db)

    # --- Pre-warm: check if cached data is valid and matches requested config ---
    user_id = user["sub"] if user else None
    warm_data = get_pre_warm_data(session_id, user_id)
    # Pre-warm cache is only reusable if the moderator style matches what was pre-computed.
    # (We always pre-warm with the default style; if the user changed it, we discard.)
    if warm_data and warm_data.get("moderator_style") != payload.moderator_style:
        logger.info(
            "Pre-warm cache discarded for session %s — moderator_style changed (%s → %s)",
            session_id,
            warm_data.get("moderator_style"),
            payload.moderator_style,
        )
        invalidate_pre_warm(session_id, user_id)
        warm_data = None

    engine = A2AEngine(
        session_id=session_id,
        question=session.question,
        stakeholders=[_stakeholder_to_dict(s) for s in stakeholders],
        project={"name": project.name, "organization": project.organization,
                 "context": project.context, "description": project.description},
        llm_base_url=llm.base_url,
        llm_api_key=llm.api_key,
        default_model=llm.default_model,
        chairman_model=llm.chairman_model,
        num_rounds=payload.num_rounds,
        agents_per_turn=payload.agents_per_turn,
        moderator_style=payload.moderator_style,
        temperature=payload.temperature_override if payload.temperature_override is not None else llm.temperature,
        max_tokens=llm.max_tokens,
        anti_groupthink=payload.anti_groupthink,
        moderator_name=payload.moderator_name,
        moderator_title=payload.moderator_title,
        moderator_mandate=payload.moderator_mandate,
        moderator_persona_prompt=payload.moderator_persona_prompt,
        prior_session_context=prior_session_context,
        feature_flags=llm.feature_flags_dict,
        project_id=session.project_id,
        locale=payload.locale,
    )
    engine.user_id = user_id
    engine.council_models = llm.council_models_list  # model fallback chain
    # CR-019: per-stakeholder model overrides
    stk_dicts = [_stakeholder_to_dict(s) for s in stakeholders]
    engine.agent_model_overrides = _build_agent_model_overrides(stk_dicts, llm, user_id, db)
    # CR-011: thread private thread config from payload into engine
    engine._private_thread_limit = payload.private_thread_limit
    engine._private_thread_depth = payload.private_thread_depth
    engine._private_thread_quota_mode = payload.private_thread_quota_mode
    # #200/#97: forward context window strategy
    engine.context_window_strategy = payload.context_window_strategy

    # Inject pre-warmed data into engine so run() skips redundant LLM calls
    if warm_data:
        if warm_data.get("agenda"):
            engine._pre_warmed_agenda = warm_data["agenda"]
        if warm_data.get("moderator_opening"):
            engine._pre_warmed_moderator_opening = warm_data["moderator_opening"]
        logger.info(
            "Pre-warm cache applied to engine for session %s (agenda=%s, opening=%s)",
            session_id,
            bool(warm_data.get("agenda")),
            bool(warm_data.get("moderator_opening")),
        )

    # #176: commit DB state BEFORE registering engine — avoids window where status="running"
    # but _running_engines has no entry yet (concurrent /stream gets 404)
    session.status = "running"
    session.moderator_name = payload.moderator_name
    session.moderator_title = payload.moderator_title
    session.moderator_mandate = payload.moderator_mandate
    session.moderator_persona_prompt = payload.moderator_persona_prompt
    existing_cfg = db.query(SessionConfig).filter_by(session_id=session_id).first()
    if existing_cfg:
        existing_cfg.num_rounds = payload.num_rounds
        existing_cfg.agents_per_turn = payload.agents_per_turn
        existing_cfg.moderator_style = payload.moderator_style
        existing_cfg.private_thread_limit = payload.private_thread_limit
        existing_cfg.private_thread_depth = payload.private_thread_depth
        existing_cfg.private_thread_quota_mode = payload.private_thread_quota_mode
        # #174: persist anti_groupthink and devil_advocate_round so continue/recover can restore them
        existing_cfg.anti_groupthink = payload.anti_groupthink
        existing_cfg.devil_advocate_round = payload.devil_advocate_round
    else:
        db.add(SessionConfig(
            session_id=session_id, num_rounds=payload.num_rounds,
            agents_per_turn=payload.agents_per_turn, moderator_style=payload.moderator_style,
            private_thread_limit=payload.private_thread_limit,
            private_thread_depth=payload.private_thread_depth,
            private_thread_quota_mode=payload.private_thread_quota_mode,
            # #174: persist anti_groupthink and devil_advocate_round so continue/recover can restore them
            anti_groupthink=payload.anti_groupthink,
            devil_advocate_round=payload.devil_advocate_round,
        ))
    db.commit()

    # Register engine after DB commit so any status check also sees the registered engine
    _running_engines[session_id] = engine

    return {"status": "started", "session_id": session_id, "num_rounds": payload.num_rounds}


# ---------------------------------------------------------------------------
# Shared SSE stream helper (#102: de-duplicate event_generator across
# stream / recover / continue endpoints)
# ---------------------------------------------------------------------------

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _sse_event_generator(
    engine: "A2AEngine",
    request: Request,
    session_id: int,
    start_round: int,
    skip_speakers: list,
    log_context: str = "",
):
    """Shared async generator for all three SSE stream endpoints.

    Drives engine.run(), handles keepalive pings, fires background DB persist
    tasks for turn_end and analytics events, and calls _finalize_session on
    normal completion or error.  The caller wraps this in StreamingResponse.
    """
    error_occurred = False
    finalized = False  # #137: guard against double _finalize_session calls
    bg_persist_tasks = []
    PING_INTERVAL = 25  # seconds
    label = f" ({log_context})" if log_context else ""
    engine_iter = engine.run(start_round=start_round, skip_speakers=skip_speakers).__aiter__()
    # Persistent next-event task — survives across ping intervals so that
    # long-running LLM calls (agenda extraction, moderator intro, agent turns)
    # are NOT cancelled by the keepalive timeout.  Previous implementation used
    # asyncio.wait_for() which cancels the __anext__() coroutine on timeout,
    # destroying the generator's in-flight LLM request.
    pending_next: asyncio.Task = None
    try:
        while True:
            if await request.is_disconnected():
                engine.request_stop()
                break

            # Start or reuse a pending __anext__ task
            if pending_next is None:
                pending_next = asyncio.ensure_future(engine_iter.__anext__())

            done, _ = await asyncio.wait({pending_next}, timeout=PING_INTERVAL)
            if not done:
                # Timeout — send keepalive ping but do NOT cancel the pending task
                yield "event: ping\ndata: {}\n\n"
                continue

            # Task completed — retrieve result
            pending_next = None
            try:
                event = done.pop().result()
            except StopAsyncIteration:
                break
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as inner_exc:
                # Engine generator raised — treat as engine error
                logger.exception("Engine __anext__ raised%s", label)
                error_occurred = True
                yield f"event: error\ndata: {json.dumps({'message': str(inner_exc)})}\n\n"
                if not finalized:
                    finalized = True
                    _finalize_session(session_id, engine, error=str(inner_exc))
                break

            event_type = event.get("event", "message")
            data = json.dumps(event.get("data", {}))

            # Stream token and status events directly without persisting
            if event_type in ("content_token", "thinking_token", "turn_start", "status"):
                yield f"event: {event_type}\ndata: {data}\n\n"
                continue

            yield f"event: {event_type}\ndata: {data}\n\n"

            if event_type == "turn" or event_type == "turn_end":
                loop = asyncio.get_running_loop()
                t = loop.run_in_executor(
                    None, _persist_message, session_id, event["data"], getattr(engine, "user_id", None)
                )
                bg_persist_tasks.append(t)
            elif event_type == "analytics":
                loop = asyncio.get_running_loop()
                t = loop.run_in_executor(
                    None, _persist_analytics_snapshot, session_id, event["data"], getattr(engine, "user_id", None)
                )
                bg_persist_tasks.append(t)
            elif event_type == "error":
                error_occurred = True
                err_msg = event.get("data", {}).get("message", "Unknown engine error")
                if not finalized:
                    finalized = True
                    _finalize_session(session_id, engine, error=err_msg)
    except Exception as e:
        error_occurred = True
        logger.exception("SSE stream error%s", label)
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        if not finalized:
            finalized = True
            _finalize_session(session_id, engine, error=str(e))
    finally:
        # Cancel any in-flight __anext__ task on disconnect/error
        if pending_next is not None and not pending_next.done():
            pending_next.cancel()
        engine._is_streaming = False
        if bg_persist_tasks:
            await asyncio.gather(*bg_persist_tasks, return_exceptions=True)
        if session_id in _running_engines:
            del _running_engines[session_id]
        if not error_occurred and not finalized:
            finalized = True
            _finalize_session(session_id, engine)


@router.get("/{session_id}/stream")
async def stream_session(
    session_id: int,
    request: Request,
    ticket: Optional[str] = Query(None),
    token: Optional[str] = Query(None),  # #130: deprecated — use ticket instead
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """SSE endpoint — streams turn, observer, analytics, synthesis, complete events.

    Auth priority:
      1. Authorization header (always preferred)
      2. ?ticket=<short-lived one-time token> from POST /stream-ticket (#130)
      3. ?token=<JWT> — deprecated, kept for backward compatibility
    """
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No running engine. Call POST /run first.")

    # Guard against concurrent stream connections for the same engine (#127)
    if getattr(engine, '_is_streaming', False):
        raise HTTPException(409, "Session is already being streamed by another client")
    engine._is_streaming = True

    # Resolve user: Authorization header > one-time ticket > deprecated ?token=
    user = None
    if credentials:
        try:
            user = decode_supabase_jwt(credentials.credentials)
        except Exception:
            pass
    elif ticket:
        # #130: validate and consume the one-time stream ticket
        now = datetime.datetime.now(datetime.timezone.utc)
        ticket_data = _stream_tickets.pop(ticket, None)
        if ticket_data and ticket_data["expires_at"] > now and ticket_data["session_id"] == session_id:
            user = ticket_data["user"]
        # If ticket is invalid/expired/wrong session, proceed as anonymous (user=None)
    elif token:
        try:
            user = decode_supabase_jwt(token)
        except Exception:
            pass

    # #153: use _start_round if set (handles engines built by resume_from_db)
    _start_round = getattr(engine, "_start_round", 1)
    _skip_speakers = getattr(engine, "_skip_speakers", [])

    return StreamingResponse(
        _sse_event_generator(engine, request, session_id, _start_round, _skip_speakers),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{session_id}/stream-ticket")
async def create_stream_ticket(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
):
    """Issue a short-lived (30s) one-time ticket for the SSE stream endpoint.

    #130: EventSource cannot send custom headers, so the frontend must pass the
    JWT via ?token= query param — which exposes it in server access logs.
    Instead: POST /stream-ticket (with Authorization header) returns a ticket
    that is never a JWT.  The stream endpoint accepts ?ticket=<ticket> and
    consumes it immediately (one-time use, 30s TTL).
    """
    # Purge expired tickets lazily to avoid unbounded growth
    now = datetime.datetime.now(datetime.timezone.utc)
    expired = [k for k, v in _stream_tickets.items() if v["expires_at"] < now]
    for k in expired:
        del _stream_tickets[k]

    ticket = secrets.token_urlsafe(32)
    _stream_tickets[ticket] = {
        "user": user,
        "session_id": session_id,
        "expires_at": now + datetime.timedelta(seconds=_TICKET_TTL_SECS),
    }
    return {"ticket": ticket, "expires_in": _TICKET_TTL_SECS}


@router.post("/{session_id}/stop")
def stop_session(
    session_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Gracefully stop a running session after current turn."""
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No running engine for this session")
    engine.request_stop()
    return {"status": "stop_requested", "session_id": session_id}


# ---------------------------------------------------------------------------
# Mute / Unmute agents at runtime (#115)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/agents/{slug}/mute")
def mute_agent(
    session_id: int,
    slug: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Mute an agent so it is excluded from speaker selection for this session.

    The mute state is runtime-only and resets when the session ends or is recovered.
    """
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No running engine for this session")
    engine._muted_agents.add(slug)
    engine.speaker_queue.muted_agents.add(slug)
    logger.info("Agent %s muted in session %d", slug, session_id)
    return {"status": "muted", "session_id": session_id, "slug": slug}


@router.post("/{session_id}/agents/{slug}/unmute")
def unmute_agent(
    session_id: int,
    slug: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Unmute an agent so it can be selected as a speaker again."""
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No running engine for this session")
    engine._muted_agents.discard(slug)
    engine.speaker_queue.muted_agents.discard(slug)
    logger.info("Agent %s unmuted in session %d", slug, session_id)
    return {"status": "unmuted", "session_id": session_id, "slug": slug}



# ---------------------------------------------------------------------------
# Pause / Resume (Task 1)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/pause")
def pause_session(session_id: int, user: Optional[dict] = Depends(get_current_user), db: DBSession = Depends(get_db_with_rls)):
    """Pause a running session. The engine will finish its current LLM call, then wait.

    Uses optional auth (get_current_user) consistent with recover/continue — DB access is
    still protected by RLS through get_db_with_rls.  Using require_user here caused a 401
    "Authentication required" whenever the frontend's Authorization header was absent or
    contained an expired token, making it impossible to pause without re-logging in.
    """
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No active engine for this session")
    if engine.is_paused:
        raise HTTPException(409, "Session is already paused")
    engine.pause()
    # Persist status and checkpoint to DB for crash recovery
    session = db.query(Session).filter_by(id=session_id).first()
    if session:
        session.status = "paused"
        session.checkpoint = json.dumps(engine.get_checkpoint())
        db.commit()
    return {"status": "paused", "session_id": session_id, "checkpoint": engine.get_checkpoint()}


@router.post("/{session_id}/resume")
def resume_session(session_id: int, user: Optional[dict] = Depends(get_current_user), db: DBSession = Depends(get_db_with_rls)):
    """Resume a paused session (engine is still in memory).

    Uses optional auth (get_current_user) consistent with recover/continue.  The previous
    require_user guard caused "Authentication required" (HTTP 401) errors when the JWT
    was expired or the Authorization header was missing — e.g., after a token refresh race
    or when running without Supabase JWT configured.  Session ownership is enforced via RLS
    through get_db_with_rls, so strict auth here was redundant and harmful.
    """
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No active engine for this session")
    if not engine.is_paused:
        raise HTTPException(409, "Session is not paused")
    engine.resume()
    # Clear paused status and checkpoint
    session = db.query(Session).filter_by(id=session_id).first()
    if session:
        session.status = "running"
        session.checkpoint = None
        db.commit()
    return {"status": "resumed", "session_id": session_id}


# ---------------------------------------------------------------------------
# Recover Session (crash recovery for paused/failed/interrupted sessions)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/recover")
async def recover_session(
    session_id: int,
    payload: ContinueIn,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Reconstruct engine from DB for crashed/paused/failed sessions.

    Registers the rebuilt engine in _running_engines and returns JSON
    {"status": "started"} immediately — matching the two-step POST /run +
    GET /stream pattern.  The client opens GET /stream after this call.
    This fixes the axios-buffers-SSE regression where the old StreamingResponse
    return caused the frontend to block until session completion before the
    EventSource was opened, leaving GET /stream to 404 on a dead engine.

    Only allowed when the session has no live engine in memory (i.e., engine
    crashed or server restarted). For sessions still in memory and paused,
    use /resume instead.
    """
    session = db.query(Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status not in ("paused", "running", "failed", "interrupted"):
        raise HTTPException(409, f"Session status is '{session.status}'; only paused/running/failed sessions can be recovered")
    if session_id in _running_engines:
        raise HTTPException(409, "Engine is still active in memory — use /resume or /stop instead")
    if payload.additional_rounds < 1:
        raise HTTPException(400, "additional_rounds must be at least 1")

    project = db.query(Project).filter_by(id=session.project_id).first()
    participants = json.loads(session.participants or "[]")
    stk_q = db.query(Stakeholder).filter_by(project_id=session.project_id, is_active=True)
    if participants:
        stk_q = stk_q.filter(Stakeholder.slug.in_(participants))
    stakeholders = stk_q.all()

    if not stakeholders:
        raise HTTPException(400, "No active stakeholders found")

    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if not llm:
        raise HTTPException(400, "No active LLM settings. Configure one in Settings.")

    original_config = db.query(SessionConfig).filter_by(session_id=session_id).first()
    original_status = session.status  # save for rollback on engine build failure

    try:
        engine = await A2AEngine.resume_from_db(
            session_id=session_id,
            additional_rounds=payload.additional_rounds,
            stakeholders=[_stakeholder_to_dict(s) for s in stakeholders],
            project={"name": project.name, "organization": project.organization,
                     "context": project.context, "description": project.description},
            llm_base_url=llm.base_url,
            llm_api_key=llm.api_key,
            default_model=llm.default_model,
            chairman_model=llm.chairman_model,
            agents_per_turn=original_config.agents_per_turn if original_config else 3,
            moderator_style=original_config.moderator_style if original_config else "neutral",
            temperature=original_config.temperature_override if (original_config and original_config.temperature_override is not None) else llm.temperature,
            max_tokens=llm.max_tokens,
            user_id=_parse_uid(user.get("sub") if user else None),
            project_id=session.project_id,
            resume_mode="mid_round",
        )
    except Exception as e:
        logger.error("recover_session: engine build failed for session %s: %s", session_id, e)
        session.status = original_status
        db.commit()
        raise HTTPException(500, f"Failed to reconstruct engine: {e}")

    # #163/#145: set question and other fields BEFORE registering in _running_engines
    # to avoid window where engine.question="" if a concurrent /stream opens early
    engine.question = session.question
    engine.feature_flags = llm.feature_flags_dict
    engine.moderator_name = session.moderator_name or "Moderator"
    engine.moderator_title = session.moderator_title or ""
    engine.moderator_mandate = session.moderator_mandate or ""
    engine.moderator_persona_prompt = session.moderator_persona_prompt or ""
    # CR-019: per-stakeholder model overrides (recover path)
    _uid = user.get("sub") if user else None
    engine.agent_model_overrides = _build_agent_model_overrides(
        [_stakeholder_to_dict(s) for s in stakeholders], llm, _uid, db
    )
    # #155/#174: restore all SessionConfig fields on recover path
    if original_config:
        engine.anti_groupthink = original_config.anti_groupthink
        engine.devil_advocate_round = getattr(original_config, 'devil_advocate_round', 0) or 0
        engine._private_thread_limit = getattr(original_config, 'private_thread_limit', 3) or 3
        engine._private_thread_depth = getattr(original_config, 'private_thread_depth', 2) or 2
        engine._private_thread_quota_mode = getattr(original_config, 'private_thread_quota_mode', 'fixed') or 'fixed'

    # Only mark running after engine is successfully built
    session.status = "running"
    session.checkpoint = None
    db.commit()

    # Register engine so GET /stream can pick it up immediately.
    # _is_streaming is intentionally NOT set here — GET /stream owns that flag,
    # ensuring the concurrent-stream guard works correctly.
    _running_engines[session_id] = engine

    return {"status": "started", "session_id": session_id, "additional_rounds": payload.additional_rounds}


# ---------------------------------------------------------------------------
# Inject message
# ---------------------------------------------------------------------------

@router.post("/{session_id}/inject")
async def inject_message(
    session_id: int,
    payload: InjectIn,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Inject a consultant message into a running debate."""
    engine = _running_engines.get(session_id)
    if not engine:
        raise HTTPException(404, "No running engine for this session")
    msg = await engine.inject_message(payload.content, as_moderator=payload.as_moderator)
    return msg




# ---------------------------------------------------------------------------
# Continue Session (Task 2)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/continue")
async def continue_session(
    session_id: int,
    payload: ContinueIn,
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db_with_rls),
):
    """Add additional rounds to a completed/stopped session.

    Registers the rebuilt engine in _running_engines and returns JSON
    {"status": "started"} immediately — matching the two-step POST /run +
    GET /stream pattern.  The client opens GET /stream after this call.
    This fixes the axios-buffers-SSE regression (same root cause as /recover).
    """
    session = db.query(Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status not in ("complete", "stopped", "errored", "failed", "paused"):
        raise HTTPException(409, f"Session status is '{session.status}'; only completed/stopped/errored/paused sessions can be continued")
    if session_id in _running_engines:
        raise HTTPException(409, "An engine is already active for this session")
    if payload.additional_rounds < 1:
        raise HTTPException(400, "additional_rounds must be at least 1")

    project = db.query(Project).filter_by(id=session.project_id).first()
    participants = json.loads(session.participants or "[]")
    stk_q = db.query(Stakeholder).filter_by(project_id=session.project_id, is_active=True)
    if participants:
        stk_q = stk_q.filter(Stakeholder.slug.in_(participants))
    stakeholders = stk_q.all()

    if not stakeholders:
        raise HTTPException(400, "No active stakeholders found")

    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if not llm:
        raise HTTPException(400, "No active LLM settings. Configure one in Settings.")

    # Restore original session config (if saved)
    original_config = db.query(SessionConfig).filter_by(session_id=session_id).first()
    original_status = session.status  # save for rollback on engine build failure

    try:
        engine = await A2AEngine.resume_from_db(
            session_id=session_id,
            additional_rounds=payload.additional_rounds,
            stakeholders=[_stakeholder_to_dict(s) for s in stakeholders],
            project={"name": project.name, "organization": project.organization,
                     "context": project.context, "description": project.description},
            llm_base_url=llm.base_url,
            llm_api_key=llm.api_key,
            default_model=llm.default_model,
            chairman_model=llm.chairman_model,
            agents_per_turn=original_config.agents_per_turn if original_config else 3,
            moderator_style=original_config.moderator_style if original_config else "neutral",
            temperature=original_config.temperature_override if (original_config and original_config.temperature_override is not None) else llm.temperature,
            max_tokens=llm.max_tokens,
            user_id=_parse_uid(user.get("sub") if user else None),
            project_id=session.project_id,
        )
    except Exception as e:
        logger.error("continue_session: engine build failed for session %s: %s", session_id, e)
        session.status = original_status
        db.commit()
        raise HTTPException(500, f"Failed to reconstruct engine: {e}")

    # #163/#145: set question and other fields BEFORE registering in _running_engines
    engine.question = session.question
    engine.feature_flags = llm.feature_flags_dict
    engine.moderator_name = session.moderator_name or "Moderator"
    engine.moderator_title = session.moderator_title or ""
    engine.moderator_mandate = session.moderator_mandate or ""
    engine.moderator_persona_prompt = session.moderator_persona_prompt or ""
    # CR-019: per-stakeholder model overrides (continue path)
    _uid = user.get("sub") if user else None
    engine.agent_model_overrides = _build_agent_model_overrides(
        [_stakeholder_to_dict(s) for s in stakeholders], llm, _uid, db
    )
    # #155/#174: restore all SessionConfig fields on continue path
    if original_config:
        engine.anti_groupthink = original_config.anti_groupthink
        engine.devil_advocate_round = getattr(original_config, 'devil_advocate_round', 0) or 0
        engine._private_thread_limit = getattr(original_config, 'private_thread_limit', 3) or 3
        engine._private_thread_depth = getattr(original_config, 'private_thread_depth', 2) or 2
        engine._private_thread_quota_mode = getattr(original_config, 'private_thread_quota_mode', 'fixed') or 'fixed'

    # Only mark running after engine is successfully built
    session.status = "running"
    db.commit()

    # Register engine so GET /stream can pick it up immediately.
    # _is_streaming is intentionally NOT set here — GET /stream owns that flag.
    _running_engines[session_id] = engine

    return {"status": "started", "session_id": session_id, "additional_rounds": payload.additional_rounds}

@router.get("/{session_id}/analytics")
def get_analytics(session_id: int, db: DBSession = Depends(get_db_with_rls)):
    """Return full analytics for a completed session."""
    session = db.query(Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    snapshots = db.query(AnalyticsSnapshot).filter_by(session_id=session_id).order_by(AnalyticsSnapshot.round).all()
    turn_data = db.query(TurnAnalytics).filter_by(session_id=session_id).order_by(TurnAnalytics.turn).all()

    rounds_data = [{
        "round": s.round, "consensus_score": s.consensus_score,
        "consensus_velocity": s.consensus_velocity,
        "polarization_index": s.polarization_index,
        "coalition_data": json.loads(s.coalition_data) if s.coalition_data else None,
        "influence_data": json.loads(s.influence_data) if s.influence_data else None,
        "risk_scores": json.loads(s.risk_scores) if s.risk_scores else None,
    } for s in snapshots] if snapshots else []

    turns_data = [{
        "turn": t.turn, "round": t.round, "speaker": t.speaker,
        "position_summary": t.position_summary,
        "sentiment_data": json.loads(t.sentiment_data) if t.sentiment_data else None,
        "behavioral_signals": json.loads(t.behavioral_signals) if t.behavioral_signals else None,
        "claims": json.loads(t.claims) if t.claims else None,
    } for t in turn_data] if turn_data else []

    # Flattened top-level keys expected by frontend AnalyticsDashboard
    consensus_trajectory = [r["consensus_score"] for r in rounds_data if r.get("consensus_score") is not None]
    final_consensus = consensus_trajectory[-1] if consensus_trajectory else session.consensus_score
    last_round = rounds_data[-1] if rounds_data else {}
    influence_leaderboard = last_round.get("influence_data") or []
    risk_table = last_round.get("risk_scores") or []
    coalition_map = (last_round.get("coalition_data") or {}).get("clusters") or []

    # Session duration from timestamps
    duration = None
    if session.created_at and session.updated_at:
        delta = session.updated_at - session.created_at
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        duration = f"{minutes}m {seconds}s"

    return {
        "session_id": session_id,
        "status": session.status,
        "consensus_score": session.consensus_score,
        "consensus_trajectory": consensus_trajectory,
        "final_consensus_score": final_consensus,
        "total_rounds": len(rounds_data),
        "total_turns": len(turns_data),
        "session_duration": duration,
        "influence_leaderboard": influence_leaderboard,
        "risk_table": risk_table,
        "coalition_map": coalition_map,
        "rounds": rounds_data,
        "turns": turns_data,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_STAGES = {"agent_turn", "thinking", "moderator_intro", "moderator_challenge", "moderator_synthesis", "inject", "observer",
                "intro", "response", "challenge", "synthesis"}

def _persist_message(session_id: int, data: dict, user_id: str = None):
    stage = data.get("stage", "agent_turn")
    if stage not in VALID_STAGES:
        logger.warning("Unknown stage '%s' — defaulting to agent_turn", stage)
        stage = "agent_turn"

    def _do_persist():
        db = get_db_session_with_user(user_id)
        try:
            db.add(Message(
                session_id=session_id, turn=data.get("turn", 0),
                round_num=data.get("round", 0),  # CR-004: persist round for resume_from_db()
                stage=_stage_to_int(stage),
                speaker=data.get("speaker", ""), speaker_name=data.get("speaker_name", ""),
                content=data.get("content", ""),
                finish_reason=data.get("finish_reason"),
            ))
            db.commit()
        except Exception:
            db.rollback()  # #139: rollback on error to avoid leaking RLS context on pool reuse
            raise
        finally:
            db.close()

    try:
        _do_persist()
    except OperationalError as e:
        # Connection may have gone stale during a long LLM wait — retry once with a fresh session.
        logger.warning("_persist_message: OperationalError (stale connection?), retrying — %s", e)
        try:
            _do_persist()
        except Exception as e2:
            logger.error("_persist_message: retry failed: %s", e2)
    except Exception as e:
        logger.error("Failed to persist message: %s", e)


def _persist_analytics_snapshot(session_id: int, data: dict, user_id: str = None):
    """Persist an AnalyticsSnapshot row after each round."""

    def _do_persist():
        db = get_db_session_with_user(user_id)
        _run_analytics_persist(db, session_id, data)

    try:
        _do_persist()
    except OperationalError as e:
        # Connection may have gone stale during a long LLM wait — retry once with a fresh session.
        logger.warning("_persist_analytics_snapshot: OperationalError (stale connection?), retrying — %s", e)
        try:
            _do_persist()
        except Exception as e2:
            logger.error("_persist_analytics_snapshot: retry failed: %s", e2)
    except Exception as e:
        logger.error("Failed to persist analytics snapshot: %s", e)


def _run_analytics_persist(db, session_id: int, data: dict):
    """Core analytics persistence logic, separated so it can be retried with a fresh db session."""
    try:
        round_num = data.get("round", 0)

        # #188/#156: skip insert if this round already has a snapshot (idempotent persist)
        existing = db.query(AnalyticsSnapshot).filter_by(
            session_id=session_id, round=round_num
        ).first()
        if existing:
            logger.debug(
                "_run_analytics_persist: round %d already persisted for session %d — skipping",
                round_num, session_id
            )
            return
        observer_extractions = data.get("observer_extractions", [])

        # Compute aggregate sentiment data from observer extractions
        sentiment_data = {}
        for obs in observer_extractions:
            speaker = obs.get("speaker", "")
            if speaker and "sentiment" in obs:
                sentiment_data[speaker] = obs["sentiment"]

        # Consensus proxy from observer data
        # Observer emits sentiment.overall in [-1, 1]; normalize to [0, 1] for variance calc
        sentiments_overall = [
            s.get("overall", 0.0)
            for s in sentiment_data.values()
            if isinstance(s, dict) and "overall" in s
        ]
        consensus_score = None
        if len(sentiments_overall) >= 2:
            normalized = [(v + 1) / 2 for v in sentiments_overall]  # [-1,1] → [0,1]
            mean = sum(normalized) / len(normalized)
            variance = sum((v - mean) ** 2 for v in normalized) / len(normalized)
            # Max variance in [0,1] is 0.25, so ×4 maps full range to [0,1]
            consensus_score = max(0.0, min(1.0, 1.0 - variance * 4))

        # Build risk data from observer extractions.
        # Fields match AnalyticsDashboard.vue: name, score, level, drivers.
        risk_data = []
        for obs in observer_extractions:
            speaker = obs.get("speaker", "")
            sentiment = obs.get("sentiment", {})
            overall = sentiment.get("overall", 0.0) if isinstance(sentiment, dict) else 0.0
            # score: map [-1, 1] → [0, 1] (higher = more negative/risky sentiment)
            score = round((1.0 - overall) / 2.0, 3)
            if score >= 0.7:
                level = "HIGH"
            elif score >= 0.4:
                level = "MEDIUM"
            else:
                level = "LOW"
            fears = obs.get("fears_triggered", [])
            risk_data.append({
                "name": speaker,
                "score": score,
                "level": level,
                "drivers": fears,
            })

        # Build coalition data: group agents by sentiment polarity (simple heuristic)
        coalition_clusters = {"supportive": [], "opposing": [], "neutral": []}
        for speaker, sentiment in sentiment_data.items():
            if isinstance(sentiment, dict):
                overall = sentiment.get("overall", 0.0)
                if overall > 0.3:
                    coalition_clusters["supportive"].append(speaker)
                elif overall < -0.3:
                    coalition_clusters["opposing"].append(speaker)
                else:
                    coalition_clusters["neutral"].append(speaker)
        coalition_data = {
            "clusters": [
                {"label": label, "members": members}
                for label, members in coalition_clusters.items() if members
            ]
        }

        # Build influence data using a directed agreement/disagreement citation graph.
        # Fields match AnalyticsDashboard.vue: name, combined_score, eigenvector, betweenness.
        # #107: use networkx to compute real betweenness and eigenvector centrality from
        # observer agreement_with / disagreement_with signals instead of raw turns count.
        turns_spoken = data.get("turns_spoken", {})
        max_turns = max(turns_spoken.values(), default=1) or 1

        # Build directed citation graph: edge A→B means A cited B (agreed or disagreed)
        eigenvector_scores: dict = {}
        betweenness_scores: dict = {}
        if _NX_AVAILABLE and observer_extractions:
            G = nx.DiGraph()
            all_speakers = list(turns_spoken.keys())
            G.add_nodes_from(all_speakers)
            for obs in observer_extractions:
                src = obs.get("speaker", "")
                if not src:
                    continue
                signals = obs.get("behavioral_signals", {})
                agreed = signals.get("agreement_with", []) or []
                disagreed = signals.get("disagreement_with", []) or []
                for tgt in agreed:
                    if tgt in all_speakers:
                        if G.has_edge(src, tgt):
                            G[src][tgt]["weight"] += 1
                        else:
                            G.add_edge(src, tgt, weight=1)
                for tgt in disagreed:
                    if tgt in all_speakers:
                        if G.has_edge(src, tgt):
                            G[src][tgt]["weight"] += 1
                        else:
                            G.add_edge(src, tgt, weight=1)
            if G.number_of_edges() > 0:
                try:
                    # Betweenness: fraction of shortest paths through each node
                    bc = nx.betweenness_centrality(G, weight="weight", normalized=True)
                    betweenness_scores = {k: round(v, 4) for k, v in bc.items()}
                except Exception:  # pragma: no cover — fails on empty/degenerate graphs
                    bc = nx.degree_centrality(G)
                    betweenness_scores = {k: round(v, 4) for k, v in bc.items()}
                try:
                    # Eigenvector: recursive prestige score (citation by high-cited agents).
                    # #220: eigenvector_centrality_numpy fails on disconnected graphs
                    # (numpy LinAlgError or convergence failure). Fall back to degree_centrality.
                    ec = nx.eigenvector_centrality_numpy(G, weight="weight")
                    eigenvector_scores = {k: round(v, 4) for k, v in ec.items()}
                except Exception:  # #220: disconnected graph fallback
                    ec = nx.degree_centrality(G)
                    eigenvector_scores = {k: round(v, 4) for k, v in ec.items()}

        # Combine turns proxy with graph centrality for a blended score
        influence_data = [
            {
                "name": speaker,
                "combined_score": round(
                    0.4 * (count / max_turns)
                    + 0.3 * betweenness_scores.get(speaker, 0.0)
                    + 0.3 * eigenvector_scores.get(speaker, 0.0),
                    3,
                ),
                "turns": count,
                "eigenvector": eigenvector_scores.get(speaker),
                "betweenness": betweenness_scores.get(speaker),
            }
            for speaker, count in sorted(turns_spoken.items(), key=lambda x: -x[1])
        ]

        # Compute consensus_velocity (delta vs previous round) and polarization_index
        consensus_velocity = None
        polarization_index = None
        if consensus_score is not None:
            prior = (
                db.query(AnalyticsSnapshot)
                .filter_by(session_id=session_id)
                .order_by(AnalyticsSnapshot.round.desc())
                .first()
            )
            if prior and prior.consensus_score is not None:
                consensus_velocity = round(consensus_score - prior.consensus_score, 4)
            if len(sentiments_overall) >= 2:
                # Polarization = variance of normalized sentiments (0=full consensus, 0.25=max spread)
                normalized = [(v + 1) / 2 for v in sentiments_overall]
                mean = sum(normalized) / len(normalized)
                polarization_index = round(
                    sum((v - mean) ** 2 for v in normalized) / len(normalized), 4
                )

        snap = AnalyticsSnapshot(
            session_id=session_id,
            round=round_num,
            consensus_score=consensus_score,
            consensus_velocity=consensus_velocity,
            polarization_index=polarization_index,
            risk_scores=json.dumps(risk_data) if risk_data else None,
            coalition_data=json.dumps(coalition_data) if coalition_data["clusters"] else None,
            influence_data=json.dumps(influence_data) if influence_data else None,
        )
        db.add(snap)
        db.commit()
    except Exception:
        db.rollback()  # #139: rollback on error to avoid leaking RLS context on pool reuse
        raise
    finally:
        db.close()


def _save_checkpoint(session_id: int, engine: A2AEngine, db=None, close_db: bool = True):
    """Persist current engine checkpoint to the session DB row."""
    try:
        user_id = getattr(engine, 'user_id', None)
        own_db = db is None
        if own_db:
            db = get_db_session_with_user(user_id)
        session = db.query(Session).filter_by(id=session_id).first()
        if session:
            session.checkpoint = json.dumps(engine.get_checkpoint())
            db.commit()
        if own_db and close_db:
            db.close()
    except Exception as e:
        logger.error("Failed to save checkpoint for session %s: %s", session_id, e)


def _finalize_session(session_id: int, engine: A2AEngine, error: str = None):
    """Finalize a session: update status, persist analytics, copy consensus score.

    #183: Each write phase uses its own try/except so a connection failure in
    analytics persist does not prevent the critical status update from being saved.
    """
    user_id = getattr(engine, 'user_id', None)

    # --- Phase 1: Update session status (most critical) ---
    try:
        db = get_db_session_with_user(user_id)
        try:
            session = db.query(Session).filter_by(id=session_id).first()
            if session:
                is_paused = getattr(engine, '_paused', False) is True
                stop_requested = getattr(engine, '_stop_requested', False) is True
                current_round = getattr(engine, 'current_round', 0)
                num_rounds = getattr(engine, 'num_rounds', 0)
                if error:
                    session.status = "failed"
                    session.synthesis = f"[Session failed: {error[:500]}]"
                    try:
                        session.checkpoint = json.dumps(engine.get_checkpoint())
                    except Exception:
                        pass
                elif is_paused:
                    session.status = "paused"
                    try:
                        session.checkpoint = json.dumps(engine.get_checkpoint())
                    except Exception:
                        pass
                elif stop_requested and current_round < num_rounds:
                    session.status = "stopped"
                    try:
                        session.checkpoint = json.dumps(engine.get_checkpoint())
                    except Exception:
                        pass
                    if engine.round_syntheses:
                        session.synthesis = engine.round_syntheses[-1]
                else:
                    session.status = "complete"
                    session.checkpoint = None
                    if engine.round_syntheses:
                        session.synthesis = engine.round_syntheses[-1]
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error("Failed to update session status for session %s: %s", session_id, e)

    # --- Phase 2: Persist TurnAnalytics rows from observer_data ---
    try:
        if hasattr(engine, 'observer_data') and engine.observer_data:
            db = get_db_session_with_user(user_id)
            try:
                existing_turns = {
                    t.turn for t in db.query(TurnAnalytics).filter_by(session_id=session_id).all()
                }
                for obs in engine.observer_data:
                    turn_num = obs.get("turn", 0)
                    if turn_num in existing_turns:
                        continue
                    round_num = obs.get("round", 0)
                    speaker = obs.get("speaker", "")
                    position = obs.get("position_summary", "")
                    sentiment = obs.get("sentiment", {})
                    behavioral = obs.get("behavioral_signals", {})
                    claims = obs.get("claims", [])

                    db.add(TurnAnalytics(
                        session_id=session_id,
                        turn=turn_num,
                        round=round_num,
                        speaker=speaker,
                        position_summary=position,
                        sentiment_data=json.dumps(sentiment) if sentiment else None,
                        behavioral_signals=json.dumps(behavioral) if behavioral else None,
                        claims=json.dumps(claims) if claims else None,
                    ))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
    except Exception as e:
        logger.error("Failed to persist TurnAnalytics for session %s: %s", session_id, e)

    # --- Phase 3: Persist missing AnalyticsSnapshot rows ---
    try:
        if hasattr(engine, 'observer_data') and engine.observer_data:
            db = get_db_session_with_user(user_id)
            try:
                existing_snaps = db.query(AnalyticsSnapshot).filter_by(session_id=session_id).all()
                persisted_rounds = {s.round for s in existing_snaps}
                all_rounds = {o.get("round") for o in engine.observer_data if o.get("round")}
                for rnd in sorted(all_rounds - persisted_rounds):
                    round_data = {
                        "round": rnd,
                        "observer_extractions": [o for o in engine.observer_data if o.get("round") == rnd],
                        "turns_spoken": dict(engine.turns_spoken),
                    }
                    _persist_analytics_snapshot(session_id, round_data, user_id=user_id)
            finally:
                db.close()
    except Exception as e:
        logger.error("Failed to persist AnalyticsSnapshot for session %s: %s", session_id, e)

    # --- Phase 4: Copy consensus_score from last snapshot to session record ---
    try:
        db = get_db_session_with_user(user_id)
        try:
            session = db.query(Session).filter_by(id=session_id).first()
            if session:
                last_snap = db.query(AnalyticsSnapshot).filter_by(session_id=session_id)\
                    .order_by(AnalyticsSnapshot.round.desc()).first()
                if last_snap and last_snap.consensus_score is not None:
                    session.consensus_score = last_snap.consensus_score
                    db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error("Failed to copy consensus_score for session %s: %s", session_id, e)

_MAX_PRIOR_SESSIONS = 5          # #187: only include most recent N sessions
_MAX_PRIOR_CONTEXT_CHARS = 4000  # #187: cap total chars (~1000 tokens)
_MAX_SYNTHESIS_CHARS = 500       # #187: truncate each synthesis to this length


def _build_prior_session_context(project_id: int, current_session_id: int, db: DBSession) -> Optional[str]:
    """
    Query completed sessions on the same project and collect their final
    moderator syntheses to pass as cross-session context (Task 3).

    #187: Capped to the most recent MAX_PRIOR_SESSIONS sessions and
    MAX_PRIOR_CONTEXT_CHARS total characters to avoid overflowing the LLM context window.
    """
    prior_sessions = (
        db.query(Session)
        .filter(
            Session.project_id == project_id,
            Session.status == "complete",
            Session.id != current_session_id,
        )
        .order_by(Session.id.desc())  # most recent first
        .limit(_MAX_PRIOR_SESSIONS)
        .all()
    )

    if not prior_sessions:
        return None

    session_ids = [s.id for s in prior_sessions]

    # Single query: per-session synthesis (last moderator synthesis message)
    synth_rows = (
        db.query(Message.session_id, Message.content, Message.turn)
        .filter(
            Message.session_id.in_(session_ids),
            Message.stage == 3,
            Message.speaker == "moderator",
        )
        .order_by(Message.session_id, Message.turn.desc())
        .all()
    )
    # Keep only the last synthesis per session and count rounds
    seen: dict[int, str] = {}
    round_counts: dict[int, int] = {}
    for sid, content, turn in synth_rows:
        if sid not in seen:
            seen[sid] = content
        round_counts[sid] = round_counts.get(sid, 0) + 1

    lines = []
    total_chars = 0
    for sid in session_ids:  # already ordered most-recent-first
        if sid not in seen:
            continue
        synthesis = seen[sid][:_MAX_SYNTHESIS_CHARS]
        line = f"Session {sid} (round {round_counts[sid]}): {synthesis}"
        if total_chars + len(line) > _MAX_PRIOR_CONTEXT_CHARS:
            break
        lines.append(line)
        total_chars += len(line)

    return "\n\n".join(reversed(lines)) if lines else None



# ---------------------------------------------------------------------------
# Agenda endpoint (CR-006)
# ---------------------------------------------------------------------------

@router.get("/{session_id}/agenda")
def get_session_agenda(session_id: int, db: DBSession = Depends(get_db_with_rls)):
    """Return agenda items and current vote state for a session."""
    items = (
        db.query(SessionAgenda)
        .filter_by(session_id=session_id)
        .order_by(SessionAgenda.id)
        .all()
    )
    if not items:
        return {"items": []}

    all_votes = (
        db.query(AgendaVote)
        .filter_by(session_id=session_id)
        .order_by(AgendaVote.turn)
        .all()
    )

    # Latest vote per speaker per item: {item_key: {speaker_slug: {stance, confidence, turn}}}
    latest: dict[str, dict[str, dict]] = {}
    for v in all_votes:
        latest.setdefault(v.item_key, {})[v.speaker_slug] = {
            "stance": v.stance,
            "confidence": v.confidence,
            "turn": v.turn,
        }

    result = []
    for item in items:
        item_votes = latest.get(item.item_key, {})
        tally: dict[str, int] = {"agree": 0, "oppose": 0, "neutral": 0, "abstain": 0}
        for v in item_votes.values():
            tally[v["stance"]] = tally.get(v["stance"], 0) + 1
        result.append({
            "key": item.item_key,
            "label": item.label,
            "description": item.description,
            "votes": item_votes,
            "tally": tally,
        })

    return {"items": result}


@router.get("/{session_id}/voting-summary")
def get_voting_summary(session_id: int, db: DBSession = Depends(get_db_with_rls)):
    """Per-agenda-item stance history and convergence trend.

    Returns:
      items: list of {
        key, label,
        agents: { slug: [{ round, stance, confidence }] },   # history per agent
        tally_by_round: { round: { agree, oppose, neutral, abstain } },
        consensus_trend: "converging" | "diverging" | "stable" | "no_data"
      }
    """
    items = (
        db.query(SessionAgenda)
        .filter_by(session_id=session_id)
        .order_by(SessionAgenda.id)
        .all()
    )
    if not items:
        return {"items": []}

    all_votes = (
        db.query(AgendaVote)
        .filter_by(session_id=session_id)
        .order_by(AgendaVote.round, AgendaVote.turn)
        .all()
    )

    # Group votes: item_key → agent_slug → [(round, stance, confidence)]
    history: dict[str, dict[str, list]] = {}
    for v in all_votes:
        history.setdefault(v.item_key, {}).setdefault(v.speaker_slug, []).append({
            "round": v.round,
            "stance": v.stance,
            "confidence": v.confidence,
        })

    # Tally per round: item_key → round → {agree, oppose, neutral, abstain}
    tally_by_round: dict[str, dict[int, dict]] = {}
    for v in all_votes:
        tally_by_round.setdefault(v.item_key, {}).setdefault(
            v.round, {"agree": 0, "oppose": 0, "neutral": 0, "abstain": 0}
        )
        tally_by_round[v.item_key][v.round][v.stance] = (
            tally_by_round[v.item_key][v.round].get(v.stance, 0) + 1
        )

    def _consensus_trend(rounds_tally: dict[int, dict]) -> str:
        """Determine if the room is converging, diverging, or stable."""
        if len(rounds_tally) < 2:
            return "no_data"
        sorted_rounds = sorted(rounds_tally.keys())
        scores = []
        for r in sorted_rounds:
            t = rounds_tally[r]
            total = sum(t.values()) or 1
            agree_frac = t.get("agree", 0) / total
            scores.append(agree_frac)
        # Simple linear trend: compare first half vs second half
        mid = len(scores) // 2
        first_avg = sum(scores[:mid]) / max(mid, 1)
        second_avg = sum(scores[mid:]) / max(len(scores) - mid, 1)
        delta = second_avg - first_avg
        if abs(delta) < 0.05:
            return "stable"
        return "converging" if delta > 0 else "diverging"

    result = []
    for item in items:
        agents_history = history.get(item.item_key, {})
        rounds_tally = tally_by_round.get(item.item_key, {})
        result.append({
            "key": item.item_key,
            "label": item.label,
            "description": item.description,
            "agents": agents_history,
            "tally_by_round": {str(k): v for k, v in sorted(rounds_tally.items())},
            "consensus_trend": _consensus_trend(rounds_tally),
        })

    return {"items": result}


# ---------------------------------------------------------------------------
# CR-011 — Private Threads (Whisper Channels) endpoints
# ---------------------------------------------------------------------------

@router.get("/{session_id}/private-threads")
def get_private_threads(session_id: int, db: DBSession = Depends(get_db_with_rls)):
    """Return all private threads for a session (overseer view)."""
    session = db.query(Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    threads = (
        db.query(PrivateThread)
        .filter_by(session_id=session_id)
        .order_by(PrivateThread.created_at)
        .all()
    )

    result = []
    for t in threads:
        msgs = [
            {
                "id": m.id,
                "speaker_slug": m.speaker_slug,
                "content": m.content,
                "round_num": m.round_num,
                "turn": m.turn,
                "created_at": m.created_at.isoformat(),
            }
            for m in sorted(t.messages, key=lambda x: x.created_at)
        ]
        result.append({
            "id": t.id,
            "initiator_slug": t.initiator_slug,
            "target_slug": t.target_slug,
            "round_opened": t.round_opened,
            "status": t.status,
            "created_at": t.created_at.isoformat(),
            "messages": msgs,
        })

    return {"threads": result}
