"""
Engine integration tests using the mock LLM adapter.

These tests exercise the full engine.run() loop without a live LLM endpoint.
"""
import pytest
from unittest.mock import patch, AsyncMock
from backend.tests.mock_llm import mock_llm, MOCK_OBSERVER_RESPONSE, _make_fake_chat_completion


def _make_engine(num_rounds=1, agents_per_turn=2):
    from backend.a2a.engine import A2AEngine
    stakeholders = [
        {"slug": "alice", "name": "Alice", "system_prompt": "You are Alice.",
         "influence": 0.6, "attitude": "supportive", "tts_voice": None},
        {"slug": "bob", "name": "Bob", "system_prompt": "You are Bob.",
         "influence": 0.4, "attitude": "skeptical", "tts_voice": None},
    ]
    project = {"name": "Test", "description": "Integration test", "organization": "Org", "context": "ctx"}
    return A2AEngine(
        session_id=1, question="Should we adopt AI?",
        stakeholders=stakeholders, project=project,
        llm_base_url="http://mock", llm_api_key="mock",
        default_model="gpt-4", chairman_model="gpt-4",
        num_rounds=num_rounds, agents_per_turn=agents_per_turn,
    )


@pytest.mark.asyncio
async def test_engine_run_emits_complete_event(mock_llm):
    """Full run() loop completes and emits a 'complete' event."""
    engine = _make_engine(num_rounds=1, agents_per_turn=2)
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "complete" in event_types
    assert "turn_end" in event_types


@pytest.mark.asyncio
async def test_engine_run_emits_turn_end_with_content(mock_llm):
    """turn_end events carry non-empty content."""
    engine = _make_engine(num_rounds=1, agents_per_turn=2)
    turn_ends = [e async for e in engine.run() if e["event"] == "turn_end"]
    assert len(turn_ends) >= 1
    for event in turn_ends:
        assert event["data"]["content"]  # no blank responses


@pytest.mark.asyncio
async def test_engine_run_stop_requested_halts_early(mock_llm):
    """Requesting stop before run() causes the loop to exit cleanly."""
    engine = _make_engine(num_rounds=3, agents_per_turn=2)
    engine.request_stop()
    events = [e async for e in engine.run()]
    # Should emit very few events (agenda_init at most) then stop
    turn_ends = [e for e in events if e["event"] == "turn_end"]
    assert len(turn_ends) == 0


@pytest.mark.asyncio
async def test_engine_run_empty_content_replaced_with_fallback(mock_llm):
    """Empty LLM response (blank string) is replaced, not persisted as blank."""
    async def empty_stream(*args, **kwargs):
        yield {"type": "content_token", "delta": ""}
        yield {"type": "done", "thinking": "", "content": ""}

    with patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=empty_stream):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        turn_ends = [e async for e in engine.run() if e["event"] == "turn_end"]
    # Content should be a fallback string, not empty
    for te in turn_ends:
        content = te["data"]["content"]
        if te["data"]["speaker"] != "moderator":
            assert content.strip(), f"Agent turn_end has blank content: {te['data']}"


@pytest.mark.asyncio
async def test_engine_fallback_skips_observer(mock_llm):
    """When an agent returns a fallback response, observer is skipped."""
    async def fallback_stream(*args, **kwargs):
        yield {"type": "done", "thinking": "", "content": ""}

    with patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fallback_stream):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        engine.feature_flags["streaming_tokens"] = True  # #191: opt-in streaming
        events = [e async for e in engine.run()]
        # Agent content should be replaced with fallback text
        turn_ends = [e for e in events if e["event"] == "turn_end"
                     and e["data"]["speaker"] != "moderator"]
        for te in turn_ends:
            assert "reflecting" in te["data"]["content"] or "unavailable" in te["data"]["content"]


@pytest.mark.asyncio
async def test_engine_observer_runs_in_background(mock_llm):
    """Observer data is populated after run() completes (background task)."""
    engine = _make_engine(num_rounds=1, agents_per_turn=2)
    events = [e async for e in engine.run()]
    # After the full run, observer_data should have been populated by background tasks
    # (the _wait_for_observers() call ensures this before synthesis)
    assert len(engine.observer_data) >= 2  # at least 2 agents' data


@pytest.mark.asyncio
async def test_engine_mention_routing_no_error(mock_llm):
    """Enabling mention_routing does not raise AttributeError."""
    engine = _make_engine(num_rounds=1, agents_per_turn=2)
    engine.feature_flags["mention_routing"] = True
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "complete" in event_types


@pytest.mark.asyncio
async def test_engine_thinking_bubbles_fallback_detected(mock_llm):
    """When thinking_bubbles is enabled and LLM returns fallback, observer is skipped."""
    from backend.a2a.llm_client import _fallback_response

    fallback = _fallback_response("TestAgent")
    # The 3-tuple now includes is_fallback=True
    thinking_text = ""
    content = fallback["choices"][0]["message"]["content"]

    with patch("backend.a2a.engine.get_completion_with_thinking",
               return_value=(thinking_text, content, True)):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        engine.feature_flags["streaming_tokens"] = False  # force non-streaming path
        engine.feature_flags["thinking_bubbles"] = True
        events = [e async for e in engine.run()]
        # Agent turns with fallback should NOT trigger background observer
        turn_ends = [e for e in events if e["event"] == "turn_end"
                     and e["data"]["speaker"] != "moderator"]
        for te in turn_ends:
            assert te["data"].get("finish_reason") == "error"


@pytest.mark.asyncio
async def test_engine_observer_emits_via_queue(mock_llm):
    """Background observer pushes observer events through the injected queue."""
    engine = _make_engine(num_rounds=1, agents_per_turn=1)
    events = [e async for e in engine.run()]
    observer_events = [e for e in events if e["event"] == "observer"]
    # At least one observer event should have real data (not empty dict)
    non_empty = [e for e in observer_events if e["data"] and e["data"].get("position_summary")]
    assert len(non_empty) >= 1, f"Expected at least 1 non-empty observer event, got: {observer_events}"


@pytest.mark.asyncio
async def test_engine_skip_observer_no_observer_calls(mock_llm):
    """With skip_observer=True, no observer extraction occurs."""
    engine = _make_engine(num_rounds=1, agents_per_turn=2)
    engine.skip_observer = True
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "complete" in event_types
    # No observer events should be emitted (observer is fully skipped)
    observer_events = [e for e in events if e["event"] == "observer"]
    assert len(observer_events) == 0
    assert len(engine.observer_data) == 0


@pytest.mark.asyncio
async def test_engine_streaming_tokens_emits_content_tokens(mock_llm):
    """With streaming_tokens=True, content_token events are yielded in real-time."""
    async def fake_stream(*args, **kwargs):
        yield {"type": "content_token", "delta": "Hello "}
        yield {"type": "content_token", "delta": "world"}
        yield {"type": "done", "thinking": "", "content": "Hello world"}

    with patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fake_stream):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        engine.feature_flags["streaming_tokens"] = True
        events = [e async for e in engine.run()]

    content_tokens = [e for e in events if e["event"] == "content_token"]
    assert len(content_tokens) >= 2, f"Expected >=2 content_token events, got {len(content_tokens)}"
    # Verify deltas
    deltas = [e["data"]["delta"] for e in content_tokens]
    assert "Hello " in deltas
    assert "world" in deltas

    # turn_end should still fire with the complete content
    turn_ends = [e for e in events if e["event"] == "turn_end" and e["data"]["speaker"] != "moderator"]
    assert len(turn_ends) >= 1
    assert turn_ends[0]["data"]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_engine_streaming_tokens_with_thinking(mock_llm):
    """With streaming_tokens=True, thinking_token events are also yielded."""
    async def fake_stream(*args, **kwargs):
        yield {"type": "thinking_token", "delta": "Let me think..."}
        yield {"type": "content_token", "delta": "My answer"}
        yield {"type": "done", "thinking": "Let me think...", "content": "My answer"}

    with patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fake_stream):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        engine.feature_flags["streaming_tokens"] = True
        events = [e async for e in engine.run()]

    thinking_tokens = [e for e in events if e["event"] == "thinking_token"]
    content_tokens = [e for e in events if e["event"] == "content_token"]
    assert len(thinking_tokens) >= 1
    assert len(content_tokens) >= 1


@pytest.mark.asyncio
async def test_engine_build_self_model_null_safety(mock_llm):
    """_build_self_model handles None values for agreement_with/disagreement_with."""
    engine = _make_engine(num_rounds=1, agents_per_turn=1)
    # Simulate observer result with None values
    observer_result = {
        "sentiment": {"overall": 0.5},
        "behavioral_signals": {
            "agreement_with": None,
            "disagreement_with": None,
            "position_stability": 0.9,
        },
    }
    # Should not raise
    engine._build_self_model("alice", observer_result)
    assert "alice" in engine._agent_self_models


@pytest.mark.asyncio
async def test_engine_turn_start_includes_speaker_name(mock_llm):
    """turn_start events include both speaker and speaker_name fields."""
    engine = _make_engine(num_rounds=1, agents_per_turn=1)
    events = [e async for e in engine.run()]
    turn_starts = [e for e in events if e["event"] == "turn_start"]
    assert len(turn_starts) >= 1
    for ts in turn_starts:
        assert "speaker" in ts["data"]
        assert "speaker_name" in ts["data"]
        assert ts["data"]["speaker_name"]  # not empty


@pytest.mark.asyncio
async def test_engine_suppresses_contaminated_meta_content(mock_llm):
    """Meta chain-of-thought text in content is treated as fallback output."""
    leaked_meta = (
        "The user wants me to respond as Marc, the Finance lead.\n\n"
        "Key characteristics to embody:\n- Department: Finance\n- Power level: 7/10"
    )

    async def contaminated_chat(*args, **kwargs):
        return {
            "choices": [{"message": {"role": "assistant", "content": leaked_meta}, "finish_reason": "stop"}],
            "model": "deepseek-r1",
        }

    with patch("backend.a2a.engine.chat_completion", side_effect=contaminated_chat):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        events = [e async for e in engine.run()]

    turn_ends = [e for e in events if e["event"] == "turn_end" and e["data"]["speaker"] != "moderator"]
    assert len(turn_ends) >= 1
    for turn_end in turn_ends:
        assert turn_end["data"]["finish_reason"] == "error"
        assert turn_end["data"]["content"].startswith("*")
        assert "The user wants me to respond as Marc" not in turn_end["data"]["content"]


@pytest.mark.asyncio
async def test_engine_streaming_reasoning_model_drops_contaminated_tokens(mock_llm):
    """Reasoning models defer content tokens and suppress them if final content is contaminated."""
    leaked_meta = "The user wants me to respond as Marc.\nKey characteristics to embody:"

    async def fake_stream(*args, **kwargs):
        yield {"type": "content_token", "delta": "The user wants me to respond as Marc."}
        yield {"type": "content_token", "delta": "\nKey characteristics to embody:"}
        yield {"type": "done", "thinking": "", "content": leaked_meta}

    with patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fake_stream):
        engine = _make_engine(num_rounds=1, agents_per_turn=1)
        engine.feature_flags["streaming_tokens"] = True
        for stakeholder in engine.stakeholders:
            stakeholder["llm_model"] = "deepseek-r1"
        events = [e async for e in engine.run()]

    content_tokens = [e for e in events if e["event"] == "content_token"]
    assert content_tokens == []
    turn_ends = [e for e in events if e["event"] == "turn_end" and e["data"]["speaker"] != "moderator"]
    assert len(turn_ends) >= 1
    assert all(turn_end["data"]["finish_reason"] == "error" for turn_end in turn_ends)
