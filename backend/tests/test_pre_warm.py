"""
Tests for session pre-warming feature.

Covers:
  - pre_warm module: trigger_pre_warm, invalidate_pre_warm, get_pre_warm_data
  - GET /api/sessions/{id}/pre-warm-status endpoint
  - Engine run() using pre-warmed agenda and moderator opening (skips LLM calls)
  - Invalidation when moderator_style differs at run time
  - Idempotency (pre-warm with existing agenda rows)
  - Race: pre-warm still warming when run() starts → engine falls back gracefully
"""

import asyncio
import json
import os
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Environment bootstrap (must happen before backend imports)
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:9999")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_DEFAULT_MODEL", "gpt-4o-mini")
os.environ.setdefault("LLM_CHAIRMAN_MODEL", "gpt-4o-mini")
os.environ.setdefault("SUPABASE_URL", "http://localhost:9999")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-minimum-32-chars-here")

from backend.main import app  # noqa: E402
from backend.database import Base, get_db  # noqa: E402
from backend import models  # noqa: E402, F401
from backend.routers import sessions as _sessions_router  # noqa: E402
from backend.a2a import pre_warm as pre_warm_module  # noqa: E402
from backend.auth import get_current_user, require_user  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_test_engine_ref = None  # module-level handle for the SQLAlchemy engine
_test_session_factory = None  # module-level sessionmaker for pre_warm patching


@pytest.fixture(autouse=True)
def override_db():
    """
    Fresh in-memory SQLite for every test.

    Also patches pre_warm._get_db_session so the pre_warm module's DB helpers
    use the same in-memory SQLite rather than the global production SessionLocal.
    """
    global _test_engine_ref, _test_session_factory
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    _test_engine_ref = eng
    _test_session_factory = TestSession

    def _get_test_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def _test_get_db_session(user_id=None):
        """Override for pre_warm._get_db_session — returns test DB session."""
        return TestSession()

    _TEST_USER = {"sub": "00000000-0000-0000-0000-000000000001", "email": "test@example.com"}
    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[require_user] = lambda: _TEST_USER

    # Patch pre_warm's DB session factory to use the test DB
    original_get_db_session = pre_warm_module._get_db_session
    pre_warm_module._get_db_session = _test_get_db_session

    yield

    pre_warm_module._get_db_session = original_get_db_session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(eng)
    eng.dispose()
    _sessions_router._running_engines.clear()


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_project_and_session(client):
    """Create a project with one stakeholder and a session. Returns (project, session)."""
    pr = await client.post(
        "/api/projects/",
        json={"name": "PreWarmProject", "description": "Test"},
    )
    assert pr.status_code == 201, pr.text
    project = pr.json()

    # Add a stakeholder (note: no trailing slash on stakeholders endpoint)
    sk = await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={
            "slug": "alice",
            "name": "Alice",
            "role": "CTO",
            "attitude": "enthusiast",
            "influence": 0.8,
            "interest": 0.9,
        },
    )
    assert sk.status_code == 201, sk.text

    # Add LLM settings
    await client.post(
        "/api/settings/",
        json={
            "profile_name": "default",
            "base_url": "http://example-llm.test",
            "api_key": "key",
            "default_model": "gpt-4o-mini",
            "chairman_model": "gpt-4o-mini",
            "council_models": ["gpt-4o-mini"],
        },
    )

    # Create session — triggers pre-warm background task (mocked below)
    sr = await client.post(
        "/api/sessions/",
        json={"project_id": project["id"], "question": "Should we adopt AI?"},
    )
    assert sr.status_code == 201, sr.text
    session = sr.json()
    return project, session


# ---------------------------------------------------------------------------
# Tests: pre-warm status endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_warm_status_endpoint_returns_null_when_no_llm(client):
    """
    When no LLM settings exist, session is created normally and pre_warm_status is null.
    """
    pr = await client.post(
        "/api/projects/",
        json={"name": "NullLLMProject", "description": ""},
    )
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "bob", "name": "Bob", "role": "PM", "attitude": "neutral"},
    )

    # Do NOT create LLM settings — pre-warm should be skipped silently
    sr = await client.post(
        "/api/sessions/",
        json={"project_id": project["id"], "question": "Should we adopt AI?"},
    )
    assert sr.status_code == 201

    session_id = sr.json()["id"]
    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session_id
    assert body["pre_warm_status"] is None
    assert body["has_agenda"] is False
    assert body["has_moderator_opening"] is False


@pytest.mark.asyncio
async def test_pre_warm_status_endpoint_404_unknown_session(client):
    r = await client.get("/api/sessions/99999/pre-warm-status")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests: pre_warm module internals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_pre_warm_data_returns_none_for_nonexistent_session():
    """get_pre_warm_data should return None gracefully when session doesn't exist."""
    result = pre_warm_module.get_pre_warm_data(session_id=999999)
    assert result is None


@pytest.mark.asyncio
async def test_invalidate_pre_warm_noop_for_nonexistent_session():
    """invalidate_pre_warm should not raise for a nonexistent session."""
    pre_warm_module.invalidate_pre_warm(session_id=999999)  # must not raise


@pytest.mark.asyncio
async def test_extract_agenda_returns_items_on_success():
    """_extract_agenda returns correctly shaped items when LLM returns valid JSON."""
    mock_json = {
        "items": [
            {"key": "item_1", "label": "Should we proceed?", "description": "Core question"},
            {"key": "item_2", "label": "Timeline acceptable?", "description": "6-month window"},
        ]
    }
    with patch(
        "backend.a2a.pre_warm.get_completion_json",
        new_callable=AsyncMock,
        return_value=mock_json,
    ):
        items = await pre_warm_module._extract_agenda(
            question="Should we adopt AI?",
            llm_base_url="http://test",
            llm_api_key="key",
            chairman_model="gpt-4o-mini",
        )
    assert len(items) == 2
    assert items[0]["key"] == "item_1"
    assert items[0]["label"] == "Should we proceed?"
    assert items[0]["description"] == "Core question"


@pytest.mark.asyncio
async def test_extract_agenda_returns_empty_on_llm_failure():
    """_extract_agenda returns [] gracefully if the LLM call raises."""
    with patch(
        "backend.a2a.pre_warm.get_completion_json",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM unavailable"),
    ):
        items = await pre_warm_module._extract_agenda(
            question="Should we adopt AI?",
            llm_base_url="http://test",
            llm_api_key="key",
            chairman_model="gpt-4o-mini",
        )
    assert items == []


@pytest.mark.asyncio
async def test_generate_moderator_opening_returns_string():
    """_generate_moderator_opening returns the LLM content string."""
    with patch(
        "backend.a2a.pre_warm.get_completion_content",
        new_callable=AsyncMock,
        return_value="Welcome to the wargame! Today we debate AI adoption.",
    ):
        opening = await pre_warm_module._generate_moderator_opening(
            question="Should we adopt AI?",
            stakeholders=[{"name": "Alice", "role": "CTO", "influence": 0.8, "attitude_label": "Enthusiast"}],
            llm_base_url="http://test",
            llm_api_key="key",
            chairman_model="gpt-4o-mini",
            moderator_style="neutral",
            moderator_name="Moderator",
            moderator_title="",
            moderator_mandate="",
            moderator_persona_prompt="",
        )
    assert "wargame" in opening


@pytest.mark.asyncio
async def test_generate_moderator_opening_returns_empty_on_failure():
    """_generate_moderator_opening returns '' gracefully if the LLM call raises."""
    with patch(
        "backend.a2a.pre_warm.get_completion_content",
        new_callable=AsyncMock,
        side_effect=Exception("Network error"),
    ):
        opening = await pre_warm_module._generate_moderator_opening(
            question="Should we adopt AI?",
            stakeholders=[],
            llm_base_url="http://test",
            llm_api_key="key",
            chairman_model="gpt-4o-mini",
            moderator_style="neutral",
            moderator_name="Moderator",
            moderator_title="",
            moderator_mandate="",
            moderator_persona_prompt="",
        )
    assert opening == ""


# ---------------------------------------------------------------------------
# Tests: _run_pre_warm (full background task integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_pre_warm_writes_status_ready(client):
    """
    _run_pre_warm sets pre_warm_status='ready' and stores agenda + opening in the DB.
    """
    # Create project + stakeholder + session via API
    pr = await client.post("/api/projects/", json={"name": "PWTest", "description": ""})
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "carol", "name": "Carol", "role": "CFO", "attitude": "critical"},
    )
    await client.post(
        "/api/settings/",
        json={
            "profile_name": "pw-profile",
            "base_url": "http://test-llm",
            "api_key": "k",
            "default_model": "gpt-4o",
            "chairman_model": "gpt-4o",
            "council_models": ["gpt-4o"],
        },
    )
    # Patch trigger_pre_warm so session creation doesn't fire an uncontrolled task
    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Is AI safe?"},
        )
    session_id = sr.json()["id"]

    # Now run _run_pre_warm directly with mocked LLM
    agenda_mock = {"items": [{"key": "item_1", "label": "Is it safe?", "description": "Safety question"}]}
    opening_mock = "Welcome to the AI safety debate."

    with (
        patch("backend.a2a.pre_warm.get_completion_json", new_callable=AsyncMock, return_value=agenda_mock),
        patch("backend.a2a.pre_warm.get_completion_content", new_callable=AsyncMock, return_value=opening_mock),
    ):
        await pre_warm_module._run_pre_warm(
            session_id=session_id,
            question="Is AI safe?",
            stakeholders=[{"name": "Carol", "role": "CFO", "influence": 0.5, "attitude_label": "Critical"}],
            project={"name": "PWTest", "organization": "", "context": "", "description": ""},
            llm_base_url="http://test-llm",
            llm_api_key="k",
            chairman_model="gpt-4o",
            moderator_style="neutral",
            moderator_name="Moderator",
            moderator_title="",
            moderator_mandate="",
            moderator_persona_prompt="",
            user_id=None,
        )

    # Verify status endpoint reflects "ready"
    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    assert r.status_code == 200
    body = r.json()
    assert body["pre_warm_status"] == "ready"
    assert body["has_agenda"] is True
    assert body["has_moderator_opening"] is True
    assert body["warmed_at"] is not None


@pytest.mark.asyncio
async def test_run_pre_warm_resets_status_on_catastrophic_failure(client):
    """
    When _run_pre_warm encounters an unhandled exception (e.g. from _extract_agenda
    raising unexpectedly outside its own try/except), status is reset to null.
    We simulate this by patching _extract_agenda itself to raise.
    """
    pr = await client.post("/api/projects/", json={"name": "FailTest", "description": ""})
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "dave", "name": "Dave", "role": "COO", "attitude": "neutral"},
    )

    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Is AI safe?"},
        )
    session_id = sr.json()["id"]

    # Patch _extract_agenda to raise directly — bypasses its internal exception handler
    async def _raise_extract(*args, **kwargs):
        raise RuntimeError("catastrophic failure — not caught by inner try/except")

    with patch.object(pre_warm_module, "_extract_agenda", side_effect=_raise_extract):
        await pre_warm_module._run_pre_warm(
            session_id=session_id,
            question="Is AI safe?",
            stakeholders=[],
            project={},
            llm_base_url="http://fail-llm",
            llm_api_key="k",
            chairman_model="gpt-4o",
            moderator_style="neutral",
            moderator_name="Moderator",
            moderator_title="",
            moderator_mandate="",
            moderator_persona_prompt="",
            user_id=None,
        )

    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    body = r.json()
    # Status should be null (reset after unhandled failure)
    assert body["pre_warm_status"] is None


@pytest.mark.asyncio
async def test_run_pre_warm_still_ready_with_empty_agenda_on_soft_llm_failure(client):
    """
    When the LLM fails inside _extract_agenda (caught internally → returns []),
    _run_pre_warm still writes status='ready' with empty agenda.
    This is a soft failure — the engine will re-extract at start time.
    """
    pr = await client.post("/api/projects/", json={"name": "SoftFailTest", "description": ""})
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "grace", "name": "Grace", "role": "CTO", "attitude": "neutral"},
    )

    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Is AI safe?"},
        )
    session_id = sr.json()["id"]

    # Both LLM helpers return soft-failure defaults (empty results, no exception)
    with (
        patch("backend.a2a.pre_warm.get_completion_json", new_callable=AsyncMock, return_value={"items": []}),
        patch("backend.a2a.pre_warm.get_completion_content", new_callable=AsyncMock, return_value=""),
    ):
        await pre_warm_module._run_pre_warm(
            session_id=session_id,
            question="Is AI safe?",
            stakeholders=[],
            project={},
            llm_base_url="http://fail-llm",
            llm_api_key="k",
            chairman_model="gpt-4o",
            moderator_style="neutral",
            moderator_name="Moderator",
            moderator_title="",
            moderator_mandate="",
            moderator_persona_prompt="",
            user_id=None,
        )

    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    body = r.json()
    # Soft failure still writes "ready" but with empty content
    assert body["pre_warm_status"] == "ready"
    assert body["has_agenda"] is False
    assert body["has_moderator_opening"] is False


# ---------------------------------------------------------------------------
# Tests: Engine integration — pre-warmed agenda / opening used in run()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_uses_prewarmed_agenda_skips_extract():
    """
    When _pre_warmed_agenda is set on the engine, run() uses it directly and
    does NOT call _extract_agenda.
    """
    from backend.a2a.engine import A2AEngine

    stakeholders = [{"slug": "alice", "name": "Alice", "role": "CTO",
                     "attitude": "enthusiast", "attitude_label": "Enthusiast",
                     "influence": 0.8, "interest": 0.9,
                     "needs": "[]", "fears": "[]", "adkar": "{}", "preconditions": "[]",
                     "quote": "", "signal_cle": "", "color": "#fff", "llm_model": None,
                     "system_prompt": None, "hard_constraints": "[]",
                     "key_concerns": "[]", "cognitive_biases": "[]", "batna": "",
                     "anti_sycophancy": "", "grounding_quotes": "[]",
                     "communication_style": "", "success_criteria": "[]"}]

    engine = A2AEngine(
        session_id=1,
        question="Should we adopt AI?",
        stakeholders=stakeholders,
        project={"name": "Test", "organization": "Org", "context": "", "description": ""},
        llm_base_url="http://test",
        llm_api_key="key",
        default_model="gpt-4o",
        chairman_model="gpt-4o",
        num_rounds=1,
        agents_per_turn=1,
    )

    pre_warmed_agenda = [{"key": "item_1", "label": "Should we proceed?", "description": ""}]
    engine._pre_warmed_agenda = pre_warmed_agenda
    engine._pre_warmed_moderator_opening = "Welcome to the debate!"

    extract_called = []

    async def mock_extract():
        extract_called.append(True)
        return [{"key": "item_2", "label": "Fresh extract", "description": ""}]

    # Patch _persist_agenda, _extract_agenda, and the agent turn machinery
    async def mock_persist(items):
        pass

    engine._extract_agenda = mock_extract
    engine._persist_agenda = mock_persist

    # Collect all events; stop after agenda_init + moderator turn
    events = []
    with (
        patch("backend.a2a.engine.moderator_intro", new_callable=AsyncMock,
              return_value="LLM moderator intro"),
        patch("backend.a2a.engine.extract_turn_data", new_callable=AsyncMock,
              return_value={"sentiment": {}, "agenda_votes": {}}),
        patch("backend.a2a.engine.stream_completion_with_thinking") as mock_stream,
        patch("backend.a2a.engine.chat_completion", new_callable=AsyncMock,
              return_value={"choices": [{"message": {"role": "assistant", "content": "Agent response"}, "finish_reason": "stop"}]}),
    ):
        async def fake_stream(*args, **kwargs):
            yield {"type": "content_token", "delta": "Hello"}
            yield {"type": "done", "thinking": "", "content": "Hello world"}
        mock_stream.return_value = fake_stream()

        try:
            async for event in engine.run():
                events.append(event)
                if len(events) >= 5:
                    engine.request_stop()
                    break
        except Exception:
            pass

    # Agenda extraction was NOT called — pre-warm was used instead
    assert not extract_called, "Expected _extract_agenda to be skipped when pre-warmed agenda is present"

    # agenda_init event should carry the pre-warmed items
    agenda_events = [e for e in events if e.get("event") == "agenda_init"]
    assert agenda_events, "Expected at least one agenda_init event"
    assert agenda_events[0]["data"]["items"] == pre_warmed_agenda


@pytest.mark.asyncio
async def test_engine_uses_prewarmed_moderator_opening_skips_llm():
    """
    When _pre_warmed_moderator_opening is set, round 1 moderator intro uses it
    without calling moderator_intro LLM function.
    """
    from backend.a2a.engine import A2AEngine

    stakeholders = [{"slug": "alice", "name": "Alice", "role": "CTO",
                     "attitude": "enthusiast", "attitude_label": "Enthusiast",
                     "influence": 0.8, "interest": 0.9,
                     "needs": "[]", "fears": "[]", "adkar": "{}", "preconditions": "[]",
                     "quote": "", "signal_cle": "", "color": "#fff", "llm_model": None,
                     "system_prompt": None, "hard_constraints": "[]",
                     "key_concerns": "[]", "cognitive_biases": "[]", "batna": "",
                     "anti_sycophancy": "", "grounding_quotes": "[]",
                     "communication_style": "", "success_criteria": "[]"}]

    engine = A2AEngine(
        session_id=2,
        question="Should we adopt AI?",
        stakeholders=stakeholders,
        project={"name": "Test", "organization": "Org", "context": "", "description": ""},
        llm_base_url="http://test",
        llm_api_key="key",
        default_model="gpt-4o",
        chairman_model="gpt-4o",
        num_rounds=1,
        agents_per_turn=1,
    )
    engine._pre_warmed_agenda = [{"key": "item_1", "label": "Core question", "description": ""}]
    engine._pre_warmed_moderator_opening = "PRE_WARMED_OPENING_CONTENT"

    async def mock_persist(items):
        pass

    engine._persist_agenda = mock_persist

    moderator_intro_called = []

    async def fake_moderator_intro(*args, **kwargs):
        moderator_intro_called.append(True)
        return "LLM fresh intro"

    events = []
    with (
        patch("backend.a2a.engine.moderator_intro", side_effect=fake_moderator_intro),
        patch("backend.a2a.engine.extract_turn_data", new_callable=AsyncMock,
              return_value={"sentiment": {}, "agenda_votes": {}}),
        patch("backend.a2a.engine.stream_completion_with_thinking") as mock_stream,
        patch("backend.a2a.engine.chat_completion", new_callable=AsyncMock,
              return_value={"choices": [{"message": {"role": "assistant", "content": "Agent"}, "finish_reason": "stop"}]}),
    ):
        async def fake_stream(*args, **kwargs):
            yield {"type": "content_token", "delta": "x"}
            yield {"type": "done", "thinking": "", "content": "x"}
        mock_stream.return_value = fake_stream()

        try:
            async for event in engine.run():
                events.append(event)
                # Stop after collecting the moderator turn_end (or at most 10 events)
                if len(events) >= 10:
                    engine.request_stop()
                    break
                if event.get("event") in ("turn", "turn_end") and event.get("data", {}).get("speaker") == "moderator":
                    engine.request_stop()
                    break
        except Exception:
            pass

    # moderator_intro LLM function was NOT called — pre-warm was used
    assert not moderator_intro_called, "Expected moderator_intro LLM to be skipped when pre-warm opening is present"

    # The moderator turn_end event should contain the pre-warmed content
    # (#114: moderator turns now use "turn_end" event name for consistency)
    turn_events = [e for e in events if e.get("event") in ("turn", "turn_end") and
                   e.get("data", {}).get("speaker") == "moderator"]
    assert turn_events, "Expected a moderator turn_end event"
    assert "PRE_WARMED_OPENING_CONTENT" in turn_events[0]["data"]["content"]


# ---------------------------------------------------------------------------
# Tests: Invalidation on moderator_style mismatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_session_discards_prewarmed_data_on_style_mismatch(client):
    """
    When run_session is called with a different moderator_style than what was
    pre-warmed with, the pre-warm data is discarded and invalidated.
    """
    pr = await client.post("/api/projects/", json={"name": "StyleTest", "description": ""})
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "eve", "name": "Eve", "role": "CEO", "attitude": "enthusiast",
              "influence": 0.9, "interest": 0.9},
    )
    await client.post(
        "/api/settings/",
        json={
            "profile_name": "style-profile",
            "base_url": "http://test-llm",
            "api_key": "k",
            "default_model": "gpt-4o",
            "chairman_model": "gpt-4o",
            "council_models": ["gpt-4o"],
        },
    )

    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Should we proceed?"},
        )
    session_id = sr.json()["id"]

    # Simulate a pre-warm that was done with "neutral" style
    warm_payload = {
        "agenda": [{"key": "item_1", "label": "Core Q", "description": ""}],
        "moderator_opening": "Neutral opening text",
        "warmed_at": "2026-01-01T00:00:00",
        "moderator_style": "neutral",
    }
    from backend.a2a.pre_warm import _store_warm_data
    _store_warm_data(session_id=session_id, data=warm_payload, user_id=None)

    # Verify it's ready
    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    assert r.json()["pre_warm_status"] == "ready"

    # Now run with a different moderator_style — cache should be discarded
    with patch("backend.a2a.engine.A2AEngine.run") as mock_run:
        # Return a minimal generator so the endpoint doesn't actually stream
        async def _no_events():
            return
            yield  # make it an async generator

        mock_run.return_value = _no_events()

        run_r = await client.post(
            f"/api/sessions/{session_id}/run",
            json={
                "num_rounds": 1,
                "moderator_style": "challenging",  # different from "neutral"
                "agents_per_turn": 1,
            },
        )
        assert run_r.status_code == 200

    # Engine in _running_engines should NOT have pre-warmed opening set
    engine = _sessions_router._running_engines.get(session_id)
    if engine:
        assert not engine._pre_warmed_moderator_opening, (
            "Pre-warmed opening should have been discarded due to style mismatch"
        )
        assert not engine._pre_warmed_agenda, (
            "Pre-warmed agenda should have been discarded due to style mismatch"
        )


# ---------------------------------------------------------------------------
# Tests: Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_agenda_items_is_idempotent(client):
    """
    Calling _persist_agenda_items twice with the same session_id does not duplicate rows.
    """
    pr = await client.post("/api/projects/", json={"name": "IdemTest", "description": ""})
    project = pr.json()
    await client.post(
        f"/api/projects/{project['id']}/stakeholders",
        json={"slug": "frank", "name": "Frank", "role": "VP", "attitude": "neutral"},
    )
    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Is this safe?"},
        )
    session_id = sr.json()["id"]

    items = [{"key": "item_1", "label": "Safety?", "description": "Core"}]

    # Call twice — second call should be a no-op (existing rows detected)
    await pre_warm_module._persist_agenda_items(session_id=session_id, items=items, user_id=None)
    await pre_warm_module._persist_agenda_items(session_id=session_id, items=items, user_id=None)

    # Verify no duplicates via the test DB
    from backend.models import SessionAgenda
    db = _test_session_factory()
    try:
        count = db.query(SessionAgenda).filter_by(session_id=session_id).count()
        assert count == 1, f"Expected 1 agenda row, got {count}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: trigger_pre_warm schedules a task without blocking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_pre_warm_is_nonblocking():
    """
    trigger_pre_warm schedules a background task (asyncio.create_task) and
    returns immediately — it must not await the LLM calls itself.
    """
    task_created = []

    original_create_task = asyncio.create_task

    def mock_create_task(coro, **kwargs):
        task_created.append(True)
        # Cancel the coro to avoid unresolved futures leaking in tests
        task = original_create_task(coro, **kwargs)
        task.cancel()
        return task

    with patch("backend.a2a.pre_warm.asyncio.create_task", side_effect=mock_create_task):
        await pre_warm_module.trigger_pre_warm(
            session_id=1,
            question="Test?",
            stakeholders=[],
            project={},
            llm_base_url="http://test",
            llm_api_key="key",
            chairman_model="gpt-4o",
        )

    assert task_created, "Expected asyncio.create_task to be called"


# ---------------------------------------------------------------------------
# Tests: get_pre_warm_data status checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_pre_warm_data_returns_none_when_status_not_ready(client):
    """get_pre_warm_data returns None unless pre_warm_status == 'ready'."""
    pr = await client.post("/api/projects/", json={"name": "StatusTest", "description": ""})
    project = pr.json()
    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Q?"},
        )
    session_id = sr.json()["id"]

    # Status is null — should return None
    result = pre_warm_module.get_pre_warm_data(session_id=session_id)
    assert result is None

    # Set to "warming" — should still return None
    pre_warm_module._set_warm_status(session_id=session_id, status="warming", user_id=None)
    result = pre_warm_module.get_pre_warm_data(session_id=session_id)
    assert result is None

    # Set to "ready" with data — should return dict
    warm = {"agenda": [{"key": "item_1", "label": "Q1", "description": ""}],
            "moderator_opening": "Hello", "warmed_at": "2026-01-01T00:00:00", "moderator_style": "neutral"}
    pre_warm_module._store_warm_data(session_id=session_id, data=warm, user_id=None)
    result = pre_warm_module.get_pre_warm_data(session_id=session_id)
    assert result is not None
    assert result["agenda"][0]["label"] == "Q1"


@pytest.mark.asyncio
async def test_store_warm_data_noop_when_invalidated(client):
    """
    _store_warm_data should not overwrite status when session was invalidated
    while pre-warm was in progress.
    """
    pr = await client.post("/api/projects/", json={"name": "RaceTest", "description": ""})
    project = pr.json()
    with patch("backend.routers.sessions.trigger_pre_warm", new_callable=AsyncMock):
        sr = await client.post(
            "/api/sessions/",
            json={"project_id": project["id"], "question": "Q?"},
        )
    session_id = sr.json()["id"]

    # Simulate: pre-warm started then was invalidated (config change)
    pre_warm_module._set_warm_status(session_id=session_id, status="warming", user_id=None)
    pre_warm_module.invalidate_pre_warm(session_id=session_id)

    # Now _store_warm_data is called (would have been next step in background task)
    warm = {"agenda": [], "moderator_opening": "Should not be stored",
            "warmed_at": "2026-01-01T00:00:00", "moderator_style": "neutral"}
    pre_warm_module._store_warm_data(session_id=session_id, data=warm, user_id=None)

    # Status should remain "invalidated", not "ready"
    result = pre_warm_module.get_pre_warm_data(session_id=session_id)
    assert result is None

    r = await client.get(f"/api/sessions/{session_id}/pre-warm-status")
    assert r.json()["pre_warm_status"] == "invalidated"
