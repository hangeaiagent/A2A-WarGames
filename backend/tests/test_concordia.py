"""
Tests for Concordia-inspired cognitive components (CR-014).

Tests the three Phase 1 components:
  - Self-Reflection (build_self_reflection)
  - Formative Memories (generate_formative_memories_sync / async)
  - Thought Chains (ReasoningChain, moderator_challenge_with_reasoning, resolve_round_outcome)

Also tests engine integration when concordia_engine feature flag is enabled.
"""
import pytest
from unittest.mock import patch, AsyncMock


# =====================================================================
# 1. Formative Memories — Synchronous (no LLM)
# =====================================================================

class TestFormativeMemoriesSync:
    """Test generate_formative_memories_sync — deterministic, no LLM."""

    def test_basic_persona_generates_memories(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Alice",
            "slug": "alice",
            "role": "CFO",
            "fears": ["budget overrun", "staff layoffs"],
            "needs": ["cost control", "board confidence"],
            "batna": "Emergency austerity plan",
            "signal_cle": "Cautious approach to spending",
        }
        memories = generate_formative_memories_sync(stakeholder)
        assert len(memories) >= 4  # 2 fears + 2 needs + 1 BATNA
        types = {m["type"] for m in memories}
        assert "fear_triggered" in types
        assert "belief_update" in types
        assert "proposal" in types

    def test_empty_stakeholder_generates_no_crash(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        memories = generate_formative_memories_sync({"name": "Empty", "slug": "empty"})
        assert isinstance(memories, list)

    def test_fears_as_json_string(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Bob",
            "slug": "bob",
            "fears": '["technical debt", "team burnout"]',
        }
        memories = generate_formative_memories_sync(stakeholder)
        fear_memories = [m for m in memories if m["type"] == "fear_triggered"]
        assert len(fear_memories) == 2

    def test_hard_constraints_have_high_salience(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Carol",
            "slug": "carol",
            "hard_constraints": ["No cloud migration", "Must keep legacy DB"],
        }
        memories = generate_formative_memories_sync(stakeholder)
        constraint_mems = [m for m in memories if "red line" in m["content"]]
        assert len(constraint_mems) == 2
        for m in constraint_mems:
            assert m["salience"] >= 0.9

    def test_adkar_low_scores_detected(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Dave",
            "slug": "dave",
            "adkar": {"awareness": 1, "desire": 2, "knowledge": 4, "ability": 5, "reinforcement": 3},
        }
        memories = generate_formative_memories_sync(stakeholder)
        adkar_mems = [m for m in memories if "change-readiness" in m["content"]]
        assert len(adkar_mems) == 1
        assert "awareness" in adkar_mems[0]["content"]
        assert "desire" in adkar_mems[0]["content"]

    def test_content_truncated_to_200_chars(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Eve",
            "slug": "eve",
            "fears": ["a" * 300],
        }
        memories = generate_formative_memories_sync(stakeholder)
        for m in memories:
            assert len(m["content"]) <= 200

    def test_grounding_quotes_converted(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {
            "name": "Frank",
            "slug": "frank",
            "grounding_quotes": ["We tried that before and it failed", "I believe in gradual change"],
        }
        memories = generate_formative_memories_sync(stakeholder)
        quote_mems = [m for m in memories if "once said" in m["content"]]
        assert len(quote_mems) == 2

    def test_project_context_adds_org_memory(self):
        from backend.a2a.concordia.formative_memories import generate_formative_memories_sync
        stakeholder = {"name": "Grace", "slug": "grace"}
        project = {"organization_name": "Acme Corp"}
        memories = generate_formative_memories_sync(stakeholder, project)
        org_mems = [m for m in memories if "Acme Corp" in m["content"]]
        assert len(org_mems) == 1


# =====================================================================
# 2. Self-Reflection
# =====================================================================

class TestSelfReflection:
    """Test build_self_reflection — requires mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_history(self):
        from backend.a2a.concordia.self_reflection import build_self_reflection
        result = await build_self_reflection(
            base_url="http://mock",
            api_key="key",
            model="gpt-4",
            agent_name="Alice",
            agent_slug="alice",
            baseline_position="Cautious about spending",
            recent_memories=[],
            conversation_history=[],
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_generates_reflection_with_mocked_llm(self):
        from backend.a2a.concordia.self_reflection import build_self_reflection

        async def mock_content(*args, **kwargs):
            return "Alice's current stance: Still cautious about budget increases."

        with patch("backend.a2a.concordia.self_reflection.get_completion_content", side_effect=mock_content):
            result = await build_self_reflection(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                agent_name="Alice",
                agent_slug="alice",
                baseline_position="Cautious about spending",
                recent_memories=["- [concession] Alice agreed to phased rollout"],
                conversation_history=[
                    {"role": "user", "content": "What do you think about the budget?"},
                    {"role": "assistant", "content": "I remain cautious but open to phased approaches."},
                ],
            )
        assert "[SELF-REFLECTION" in result
        assert "position_check" in result

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self):
        from backend.a2a.concordia.self_reflection import build_self_reflection

        async def fail_content(*args, **kwargs):
            raise ConnectionError("LLM unreachable")

        with patch("backend.a2a.concordia.self_reflection.get_completion_content", side_effect=fail_content):
            result = await build_self_reflection(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                agent_name="Alice",
                agent_slug="alice",
                baseline_position="Cautious",
                recent_memories=[],
                conversation_history=[
                    {"role": "assistant", "content": "I think we should be careful."},
                ],
            )
        # Should return empty string on failure (all questions failed)
        assert result == ""


# =====================================================================
# 3. Thought Chains
# =====================================================================

class TestReasoningChain:
    """Test ReasoningChain accumulating Q&A context."""

    @pytest.mark.asyncio
    async def test_chain_accumulates_steps(self):
        from backend.a2a.concordia.thought_chains import ReasoningChain

        async def mock_content(*args, **kwargs):
            return "The debate is making progress."

        with patch("backend.a2a.concordia.thought_chains.get_completion_content", side_effect=mock_content):
            chain = ReasoningChain(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                system_prompt="You are a moderator.",
            )
            a1 = await chain.ask("Is the debate progressing?")
            a2 = await chain.ask("Should we intervene?")

        assert len(chain.steps) == 2
        assert "Step 1" in chain.context
        assert "Step 2" in chain.context

    @pytest.mark.asyncio
    async def test_chain_handles_failure(self):
        from backend.a2a.concordia.thought_chains import ReasoningChain

        async def fail_content(*args, **kwargs):
            raise ConnectionError("LLM down")

        with patch("backend.a2a.concordia.thought_chains.get_completion_content", side_effect=fail_content):
            chain = ReasoningChain(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                system_prompt="You are a moderator.",
            )
            result = await chain.ask("Test question")

        assert result == "(reasoning step failed)"
        assert len(chain.steps) == 1


class TestModeratorChallengeWithReasoning:
    """Test moderator_challenge_with_reasoning — multi-step challenge."""

    @pytest.mark.asyncio
    async def test_returns_intervention_and_reasoning(self):
        from backend.a2a.concordia.thought_chains import moderator_challenge_with_reasoning

        call_count = 0

        async def mock_content(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            answers = [
                "The debate is stalling on budget issues.",
                "The agreement appears genuine.",
                "Agent Bob's claims about ROI are unsupported.",
                "No clear repetition yet.",
                "I challenge Agent Bob: provide specific ROI projections.",
            ]
            return answers[min(call_count - 1, len(answers) - 1)]

        with patch("backend.a2a.concordia.thought_chains.get_completion_content", side_effect=mock_content):
            result = await moderator_challenge_with_reasoning(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                transcript=[
                    {"speaker": "alice", "speaker_name": "Alice", "content": "I support the proposal.", "round": 1},
                    {"speaker": "bob", "speaker_name": "Bob", "content": "The ROI is great.", "round": 1},
                ],
                stakeholders=[
                    {"slug": "alice", "name": "Alice"},
                    {"slug": "bob", "name": "Bob"},
                ],
                analytics_context={"consensus_score": 0.8},
            )

        assert "intervention" in result
        assert "reasoning" in result
        assert "should_inject_event" in result
        assert len(result["reasoning"]) == 5
        assert isinstance(result["intervention"], str)


class TestResolveRoundOutcome:
    """Test resolve_round_outcome — canonical outcome resolution."""

    @pytest.mark.asyncio
    async def test_returns_canonical_outcome(self):
        from backend.a2a.concordia.thought_chains import resolve_round_outcome

        async def mock_content(*args, **kwargs):
            return "Budget proposal tabled pending CTO review."

        with patch("backend.a2a.concordia.thought_chains.get_completion_content", side_effect=mock_content):
            result = await resolve_round_outcome(
                base_url="http://mock",
                api_key="key",
                model="gpt-4",
                transcript=[
                    {"speaker": "alice", "speaker_name": "Alice", "content": "I propose phased budget.", "round": 1},
                    {"speaker": "bob", "speaker_name": "Bob", "content": "Need more data.", "round": 1},
                ],
                round_num=1,
                stakeholders=[
                    {"slug": "alice", "name": "Alice"},
                    {"slug": "bob", "name": "Bob"},
                ],
            )

        assert "canonical_outcome" in result
        assert "proposals" in result
        assert "reasoning" in result
        assert len(result["reasoning"]) == 3


# =====================================================================
# 4. Engine Integration — concordia_engine feature flag
# =====================================================================

def _make_concordia_engine(num_rounds=1, agents_per_turn=2):
    """Create a test engine with concordia_engine enabled."""
    from backend.a2a.engine import A2AEngine
    stakeholders = [
        {
            "slug": "alice", "name": "Alice",
            "system_prompt": "You are Alice.",
            "influence": 0.6, "attitude": "supportive", "tts_voice": None,
            "signal_cle": "Supportive of innovation",
            "fears": ["budget overrun"],
            "needs": ["cost control"],
        },
        {
            "slug": "bob", "name": "Bob",
            "system_prompt": "You are Bob.",
            "influence": 0.4, "attitude": "skeptical", "tts_voice": None,
            "signal_cle": "Skeptical about change",
            "fears": ["technical debt"],
            "needs": ["stability"],
        },
    ]
    project = {"name": "Test", "description": "Integration test", "organization_name": "TestOrg", "context": "ctx"}
    return A2AEngine(
        session_id=1, question="Should we adopt AI?",
        stakeholders=stakeholders, project=project,
        llm_base_url="http://mock", llm_api_key="mock",
        default_model="gpt-4", chairman_model="gpt-4",
        num_rounds=num_rounds, agents_per_turn=agents_per_turn,
        feature_flags={"concordia_engine": True, "agent_memory": True},
    )


@pytest.fixture
def mock_llm_concordia():
    """Extended mock fixture that also mocks concordia LLM calls."""
    from backend.tests.mock_llm import DEFAULT_AGENT_RESPONSES, _make_fake_chat_completion, MOCK_OBSERVER_RESPONSE

    responses = DEFAULT_AGENT_RESPONSES
    fake_chat = _make_fake_chat_completion(responses)

    async def fake_content(*args, **kwargs):
        return responses.get("default", "[agent responds]")

    async def fake_json(*args, **kwargs):
        return {}

    async def fake_stream(*args, **kwargs):
        content = responses.get("default", "[agent responds]")
        yield {"type": "content_token", "delta": content}
        yield {"type": "done", "thinking": "", "content": content}

    async def fake_moderator_fn(*args, **kwargs):
        return "The moderator speaks."

    async def fake_observer(*args, **kwargs):
        return dict(MOCK_OBSERVER_RESPONSE)

    async def fake_self_reflection(*args, **kwargs):
        return "[SELF-REFLECTION — Review before responding]\n- **position_check**: Stance unchanged.\n"

    async def fake_challenge_reasoning(*args, **kwargs):
        return {
            "intervention": "I challenge the weak arguments presented.",
            "reasoning": [{"question": "test", "answer": "test answer"}],
            "should_inject_event": False,
        }

    with patch("backend.a2a.engine.chat_completion", side_effect=fake_chat), \
         patch("backend.a2a.engine.get_completion_content", side_effect=fake_content), \
         patch("backend.a2a.engine.get_completion_json", side_effect=fake_json), \
         patch("backend.a2a.engine.get_completion_with_thinking",
               return_value=("", responses.get("default", "[thinking]"), False)), \
         patch("backend.a2a.engine.stream_completion_with_thinking", side_effect=fake_stream), \
         patch("backend.a2a.engine.moderator_intro", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.moderator_challenge", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.moderator_synthesis", side_effect=fake_moderator_fn), \
         patch("backend.a2a.engine.extract_turn_data", side_effect=fake_observer), \
         patch("backend.a2a.engine.build_self_reflection", side_effect=fake_self_reflection), \
         patch("backend.a2a.engine.moderator_challenge_with_reasoning", side_effect=fake_challenge_reasoning):
        yield


@pytest.mark.asyncio
async def test_concordia_engine_emits_formative_memories_event(mock_llm_concordia):
    """When concordia_engine + agent_memory are enabled, formative_memories_ready event is emitted."""
    engine = _make_concordia_engine(num_rounds=1, agents_per_turn=2)
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "formative_memories_ready" in event_types
    fm_event = next(e for e in events if e["event"] == "formative_memories_ready")
    assert fm_event["data"]["agent_count"] == 2


@pytest.mark.asyncio
async def test_concordia_engine_completes_successfully(mock_llm_concordia):
    """Engine with concordia_engine flag runs to completion."""
    engine = _make_concordia_engine(num_rounds=1, agents_per_turn=2)
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "complete" in event_types


@pytest.mark.asyncio
async def test_concordia_engine_generates_formative_memories(mock_llm_concordia):
    """Formative memories are stored on the engine instance."""
    engine = _make_concordia_engine(num_rounds=1, agents_per_turn=2)
    events = [e async for e in engine.run()]
    assert hasattr(engine, '_formative_memories')
    assert "alice" in engine._formative_memories
    assert "bob" in engine._formative_memories
    assert len(engine._formative_memories["alice"]) > 0


@pytest.mark.asyncio
async def test_concordia_without_agent_memory_skips_formative(mock_llm_concordia):
    """When concordia_engine is on but agent_memory is off, formative memories are skipped."""
    from backend.a2a.engine import A2AEngine
    stakeholders = [
        {"slug": "alice", "name": "Alice", "system_prompt": "You are Alice.",
         "influence": 0.6, "attitude": "supportive", "tts_voice": None},
    ]
    project = {"name": "Test", "description": "Test", "organization_name": "Org", "context": "ctx"}
    engine = A2AEngine(
        session_id=1, question="Test?",
        stakeholders=stakeholders, project=project,
        llm_base_url="http://mock", llm_api_key="mock",
        default_model="gpt-4", chairman_model="gpt-4",
        num_rounds=1, agents_per_turn=1,
        feature_flags={"concordia_engine": True, "agent_memory": False},
    )
    events = [e async for e in engine.run()]
    event_types = [e["event"] for e in events]
    assert "formative_memories_ready" not in event_types
