"""
Mock LLM adapter for engine integration tests.

Patches all LLM call sites in the engine at the module level so
engine.run() can be executed in pytest without a live LLM endpoint.
"""
import pytest
from unittest.mock import AsyncMock, patch

# Deterministic responses keyed by agent_name (for chat_completion)
DEFAULT_AGENT_RESPONSES = {
    "default": "I support this initiative with measured optimism.",
}

# Minimal valid observer payload (mirrors what observer.py expects from LLM)
MOCK_OBSERVER_RESPONSE = {
    "position_summary": "Supportive",
    "sentiment": {"overall": 0.5, "anxiety": 0.2, "trust": 0.7, "aggression": 0.1, "compliance": 0.6},
    "behavioral_signals": {"agreement_with": [], "disagreement_with": [], "hedging": False, "deflecting": False},
    "claims": [],
    "agenda_votes": {},
    "memory_candidates": [],
}


def _make_fake_chat_completion(responses=None):
    """Create a fake chat_completion function returning full response dicts."""
    resp = responses or DEFAULT_AGENT_RESPONSES

    async def fake_chat_completion(base_url, api_key, model, messages,
                                   temperature=0.7, max_tokens=1024,
                                   json_mode=False, agent_name="unknown"):
        content = resp.get(agent_name, resp.get("default", f"[{agent_name} responds]"))
        return {
            "choices": [{
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "model": model,
        }
    return fake_chat_completion


@pytest.fixture
def mock_llm():
    """
    Fixture that patches all LLM call sites used by A2AEngine.

    Usage:
        async def test_engine_runs(mock_llm):
            engine = _make_engine()
            events = [e async for e in engine.run()]
            assert any(e["event"] == "complete" for e in events)
    """
    responses = DEFAULT_AGENT_RESPONSES

    fake_chat = _make_fake_chat_completion(responses)

    async def fake_content(base_url, api_key, model, messages,
                           temperature=0.7, max_tokens=1024,
                           json_mode=False, agent_name="unknown"):
        return responses.get(agent_name, responses.get("default", f"[{agent_name} responds]"))

    async def fake_json(*args, **kwargs):
        return {}

    async def fake_stream(*args, **kwargs):
        """Async generator mock for stream_completion_with_thinking."""
        content = responses.get("default", "[agent responds]")
        yield {"type": "content_token", "delta": content}
        yield {"type": "done", "thinking": "", "content": content}

    async def fake_moderator_fn(*args, **kwargs):
        return "The moderator speaks."

    async def fake_observer(*args, **kwargs):
        return dict(MOCK_OBSERVER_RESPONSE)

    with patch("backend.a2a.engine.chat_completion", side_effect=fake_chat), \
         patch("backend.a2a.engine.get_completion_content", side_effect=fake_content), \
         patch("backend.a2a.engine.get_completion_json", side_effect=fake_json), \
         patch("backend.a2a.engine.get_completion_with_thinking",
               return_value=("", responses.get("default", "[thinking]"), False)), \
         patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fake_stream), \
         patch("backend.a2a.engine.moderator_intro", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.moderator_challenge", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.moderator_synthesis", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.extract_turn_data", side_effect=fake_observer):
        yield
