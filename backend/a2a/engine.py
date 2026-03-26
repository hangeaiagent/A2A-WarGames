"""
A2A Engine — core async wargame simulation loop.

Orchestrates the full debate: Moderator → Stakeholder turns → Observer extraction
→ Analytics snapshots → SSE events. See PRD §4.2 for the flow.
"""

import asyncio
import datetime
import json
import logging
import re
from typing import AsyncGenerator, Optional

from .llm_client import chat_completion, get_completion_content, get_completion_json, get_completion_with_thinking, stream_completion_with_thinking
from .prompt_compiler import compile_persona_prompt, compile_reinject_reminder
from .moderator import moderator_intro, moderator_challenge, moderator_synthesis
from .observer import extract_turn_data
from .speaker_selection import SpeakerSelector
from .concordia.self_reflection import build_self_reflection
from .concordia.formative_memories import generate_formative_memories_sync
from .concordia.thought_chains import moderator_challenge_with_reasoning

logger = logging.getLogger(__name__)


class A2AEngine:
    """
    Runs a multi-agent wargame debate session.

    Usage:
        engine = A2AEngine(session_id, config, llm_settings, stakeholders, project)
        async for event in engine.run():
            # yield SSE events
    """

    # CR-010: Memory decay constants
    SESSION_MEMORY_DECAY_RATE = 0.1   # decay per round for session-scope memories
    PROJECT_MEMORY_DECAY_RATE = 0.05  # decay per round for project-scope memories
    MIN_DECAY_FACTOR = 0.1            # minimum decay floor
    REASONING_MODEL_MARKERS = ("deepseek-r1", "deepseek-reasoner", "kimi-k2.5")
    ROLE_PLANNING_PREFIXES = ("the user wants me to respond as", "i need to respond as")
    KEY_CHARACTERISTICS_PREFIX = "key characteristics to embody"
    CONTAMINATED_CONTENT_PREFIXES = ROLE_PLANNING_PREFIXES + (KEY_CHARACTERISTICS_PREFIX,)

    def __init__(
        self,
        session_id: int,
        question: str,
        stakeholders: list[dict],
        project: dict,
        llm_base_url: str,
        llm_api_key: str,
        default_model: str,
        chairman_model: str,
        num_rounds: int = 5,
        agents_per_turn: int = 3,
        moderator_style: str = "neutral",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        moderator_name: str = "Moderator",
        moderator_title: str = "",
        moderator_mandate: str = "",
        moderator_persona_prompt: str = "",
        prior_session_context: Optional[str] = None,
        feature_flags: Optional[dict] = None,
        anti_groupthink: bool = True,
        project_id: Optional[int] = None,
        skip_observer: bool = False,
        locale: str = "en",
    ):
        self.session_id = session_id
        self.project_id = project_id  # CR-010: needed for memory scoping
        # #113: session-scoped logger so all engine log lines include session_id
        self._log = logging.LoggerAdapter(logger, {"session_id": session_id})
        self.question = question
        self.stakeholders = stakeholders
        self.project = project

        # LLM config
        self.base_url = llm_base_url
        self.api_key = llm_api_key
        self.default_model = default_model
        self.chairman_model = chairman_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.council_models: list[str] = []  # populated externally after construction

        # Session config
        self.num_rounds = num_rounds
        self.agents_per_turn = agents_per_turn
        self.moderator_style = moderator_style
        self.anti_groupthink = anti_groupthink  # False disables challenge/contrarian forcing

        # Moderator persona
        self.moderator_name = moderator_name
        self.moderator_title = moderator_title
        self.moderator_mandate = moderator_mandate
        self.moderator_persona_prompt = moderator_persona_prompt

        # Cross-session context (Task 3)
        self.prior_session_context = prior_session_context

        # Locale for prompt language (en/zh)
        self.locale = locale

        # Feature flags (from LLMSettings).
        # Recognised keys (all default to False unless noted):
        #   streaming_tokens    — stream per-token deltas to frontend (#191)
        #   thinking_bubbles    — show agent thinking tokens in UI (#191)
        #   agent_memory        — CR-010 episodic memory store
        #   private_threads     — CR-011 whisper channel windows
        #   mention_routing     — @mention-directed speaker queue
        #   concordia_engine    — CR-014: Concordia-inspired cognitive enhancements
        #                         (self-reflection, formative memories, thought chains)
        #   parallel_agents     — #68: fire initial-round LLM calls concurrently,
        #                         gather results, then emit in speaker order.
        #                         NOT YET IMPLEMENTED — flag reserved for v0.15+.
        #                         When True, secondary responses remain sequential
        #                         (they benefit from reading initial-round transcript).
        self.feature_flags: dict = feature_flags or {}

        # Observer skip flag (CLI --no-observer performance mode)
        self.skip_observer: bool = skip_observer

        # State
        self.transcript: list[dict] = []
        self.turn_counter = 0
        self.round_syntheses: list[str] = []
        self.turns_spoken: dict[str, int] = {s["slug"]: 0 for s in stakeholders}
        self.agent_histories: dict[str, list[dict]] = {s["slug"]: [] for s in stakeholders}
        self.observer_data: list[dict] = []
        self.current_round: int = 0
        self._stop_requested = False
        self._agent_self_models: dict[str, str] = {}  # CR-010: per-agent self-model summaries

        # Pause/resume control (Task 1)
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # start unpaused
        self._paused = False

        self.last_challenge_turn: int = -99  # sentinel: no challenge ever issued

        # SSE broadcast queue for injected messages
        self._injected_queue: asyncio.Queue = asyncio.Queue()

        # Agenda items for this session (populated at session start)
        self.agenda_items: list[dict] = []

        # Pre-warm cache (set externally by run_session after session creation).
        # If populated, run() uses these instead of re-calling the LLM on round 1.
        self._pre_warmed_agenda: Optional[list[dict]] = None
        self._pre_warmed_moderator_opening: Optional[str] = None

        # User ID for RLS context (set externally if multi-tenant)
        self.user_id: Optional[str] = None

        # Speaker queue (for @mention routing — §1)
        self.speaker_queue = SpeakerSelector(stakeholders)

        # Background observer tasks (§2: async observer)
        self._observer_tasks: list = []

        # CR-019: per-agent model overrides {slug: (base_url, api_key, model_id)}
        self.agent_model_overrides: dict[str, tuple] = {}

        # CR-011: private thread state
        self._private_quotas: dict[str, int] = {}   # slug → remaining initiations
        self._private_contexts: dict[str, str] = {} # slug → injected private context summary
        self._private_thread_limit: int = 3
        self._private_thread_depth: int = 2
        self._private_thread_quota_mode: str = "fixed"

        # Runtime mute set — slugs in here are skipped by SpeakerSelector (#115)
        self._muted_agents: set = set()

        # Token usage tracking — accumulated across all LLM calls
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

        # #112: analytics context cache — rebuilt only when observer_data grows
        self._analytics_cache: Optional[dict] = None
        self._analytics_cache_len: int = 0

        # Checkpoint / crash-recovery state
        self._current_phase: str = "idle"
        self._speakers_completed_this_round: list = []

        # Pre-compile system prompts
        self._system_prompts: dict[str, str] = {}
        for s in stakeholders:
            if s.get("system_prompt"):
                self._system_prompts[s["slug"]] = s["system_prompt"]
            else:
                self._system_prompts[s["slug"]] = compile_persona_prompt(s, project, locale=self.locale)


    # ------------------------------------------------------------------
    # Pause / Resume (Task 1)
    # ------------------------------------------------------------------

    def pause(self):
        """Pause the engine after the current LLM call completes."""
        self._pause_event.clear()
        self._paused = True

    def resume(self):
        """Resume a paused engine."""
        self._pause_event.set()
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    def request_stop(self):
        """Signal the engine to stop after the current turn completes."""
        self._stop_requested = True
        # Also release the pause event so the loop can observe _stop_requested
        self._pause_event.set()
        # Cancel any pending background observer tasks so they don't
        # waste LLM tokens or write to DB after the session is finalized (#90)
        for task in self._observer_tasks:
            task.cancel()
        self._observer_tasks.clear()

    def get_checkpoint(self) -> dict:
        """Return current engine state for pause/crash recovery."""
        return {
            "round": self.current_round,
            "turn": self.turn_counter,
            "phase": self._current_phase,
            "speakers_completed": list(self._speakers_completed_this_round),
        }

    def _accumulate_usage(self, usage: dict):
        """Accumulate token usage from an LLM response."""
        if usage:
            self._total_prompt_tokens += usage.get("prompt_tokens", 0)
            self._total_completion_tokens += usage.get("completion_tokens", 0)

    def _moderator_kwargs(self) -> dict:
        """Common moderator persona keyword arguments."""
        return {
            "moderator_name": self.moderator_name,
            "moderator_title": self.moderator_title,
            "moderator_mandate": self.moderator_mandate,
            "moderator_persona_prompt": self.moderator_persona_prompt,
            "locale": self.locale,
        }

    def _should_challenge(self, round_num: int, agent_turns_this_round: int, is_last_agent: bool, analytics_ctx: Optional[dict] = None) -> bool:
        """Determine if the moderator should issue a challenge this turn."""
        # Must have at least 3 agent turns in the current round
        if agent_turns_this_round < 3:
            return False

        # Must not have challenged in the last 2 turns
        if self.turn_counter - self.last_challenge_turn < 2:
            return False

        # Check consensus (use pre-computed context if provided)
        if analytics_ctx is None:
            analytics_ctx = self._build_analytics_context()
        consensus = analytics_ctx.get("consensus_score") if analytics_ctx else None

        # Challenge if premature agreement detected
        if consensus is not None and consensus > 0.75:
            return True

        # Challenge if round > 1 and this is the last agent in turn order
        if round_num > 1 and is_last_agent:
            return True

        return False

    async def run(self, start_round: int = 1, skip_speakers: list = None) -> AsyncGenerator[dict, None]:
        """
        Main wargame loop. Yields SSE event dicts.

        Event types: turn_start, turn, turn_end, observer, analytics, synthesis, complete, error

        Args:
            start_round: Round number to begin from (default 1). Used by
                         resume_from_db() to continue from where a session left off.
            skip_speakers: List of speaker slugs to skip in the first round (mid-round recovery).
        """
        skip_speakers = skip_speakers or []
        try:
            # --- Agenda: use pre-warmed cache, load from DB on resume, or extract fresh ---
            yield {"event": "status", "data": {"phase": "extracting_agenda", "message": "Analyzing the question and extracting agenda items..."}}
            if start_round > 1 or skip_speakers:
                # Resume path: try to load agenda from DB first, avoid re-extracting
                self.agenda_items = await self._load_existing_agenda()
                if not self.agenda_items:
                    self.agenda_items = await self._extract_agenda()
                    await self._persist_agenda(self.agenda_items)
            elif self._pre_warmed_agenda:
                # Pre-warm fast path: agenda was extracted in background at session creation
                self._log.info(
                    "Session %s: using pre-warmed agenda (%d items)",
                    self.session_id,
                    len(self._pre_warmed_agenda),
                )
                self.agenda_items = self._pre_warmed_agenda
                # Still persist to DB in case it wasn't written yet (idempotent)
                await self._persist_agenda(self.agenda_items)
            else:
                self.agenda_items = await self._extract_agenda()
                await self._persist_agenda(self.agenda_items)
            yield {"event": "agenda_init", "data": {"items": self.agenda_items}}

            # CR-011: Initialize private thread quotas
            if self.feature_flags.get("private_threads", False):
                self._init_private_quotas()

            # CR-014: Concordia formative memories — inject persona backstory
            if self.feature_flags.get("concordia_engine", False) and self.feature_flags.get("agent_memory", False):
                yield {"event": "status", "data": {"phase": "formative_memories", "message": "Generating formative backstory memories..."}}
                for s in self.stakeholders:
                    formative = generate_formative_memories_sync(s, self.project)
                    if formative:
                        self._log.info(
                            "CR-014: Generated %d formative memories for %s",
                            len(formative), s["slug"],
                        )
                        # Store as initial memory candidates for persistence
                        if not hasattr(self, '_formative_memories'):
                            self._formative_memories: dict[str, list[dict]] = {}
                        self._formative_memories[s["slug"]] = formative
                yield {"event": "formative_memories_ready", "data": {"agent_count": len(self.stakeholders)}}

            for round_num in range(start_round, self.num_rounds + 1):
                self.current_round = round_num
                # #92: explicit round_start event so frontend can show a per-round progress bar
                yield {"event": "round_start", "data": {"round": round_num, "total_rounds": self.num_rounds}}
                yield {"event": "status", "data": {"phase": "preparing_round", "message": f"Preparing for Round {round_num}...", "round": round_num}}
                # Reset per-round speaker tracking
                self._speakers_completed_this_round = []
                if self._stop_requested:
                    break

                # --- Pause checkpoint (Task 1) ---
                if self._paused:
                    yield {"event": "session_paused", "data": {"session_id": self.session_id, "round": round_num, "checkpoint": self.get_checkpoint()}}
                    await self._pause_event.wait()
                    if self._stop_requested:
                        break
                    yield {"event": "session_resumed", "data": {"session_id": self.session_id, "round": round_num}}
                if self._stop_requested:
                    break

                # --- 1. Moderator intro ---
                yield {"event": "status", "data": {"phase": "moderator_preparing", "message": "The Moderator is preparing opening remarks..."}}
                self._current_phase = "moderator_intro"
                prior_synthesis = self.round_syntheses[-1] if self.round_syntheses else None
                analytics_ctx = self._build_analytics_context()

                # Use pre-warmed opening for round 1 (no prior synthesis / analytics available)
                if round_num == start_round and self._pre_warmed_moderator_opening and not prior_synthesis:
                    self._log.info(
                        "Session %s: using pre-warmed moderator opening (%d chars)",
                        self.session_id,
                        len(self._pre_warmed_moderator_opening),
                    )
                    mod_content = self._pre_warmed_moderator_opening
                    # Clear so subsequent rounds always call the LLM (they have prior synthesis)
                    self._pre_warmed_moderator_opening = None
                else:
                    mod_content, mod_usage = await moderator_intro(
                        base_url=self.base_url,
                        api_key=self.api_key,
                        model=self.chairman_model,
                        question=self.question,
                        stakeholders=self.stakeholders,
                        round_num=round_num,
                        prior_synthesis=prior_synthesis,
                        analytics_context=analytics_ctx,
                        moderator_style=self.moderator_style,
                        prior_session_context=self.prior_session_context if round_num == start_round else None,
                        **self._moderator_kwargs(),
                    )
                    self._accumulate_usage(mod_usage)

                self.turn_counter += 1
                mod_msg = self._make_message("moderator", self.moderator_name, mod_content, round_num, stage="intro")
                self.transcript.append(mod_msg)

                yield {"event": "turn_end", "data": mod_msg}

                # Drain any injected messages
                async for ev in self._drain_injected():
                    yield ev

                if self._stop_requested:
                    break

                # --- Pause checkpoint ---
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                # --- 2. Initial stakeholder responses ---
                # #68 parallel_agents flag (v0.15+, default False):
                #   When True, replace this sequential loop with gather-then-emit:
                #   1. Pre-allocate turn_numbers for each speaker (avoids counter race)
                #   2. Clone immutable snapshots (transcript, agent_histories, private_ctx)
                #   3. Fire all LLM calls via asyncio.gather(_agent_call_only(...))
                #   4. Process results SEQUENTIALLY in speaker order to update state
                #   5. Secondary responses (step 4) stay sequential — they read initial transcript
                #   Safety: 10 race conditions identified (see issue #68 comment 2026-03-10).
                #   Non-negotiable: parallel_agents=False must produce byte-identical output.
                # TODO(#68): extract _agent_call_only() from _agent_turn(), add if/else branch.
                self._current_phase = "agent_response"
                speakers = self.speaker_queue.select_speakers(
                    num_speakers=self.agents_per_turn,
                    turns_spoken=self.turns_spoken,
                    consensus_score=analytics_ctx.get("consensus_score") if analytics_ctx else None,
                )

                agent_turns_this_round = 0
                for idx, speaker in enumerate(speakers):
                    if self._stop_requested:
                        break
                    # Mid-round recovery: skip speakers who already completed this round
                    if speaker["slug"] in skip_speakers and round_num == start_round:
                        agent_turns_this_round += 1
                        continue
                    await self._pause_event.wait()
                    if self._stop_requested:
                        break
                    async for event in self._agent_turn(speaker, round_num, mod_content, speaker_index=idx, total_speakers=len(speakers)):
                        yield event
                    agent_turns_this_round += 1
                    self._speakers_completed_this_round.append(speaker["slug"])

                    # Drain any injected messages
                    async for ev in self._drain_injected():
                        yield ev

                if self._stop_requested:
                    break

                # --- Pause checkpoint ---
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                # --- 3. Moderator challenge (conditional — only when needed) ---
                self._current_phase = "challenge"
                # Determine remaining agents for secondary responses
                spoken_slugs = {s["slug"] for s in speakers}
                remaining = [s for s in self.stakeholders if s["slug"] not in spoken_slugs]

                # Check if challenge is warranted (compute analytics_ctx once, reuse below)
                total_agents_this_round = agent_turns_this_round
                is_last_initial = (agent_turns_this_round == len(speakers))
                challenge_analytics_ctx = self._build_analytics_context()
                if self.anti_groupthink and self._should_challenge(round_num, total_agents_this_round, is_last_initial, analytics_ctx=challenge_analytics_ctx):
                    # CR-014: Use multi-step thought chain when concordia_engine is enabled
                    if self.feature_flags.get("concordia_engine", False):
                        tc_result = await moderator_challenge_with_reasoning(
                            base_url=self.base_url,
                            api_key=self.api_key,
                            model=self.chairman_model,
                            transcript=self.transcript,
                            stakeholders=self.stakeholders,
                            analytics_context=challenge_analytics_ctx,
                            moderator_style=self.moderator_style,
                            moderator_name=self.moderator_name,
                        )
                        challenge_content = tc_result["intervention"]
                        # Emit reasoning chain for transparency
                        yield {"event": "thought_chain", "data": {
                            "type": "moderator_challenge",
                            "round": round_num,
                            "steps": tc_result["reasoning"],
                            "should_inject_event": tc_result["should_inject_event"],
                        }}
                    else:
                        challenge_content, challenge_usage = await moderator_challenge(
                            base_url=self.base_url,
                            api_key=self.api_key,
                            model=self.chairman_model,
                            transcript=self.transcript,
                            stakeholders=self.stakeholders,
                            analytics_context=challenge_analytics_ctx,
                            moderator_style=self.moderator_style,
                            **self._moderator_kwargs(),
                        )
                        self._accumulate_usage(challenge_usage)

                    self.turn_counter += 1
                    self.last_challenge_turn = self.turn_counter
                    challenge_msg = self._make_message("moderator", self.moderator_name, challenge_content, round_num, stage="challenge")
                    self.transcript.append(challenge_msg)
                    yield {"event": "turn_end", "data": challenge_msg}

                    # Drain any injected messages after challenge
                    async for ev in self._drain_injected():
                        yield ev

                    # Use challenge content as context for secondary responses
                    secondary_context = challenge_content
                else:
                    # No challenge — use moderator intro as context for remaining
                    secondary_context = mod_content

                if self._stop_requested:
                    break

                # --- Pause checkpoint ---
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                # --- 4. Secondary responses (remaining agents) ---
                for idx, speaker in enumerate(remaining):
                    if self._stop_requested:
                        break
                    # Mid-round recovery: skip speakers who already completed this round
                    if speaker["slug"] in skip_speakers and round_num == start_round:
                        agent_turns_this_round += 1
                        continue
                    await self._pause_event.wait()
                    if self._stop_requested:
                        break
                    total_round_speakers = len(speakers) + len(remaining)
                    async for event in self._agent_turn(speaker, round_num, secondary_context, speaker_index=len(speakers) + idx, total_speakers=total_round_speakers):
                        yield event
                    agent_turns_this_round += 1
                    self._speakers_completed_this_round.append(speaker["slug"])

                    # Drain any injected messages
                    async for ev in self._drain_injected():
                        yield ev

                if self._stop_requested:
                    break

                # --- Pause checkpoint ---
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                # --- 5. Round synthesis ---
                yield {"event": "status", "data": {"phase": "synthesizing", "message": "Moderator is synthesizing round insights..."}}
                self._current_phase = "synthesis"
                # Wait for all background observer tasks before synthesis
                await self._wait_for_observers()
                # Drain any observer results that were queued by background tasks
                async for ev in self._drain_injected():
                    yield ev
                round_messages = [m for m in self.transcript if m.get("round") == round_num]
                is_final = round_num == self.num_rounds

                synthesis_content, synthesis_usage = await moderator_synthesis(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model=self.chairman_model,
                    transcript=round_messages,
                    stakeholders=self.stakeholders,
                    round_num=round_num,
                    is_final=is_final,
                    moderator_style=self.moderator_style,
                    **self._moderator_kwargs(),
                )
                self._accumulate_usage(synthesis_usage)

                self.round_syntheses.append(synthesis_content)

                self.turn_counter += 1
                synthesis_msg = self._make_message("moderator", self.moderator_name, synthesis_content, round_num, stage="synthesis")
                self.transcript.append(synthesis_msg)

                # Persist synthesis as a Message row via turn_end
                yield {"event": "turn_end", "data": synthesis_msg}

                yield {"event": "synthesis", "data": {
                    "round": round_num,
                    "content": synthesis_content,
                    "is_final": is_final,
                }}

                # --- 6. Analytics snapshot event ---
                yield {"event": "status", "data": {"phase": "computing_analytics", "message": "Computing analytics and risk scores..."}}
                yield {"event": "analytics", "data": {
                    "round": round_num,
                    "observer_extractions": [o for o in self.observer_data if o.get("round") == round_num],
                    "turns_spoken": dict(self.turns_spoken),
                }}

                # CR-010: Apply memory decay after each round
                if self.feature_flags.get("agent_memory", False):
                    self._decay_memories()

                # CR-011: Between-round private thread opportunity window
                if self.feature_flags.get("private_threads", False) and not is_final and not self._stop_requested:
                    self._current_phase = "whisper_window"
                    async for whisper_event in self._run_private_opportunity_window(round_num):
                        yield whisper_event

                # #92: explicit round_end event for frontend round progress
                yield {"event": "round_end", "data": {"round": round_num, "total_rounds": self.num_rounds, "is_final": is_final}}

            # Wait for any remaining background observers before finishing
            await self._wait_for_observers()
            # Drain any remaining observer events
            async for ev in self._drain_injected():
                yield ev

            # CR-010: Promote high-salience memories to project scope
            if self.feature_flags.get("agent_memory", False):
                self._promote_session_memories()

            # Session complete
            yield {"event": "complete", "data": {
                "session_id": self.session_id,
                "status": "stopped" if self._stop_requested else "complete",
                "total_turns": self.turn_counter,
                "total_rounds": min(round_num, self.num_rounds) if 'round_num' in locals() else 0,
            }}

        except Exception as e:
            self._log.exception("A2A engine error")
            yield {"event": "error", "data": {"message": str(e), "turn": self.turn_counter}}


    # ------------------------------------------------------------------
    # Continue Session (Task 2)
    # ------------------------------------------------------------------

    @classmethod
    async def resume_from_db(
        cls,
        session_id: int,
        additional_rounds: int,
        stakeholders: list[dict],
        project: dict,
        llm_base_url: str,
        llm_api_key: str,
        default_model: str,
        chairman_model: str,
        agents_per_turn: int = 3,
        moderator_style: str = "neutral",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        user_id: str = None,
        project_id: Optional[int] = None,
        skip_observer: bool = False,
        resume_mode: str = "next_round",
    ) -> "A2AEngine":
        """
        Build an engine from a completed/paused session's DB history, ready to run
        additional_rounds more rounds.

        Args:
            resume_mode: "next_round" (default) — start from the round after the last completed one.
                         "mid_round" — for crash recovery; resume from the max round found in DB,
                         skipping speakers who already completed a turn this round.
        """
        from ..database import get_db_session_with_user
        from ..models import Message, Session

        db = get_db_session_with_user(user_id)
        compact_summary: str = None
        try:
            messages = (
                db.query(Message)
                .filter_by(session_id=session_id)
                .order_by(Message.turn)
                .all()
            )
            # BUG-CR010-3 fix: resolve project_id from session if not provided
            if project_id is None:
                sess = db.query(Session).filter_by(id=session_id).first()
                if sess:
                    project_id = sess.project_id
            # #118: load compact summary if present
            sess = db.query(Session).filter_by(id=session_id).first()
            if sess:
                compact_summary = getattr(sess, "compact_summary", None)
        finally:
            db.close()

        _stage_map = {0: "intro", 1: "response", 2: "challenge", 3: "synthesis", 4: "inject"}

        existing_rounds = 0
        round_syntheses: list[str] = []
        transcript: list[dict] = []
        agent_histories: dict[str, list[dict]] = {s["slug"]: [] for s in stakeholders}
        turns_spoken: dict[str, int] = {s["slug"]: 0 for s in stakeholders}

        max_round_num = 0
        # Track which speakers have spoken in the max (latest incomplete) round
        speakers_by_round: dict[int, list[str]] = {}

        for m in messages:
            # #118: skip compacted messages — they are replaced by compact_summary
            if getattr(m, "compacted", False):
                continue
            stage_name = _stage_map.get(m.stage, "response")
            # Use persisted round_num if available (CR-004); fall back to 0 for old rows
            msg_round = getattr(m, "round_num", None) or 0
            if msg_round > max_round_num:
                max_round_num = msg_round
            msg_dict = {
                "turn": m.turn, "round": msg_round,
                "speaker": m.speaker, "speaker_name": m.speaker_name,
                "content": m.content, "stage": stage_name,
                "session_id": session_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            transcript.append(msg_dict)

            if stage_name == "synthesis" and m.speaker == "moderator":
                round_syntheses.append(m.content)
                existing_rounds += 1

            if m.speaker != "moderator" and m.speaker in agent_histories:
                agent_histories[m.speaker].append({"role": "assistant", "content": m.content})
                turns_spoken[m.speaker] = turns_spoken.get(m.speaker, 0) + 1
                # Track speakers per round for mid-round recovery
                if msg_round not in speakers_by_round:
                    speakers_by_round[msg_round] = []
                if m.speaker not in speakers_by_round[msg_round]:
                    speakers_by_round[msg_round].append(m.speaker)

        turn_counter = max((m.turn for m in messages), default=0)

        # Determine start round and skip_speakers based on resume_mode
        skip_speakers: list[str] = []
        if resume_mode == "mid_round" and max_round_num > 0:
            # Check if the max round has a synthesis (meaning it's complete)
            max_round_has_synthesis = any(
                m.stage == 3 and m.speaker == "moderator" and
                getattr(m, "round_num", None) == max_round_num
                for m in messages
            )
            if max_round_has_synthesis:
                # Max round is complete — start from next round
                start_round = max_round_num + 1
            else:
                # Max round is incomplete — resume mid-round, skipping already-spoken agents
                start_round = max_round_num
                skip_speakers = speakers_by_round.get(max_round_num, [])
                # Remove the incomplete round from existing_rounds count
                # (it won't have a synthesis, so existing_rounds is already correct)
        else:
            start_round = existing_rounds + 1

        engine = cls(
            session_id=session_id, question="",
            stakeholders=stakeholders, project=project,
            llm_base_url=llm_base_url, llm_api_key=llm_api_key,
            default_model=default_model, chairman_model=chairman_model,
            num_rounds=existing_rounds + additional_rounds,
            agents_per_turn=agents_per_turn, moderator_style=moderator_style,
            temperature=temperature, max_tokens=max_tokens,
            project_id=project_id,
            skip_observer=skip_observer,
        )

        engine.transcript = transcript
        engine.agent_histories = agent_histories
        engine.turns_spoken = turns_spoken
        engine.round_syntheses = round_syntheses
        engine.turn_counter = turn_counter
        engine._start_round = start_round
        engine._skip_speakers = skip_speakers  # stored for run() caller to pass in
        engine.current_round = max_round_num  # §2b: restore current round from DB
        engine.user_id = user_id  # §2a: thread user_id for RLS

        # #118: inject compact summary as prior context so agents are aware of compacted history
        if compact_summary:
            engine.prior_session_context = compact_summary

        return engine

    # ------------------------------------------------------------------
    # Inject message
    # ------------------------------------------------------------------

    async def inject_message(self, content: str, as_moderator: bool = False) -> dict:
        """Inject a human/consultant message into the debate."""
        self.turn_counter += 1
        speaker = "moderator" if as_moderator else "consultant"
        speaker_name = self.moderator_name if as_moderator else "Consultant"
        msg = self._make_message(speaker, speaker_name, content, round_num=self.current_round, stage="inject")
        self.transcript.append(msg)

        # Push to the SSE broadcast queue so active stream picks it up
        await self._injected_queue.put({"event": "turn_end", "data": msg})

        return msg

    async def _drain_injected(self) -> AsyncGenerator[dict, None]:
        """Yield any queued injected messages."""
        while not self._injected_queue.empty():
            try:
                event = self._injected_queue.get_nowait()
                yield event
            except asyncio.QueueEmpty:
                break

    async def _agent_turn(self, speaker: dict, round_num: int, context_content: str, speaker_index: int = 0, total_speakers: int = 0) -> AsyncGenerator[dict, None]:
        """Run a single stakeholder agent turn + observer extraction."""
        slug = speaker["slug"]
        name = speaker["name"]
        model = speaker.get("llm_model") or self.default_model
        # CR-019: per-agent model override (base_url, api_key, model)
        _override = self.agent_model_overrides.get(slug)
        if _override:
            agent_base_url, agent_api_key, model = _override
        else:
            agent_base_url = self.base_url
            agent_api_key = self.api_key
        self._current_speaker_slug = slug  # track for @mention filtering

        # Notify frontend that this agent is about to speak
        yield {"event": "status", "data": {"phase": "agent_thinking", "message": f"{name} is formulating a response...", "speaker": slug, "speaker_name": name}}
        yield {"event": "turn_start", "data": {"speaker": slug, "speaker_name": name, "round": round_num, "stage": "response", "session_id": self.session_id}}

        # Build agent messages
        system_prompt = self._system_prompts[slug]

        # CR-011: Inject private thread context (whisper agreements/commitments)
        private_ctx = self._private_contexts.pop(slug, None)
        if private_ctx:
            system_prompt = (
                f"[PRIVATE CONTEXT — NOT TO BE DISCLOSED DIRECTLY]\n{private_ctx}\n"
                "Act on these private commitments naturally, without revealing them explicitly.\n\n"
                + system_prompt
            )

        # CR-010: Inject self-model awareness
        if self.feature_flags.get("agent_memory", False):
            self_model = self._agent_self_models.get(slug)
            if self_model:
                system_prompt = (
                    f"[SELF-AWARENESS: {self_model}]\n\n"
                    + system_prompt
                )

        # Re-inject persona every 3 turns
        total_agent_turns = self.turns_spoken.get(slug, 0)
        if total_agent_turns > 0 and total_agent_turns % 3 == 0:
            reminder = compile_reinject_reminder(speaker, locale=self.locale)
            system_prompt = reminder + "\n\n" + system_prompt

        # Token budget — all agents get substantial tokens (CR-004 §1)
        # Floor of 2048, capped at 80% of max_tokens to reserve space for system + context
        agent_max_tokens = max(int(self.max_tokens * 0.8), 2048)

        # Build conversation: system + recent transcript context + current framing
        messages = [{"role": "system", "content": system_prompt}]

        # Add agent's own conversation history (last 6 messages max)
        for hist_msg in self.agent_histories[slug][-6:]:
            messages.append(hist_msg)

        # Current context
        turns_remaining = max(0, total_speakers - speaker_index - 1) if total_speakers else 0
        base_context = self._build_agent_context(round_num, context_content)
        agenda_ctx = self._build_agenda_context(turns_remaining=turns_remaining)
        user_msg_content = base_context + (f"\n\n{agenda_ctx}" if agenda_ctx else "")

        # CR-010: Inject retrieved memories into context
        memory_block = ""
        memory_lines_raw: list[str] = []  # CR-014: for self-reflection input
        if self.feature_flags.get("agent_memory", False):
            memories = await self._retrieve_memories(slug, user_msg_content, k=5)
            if memories:
                memory_lines = []
                for mem in memories:
                    scope_tag = "[prior session] " if mem["scope"] == "project" else ""
                    line = f"- [{mem['type']}] {scope_tag}{mem['content']}"
                    memory_lines.append(line)
                    memory_lines_raw.append(line)
                memory_block = "## YOUR MEMORIES\nKey moments you should remember:\n" + "\n".join(memory_lines) + "\n\n"

        # CR-014: Concordia self-reflection — pre-turn introspection
        reflection_block = ""
        if self.feature_flags.get("concordia_engine", False):
            baseline = speaker.get("signal_cle", "")
            try:
                reflection_block = await build_self_reflection(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model=self.default_model,
                    agent_name=name,
                    agent_slug=slug,
                    baseline_position=baseline,
                    recent_memories=memory_lines_raw,
                    conversation_history=self.agent_histories[slug][-6:],
                    temperature=0.3,
                    max_tokens=512,
                )
            except Exception:
                self._log.warning("CR-014: self-reflection failed for %s — continuing", slug, exc_info=True)

        # Prepend memories + reflection to the user message content
        prefix = ""
        if memory_block:
            prefix += memory_block
        if reflection_block:
            prefix += reflection_block + "\n"
        final_user_content = prefix + user_msg_content if prefix else user_msg_content
        messages.append({
            "role": "user",
            "content": final_user_content,
        })

        # Call LLM — use streaming when feature flag is enabled
        is_fallback = False
        content = ""
        thinking_text = ""
        stream_finish_reason = None  # #111: finish_reason from streaming path
        pending_content_tokens: list[str] = []
        defer_content_streaming = (
            self.feature_flags.get("streaming_tokens", False) and self._is_reasoning_model(model)
        )

        if self.feature_flags.get("streaming_tokens", False):  # #191: opt-in, not opt-out
            # Streaming mode: yield tokens as they arrive
            accumulated_thinking = ""
            accumulated_content = ""
            async for chunk in stream_completion_with_thinking(
                base_url=agent_base_url,
                api_key=agent_api_key,
                model=model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=agent_max_tokens,
            ):
                chunk_type = chunk.get("type")
                if chunk_type == "stream_reset":
                    # #138: LLM client is retrying — discard accumulated partial content
                    # so the frontend can clear its buffer and start fresh.
                    accumulated_thinking = ""
                    accumulated_content = ""
                    yield {
                        "event": "stream_reset",
                        "data": {
                            "type": "stream_reset",
                            "speaker": slug,
                            "speaker_name": name,
                        },
                    }
                elif chunk_type == "thinking_token":
                    delta = chunk.get("delta", "")
                    accumulated_thinking += delta
                    yield {
                        "event": "thinking_token",
                        "data": {
                            "type": "thinking_token",
                            "speaker": slug,
                            "speaker_name": name,
                            "delta": delta,
                        },
                    }
                elif chunk_type == "content_token":
                    delta = chunk.get("delta", "")
                    accumulated_content += delta
                    if defer_content_streaming:
                        pending_content_tokens.append(delta)
                    else:
                        yield {
                            "event": "content_token",
                            "data": {
                                "type": "content_token",
                                "speaker": slug,
                                "speaker_name": name,
                                "delta": delta,
                            },
                        }
                elif chunk_type == "done":
                    thinking_text = chunk.get("thinking", accumulated_thinking)
                    content = chunk.get("content", accumulated_content)
                    # Reasoning-only models (kimi): if content is empty but thinking
                    # has substance, use thinking as content so the turn isn't blank.
                    if (not content or not content.strip()) and thinking_text and thinking_text.strip():
                        self._log.warning(
                            "Agent %s: streaming produced no content but has thinking (%d chars) — using as content",
                            name, len(thinking_text),
                        )
                        content = thinking_text
                    # Detect fallback from streaming path (#134)
                    if chunk.get("is_fallback"):
                        is_fallback = True
                    # #111: capture finish_reason from streaming done chunk
                    stream_finish_reason = chunk.get("finish_reason")
                    if stream_finish_reason == "length":
                        self._log.warning(
                            "Agent %s turn truncated by max_tokens (finish_reason=length)",
                            speaker["slug"],
                        )
                    break

            # Streaming failed — try batch fallback with other council models
            if is_fallback and self.council_models:
                fallback_models = [m for m in self.council_models if m != model]
                for fb_model in fallback_models:
                    self._log.warning(
                        "Agent %s: streaming model %s failed, batch fallback to %s",
                        name, model, fb_model,
                    )
                    fb_result = await chat_completion(
                        base_url=agent_base_url,
                        api_key=agent_api_key,
                        model=fb_model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=agent_max_tokens,
                        agent_name=name,
                    )
                    fb_fallback = fb_result.get("_is_fallback", False) or fb_result.get("model") == "fallback"
                    if not fb_fallback:
                        fb_msg = fb_result.get("choices", [{}])[0].get("message", {})
                        fb_content = fb_msg.get("content", "") or fb_msg.get("reasoning", "")
                        if fb_content and fb_content.strip():
                            content = fb_content
                            is_fallback = False
                            self._accumulate_usage(fb_result.get("usage"))
                            self._log.info("Agent %s: batch fallback to %s succeeded", name, fb_model)
                            break

        elif self.feature_flags.get("thinking_bubbles", False):  # #191: opt-in, not opt-out
            # Non-streaming thinking mode (existing behavior)
            thinking_text, content, is_fallback = await get_completion_with_thinking(
                base_url=agent_base_url,
                api_key=agent_api_key,
                model=model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=agent_max_tokens,
            )
            if thinking_text:
                yield {
                    "event": "thinking_token",
                    "data": {
                        "type": "thinking_token",
                        "speaker": slug,
                        "speaker_name": name,
                        "delta": thinking_text,
                    },
                }
        else:
            # Standard batch mode — try primary model, then fallback to other council models
            models_to_try = [model] + [m for m in self.council_models if m != model]
            for try_model in models_to_try:
                result = await chat_completion(
                    base_url=agent_base_url,
                    api_key=agent_api_key,
                    model=try_model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=agent_max_tokens,
                    agent_name=name,
                )
                is_fallback = result.get("_is_fallback", False) or result.get("model") == "fallback"
                if is_fallback and try_model != models_to_try[-1]:
                    self._log.warning(
                        "Agent %s: model %s failed, trying fallback model %s",
                        name, try_model, models_to_try[models_to_try.index(try_model) + 1],
                    )
                    continue  # try next model
                msg_obj = result.get("choices", [{}])[0].get("message", {})
                content = msg_obj.get("content", "")
                # Fallback: reasoning models (kimi, deepseek-r1) may return content in
                # 'reasoning' field when max_tokens exhausts during the thinking phase.
                if not content or not content.strip():
                    reasoning = msg_obj.get("reasoning", "")
                    if reasoning and reasoning.strip():
                        self._log.warning(
                            "Agent %s: empty content but has reasoning (%d chars) — using reasoning as content",
                            name, len(reasoning),
                        )
                        content = reasoning
                if try_model != model and content and content.strip():
                    self._log.info("Agent %s: fallback model %s succeeded", name, try_model)
                break  # got a response (successful or final fallback)

        # Accumulate token usage from the LLM response
        self._accumulate_usage(result.get("usage"))

        # Guard: catch empty content (tokens consumed but no output — #61)
        empty_content = not content or not content.strip()
        contaminated_content = self._is_contaminated_content(content)
        if contaminated_content:
            logger.warning("Detected contaminated chain-of-thought content for '%s'; suppressing turn", slug)

        if empty_content or contaminated_content:
            content = self._fallback_reflection_content(name)
            is_fallback = True

        if defer_content_streaming and not is_fallback:
            for delta in pending_content_tokens:
                yield {
                    "event": "content_token",
                    "data": {
                        "type": "content_token",
                        "speaker": slug,
                        "speaker_name": name,
                        "delta": delta,
                    },
                }

        # Update state
        self.turn_counter += 1
        self.turns_spoken[slug] = self.turns_spoken.get(slug, 0) + 1

        # Store in agent's history (rolling window to prevent context overflow).
        # #185: store user_msg_content (base framing + agenda) not context_content
        # (just moderator framing) so agents "remember" their agenda positions across
        # turns. Memory blocks are ephemeral and intentionally excluded from history.
        MAX_HISTORY_ENTRIES = 12  # #97: keep last 6 rounds of user/assistant pairs (was 6 → 3 rounds)
        self.agent_histories[slug].append({"role": "user", "content": user_msg_content})
        self.agent_histories[slug].append({"role": "assistant", "content": content})
        self.agent_histories[slug] = self.agent_histories[slug][-MAX_HISTORY_ENTRIES:]

        msg = self._make_message(slug, name, content, round_num, stage="response")
        if is_fallback:
            msg["finish_reason"] = "error"
        elif stream_finish_reason:
            msg["finish_reason"] = stream_finish_reason  # #111: propagate LLM finish_reason
        self.transcript.append(msg)

        yield {"event": "turn_end", "data": msg}

        # §1 — @mention routing: bump mentioned agents to front of queue
        if self.feature_flags.get("mention_routing", False):
            mentions = self._extract_mentions(content)
            if mentions:
                self.speaker_queue.prepend_mentions(mentions, current_round=round_num)

        # Skip observer for fallback/error responses (no wasted LLM call)
        # Do NOT emit an empty observer event — undefined speaker key would pollute frontend (#79)
        if is_fallback:
            self._log.warning("Agent '%s' returned fallback response, skipping observer", slug)
            # Drain any injected messages that arrived during the LLM call
            async for ev in self._drain_injected():
                yield ev
            return

        # Skip observer entirely when --no-observer is set (CLI performance mode)
        if self.skip_observer:
            async for ev in self._drain_injected():
                yield ev
            return

        # Observer extraction — run as background task (§2: async observer)
        yield {"event": "status", "data": {"phase": "observer_analyzing", "message": "Observer is analyzing sentiment and claims..."}}
        task = asyncio.create_task(self._observe_in_background(
            slug, name, content, round_num, speaker, self.turn_counter
        ))
        self._observer_tasks.append(task)

        # Drain any injected messages that arrived during the LLM call
        async for ev in self._drain_injected():
            yield ev

    async def _observe_in_background(self, slug, name, content, round_num, speaker, turn_num):
        """Run observer extraction as a background task (§2: does not block next agent)."""
        # Guard: if the session was stopped while observer was pending, skip silently
        if self._stop_requested:
            return
        try:
            observer_result = await extract_turn_data(
                base_url=self.base_url, api_key=self.api_key,
                model=self.default_model, speaker_name=name, speaker_slug=slug,
                turn_content=content, round_num=round_num, turn_num=turn_num,
                speaker_profile=speaker,
                agenda_items=self.agenda_items if self.agenda_items else None,
                locale=self.locale,
            )
            self.observer_data.append(observer_result)

            # Emit observer event via the injected queue so it reaches the SSE stream
            if self._injected_queue is not None:
                await self._injected_queue.put({"event": "observer", "data": observer_result})

            # CR-010: Build agent self-model (pure in-memory, fast)
            if self.feature_flags.get("agent_memory", False) and observer_result:
                self._build_self_model(slug, observer_result)

            # Batch all DB writes from observer into a single session
            has_memories = self.feature_flags.get("agent_memory", False) and observer_result.get("memory_candidates")
            has_votes = bool(observer_result.get("agenda_votes"))
            if has_memories or has_votes:
                await self._persist_observer_db(slug, observer_result, round_num, turn_num)

        except Exception as e:
            self._log.error("Background observer failed for %s: %s", slug, e, exc_info=True)

    async def _wait_for_observers(self):
        """Wait for all pending background observer tasks to complete."""
        if self._observer_tasks:
            await asyncio.gather(*self._observer_tasks, return_exceptions=True)
            self._observer_tasks.clear()

    def _build_self_model(self, slug: str, observer_result: dict):
        """Build agent self-model string from observer data (CR-010)."""
        sentiment = observer_result.get("sentiment", {})
        signals = observer_result.get("behavioral_signals", {})
        agreements = signals.get("agreement_with") or []
        disagreements = signals.get("disagreement_with") or []

        self_model_parts = []
        overall = sentiment.get("overall", 0)
        if overall < -0.3:
            self_model_parts.append(f"You are currently opposing (sentiment: {overall:.1f})")
        elif overall > 0.3:
            self_model_parts.append(f"You are currently supportive (sentiment: {overall:.1f})")
        else:
            self_model_parts.append(f"You are currently neutral (sentiment: {overall:.1f})")

        stability = signals.get("position_stability", 1.0)
        if stability < 0.5:
            self_model_parts.append("Your position has shifted significantly from your baseline.")
        elif stability > 0.8:
            self_model_parts.append("You are holding firm to your original position.")

        if agreements:
            self_model_parts.append(f"Allies this session: {', '.join(agreements)}")
        if disagreements:
            self_model_parts.append(f"Opponents this session: {', '.join(disagreements)}")

        if signals.get("concession_offered"):
            self_model_parts.append("You offered a concession in your last statement.")

        self._agent_self_models[slug] = " | ".join(self_model_parts)

    def _extract_mentions(self, content: str) -> list[str]:
        """Return list of stakeholder slugs mentioned as @Name or @slug in content.

        Lookup priority per captured token:
          1. Exact full-name match  (@JaneSmith → "Jane Smith" if stored as such)
          2. Direct slug match      (@cfo-jane → "cfo-jane")
          3. First-word-of-name     (@Jane → "Jane Smith" → "cfo-jane")
        This handles multi-word names where the user types only the first name.
        """
        raw = re.findall(r'@([A-Za-z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF\-]*)', content)
        name_to_slug = {s['name'].lower(): s['slug'] for s in self.stakeholders}
        slug_set = {s['slug'] for s in self.stakeholders}
        # First word of each stakeholder name as fallback (first match wins on collision)
        first_to_slug: dict[str, str] = {}
        for s in self.stakeholders:
            first_word = s['name'].split()[0].lower()
            if first_word not in first_to_slug:
                first_to_slug[first_word] = s['slug']

        current = getattr(self, '_current_speaker_slug', None)
        mentioned = []
        for token in raw:
            lower = token.lower()
            slug = (
                name_to_slug.get(lower)
                or (token if token in slug_set else None)
                or first_to_slug.get(lower)
            )
            if slug and slug != current:
                mentioned.append(slug)
        return list(dict.fromkeys(mentioned))  # deduplicate, preserve order

    def _is_reasoning_model(self, model: str) -> bool:
        model_lower = (model or "").strip().lower()
        if model_lower.startswith(("o1", "o3")):
            return True
        return any(marker in model_lower for marker in self.REASONING_MODEL_MARKERS)

    def _is_contaminated_content(self, content: str) -> bool:
        text = (content or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if any(lowered.startswith(prefix) for prefix in self.CONTAMINATED_CONTENT_PREFIXES):
            return True
        if self.KEY_CHARACTERISTICS_PREFIX in lowered and any(
            prefix in lowered for prefix in self.ROLE_PLANNING_PREFIXES
        ):
            return True
        return False

    def _fallback_reflection_content(self, name: str) -> str:
        return f"*{name} is reflecting on the discussion and has nothing to add at this time.*"

    def _make_message(self, speaker: str, speaker_name: str, content: str, round_num: int, stage: str = "response") -> dict:
        return {
            "turn": self.turn_counter,
            "round": round_num,
            "speaker": speaker,
            "speaker_name": speaker_name,
            "content": content,
            "stage": stage,
            "session_id": self.session_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def _build_agent_context(self, round_num: int, moderator_framing: str) -> str:
        """Build the context message for a stakeholder agent.

        #97: expanded context window — use context_window_strategy when set, otherwise
        include last 10 non-moderator entries (up from 5) with speaker-diversity fallback.
        """
        strategy = getattr(self, "context_window_strategy", "last_2_rounds")
        context_lines = [f"## Current debate — Round {round_num}\n"]
        context_lines.append(f"**{self.moderator_name}:** {moderator_framing}\n")

        agent_turns = [m for m in self.transcript if m.get("speaker") != "moderator"]

        if strategy == "full":
            recent = agent_turns  # all turns
        elif strategy == "synthesis_only":
            recent = []  # omit transcript; agent relies on moderator framing only
        else:
            # "last_2_rounds" (default) — last 10 entries (was 5), preserving all speakers
            recent = agent_turns[-10:]

        if recent:
            context_lines.append("**Recent statements:**\n")
            for m in recent:
                context_lines.append(f"- **{m['speaker_name']}:** {m['content']}")

        context_lines.append("\n\nRespond with your position. Be specific. Name other stakeholders if you agree or disagree with them.")
        return "\n".join(context_lines)

    def _build_analytics_context(self) -> Optional[dict]:
        """Build a summary analytics dict for the Moderator.

        #112: result is cached and only recomputed when observer_data grows,
        avoiding O(N) full-list scans on every call within the same round.
        """
        if not self.observer_data:
            return None

        # Return cached result if observer_data hasn't grown since last build
        current_len = len(self.observer_data)
        _cache = getattr(self, "_analytics_cache", None)
        _cache_len = getattr(self, "_analytics_cache_len", -1)
        if _cache is not None and _cache_len == current_len:
            return self._analytics_cache

        sentiments = {}
        for o in self.observer_data:
            slug = o.get("speaker")
            if slug and "sentiment" in o:
                sentiments[slug] = o["sentiment"].get("overall", 0)

        # Consensus proxy: normalize sentiment from [-1,1] to [0,1], then invert variance
        if len(sentiments) >= 2:
            vals = list(sentiments.values())
            normalized = [(v + 1) / 2 for v in vals]  # [-1,1] → [0,1]
            mean = sum(normalized) / len(normalized)
            variance = sum((v - mean) ** 2 for v in normalized) / len(normalized)
            consensus = max(0.0, min(1.0, 1.0 - variance * 4))
        else:
            consensus = None

        # Top risks = most negative sentiment agents
        top_risks = sorted(sentiments, key=sentiments.get)[:3]

        result = {
            "consensus_score": consensus,
            "sentiments": sentiments,
            "top_risks": top_risks,
        }
        # Update cache
        self._analytics_cache = result
        self._analytics_cache_len = current_len
        return result

    # ------------------------------------------------------------------
    # Agenda extraction (CR-006)
    # ------------------------------------------------------------------

    async def _extract_agenda(self) -> list[dict]:
        """Decompose the debate question into 2-4 specific agenda items via LLM."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a debate facilitator. Given a discussion question, break it into "
                        "2 to 4 specific sub-questions that stakeholders must vote on. "
                        "Respond ONLY with JSON: "
                        "{\"items\": [{\"key\": \"item_1\", \"label\": \"...\", \"description\": \"...\"}]}"
                    ),
                },
                {"role": "user", "content": f"Question: {self.question}"},
            ]
            result = await get_completion_json(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.chairman_model,
                messages=messages,
                temperature=0.0,
                max_tokens=1200,
                agent_name="agenda-extractor",
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
            self._log.warning("Agenda extraction failed (graceful skip): %s", e)
            return []

    async def _persist_agenda(self, items: list[dict]) -> None:
        """Persist agenda items to the DB (idempotent — skip if already exists)."""
        if not items:
            return
        from ..database import get_db_session_with_user
        from ..models import SessionAgenda
        db = get_db_session_with_user(self.user_id)
        try:
            existing = db.query(SessionAgenda).filter_by(session_id=self.session_id).count()
            if existing == 0:
                for item in items:
                    db.add(SessionAgenda(
                        session_id=self.session_id,
                        item_key=item["key"],
                        label=item["label"],
                        description=item.get("description", ""),
                    ))
                db.commit()
        except Exception as e:
            self._log.error("Failed to persist agenda: %s", e)
        finally:
            db.close()

    async def _load_existing_agenda(self) -> list[dict]:
        """Load agenda items from DB for this session (used on resume to avoid re-extraction)."""
        from ..database import get_db_session_with_user
        from ..models import SessionAgenda
        db = get_db_session_with_user(getattr(self, "user_id", None))
        try:
            rows = (
                db.query(SessionAgenda)
                .filter_by(session_id=self.session_id)
                .order_by(SessionAgenda.id)
                .all()
            )
            return [
                {"key": r.item_key, "label": r.label, "description": r.description or ""}
                for r in rows
            ]
        except Exception as e:
            self._log.warning("Failed to load existing agenda from DB: %s", e)
            return []
        finally:
            db.close()

    def _tally_votes(self, item_key: str) -> dict:
        """Return the latest stance per agent, tallied."""
        tally: dict[str, int] = {"agree": 0, "oppose": 0, "neutral": 0, "abstain": 0}
        latest: dict[str, str] = {}
        for obs in self.observer_data:
            vote = obs.get("agenda_votes", {}).get(item_key)
            if vote:
                latest[obs["speaker"]] = vote["stance"]
        for stance in latest.values():
            tally[stance] = tally.get(stance, 0) + 1
        return tally

    def _build_agenda_context(self, turns_remaining: int) -> str:
        """Return a brief agenda state block to inject into agent turns."""
        if not self.agenda_items:
            return ""

        tally_by_item = {item["key"]: self._tally_votes(item["key"]) for item in self.agenda_items}

        lines = [f"## Current Agenda ({turns_remaining} turn(s) remaining this round)"]
        for item in self.agenda_items:
            t = tally_by_item[item["key"]]
            lines.append(
                f"- [{item['key']}] {item['label']} | "
                f"agree={t['agree']} oppose={t['oppose']} neutral={t['neutral']}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Observer DB Persistence (batched)
    # ------------------------------------------------------------------

    async def _persist_observer_db(self, slug: str, observer_result: dict,
                                   round_num: int, turn_num: int):
        """Batch-persist all observer DB writes (memories + agenda votes) in one session.

        Reduces DB round-trips from 2-3 to 1 per observer background task.
        """
        from ..analytics.sbert import embed_texts
        from ..models import AgentMemory, AgendaVote
        from ..database import get_db_session_with_user, settings as db_settings

        # 1. Embed memory candidates (CPU-bound — run in executor)
        candidates = observer_result.get("memory_candidates", [])
        embeddings = None
        if candidates:
            texts = [c["content"] for c in candidates]
            embeddings = await asyncio.get_running_loop().run_in_executor(
                None, embed_texts, texts
            )

        is_sqlite = db_settings.database_url.startswith("sqlite")

        # 2. Single DB session for all writes
        db = get_db_session_with_user(getattr(self, "user_id", None))
        try:
            # Persist memory candidates
            if candidates and self.feature_flags.get("agent_memory", False):
                for i, c in enumerate(candidates):
                    raw_emb = embeddings[i] if embeddings else None
                    if raw_emb is not None and is_sqlite:
                        raw_emb = json.dumps(raw_emb)
                    db.add(AgentMemory(
                        project_id=self.project_id,
                        session_id=self.session_id,
                        speaker_slug=slug,
                        memory_type=c["type"],
                        content=c["content"],
                        structured_data=json.dumps({
                            "related_agents": c.get("related_agents", []),
                            "source_turn": turn_num,
                            "source_round": round_num,
                        }),
                        embedding=raw_emb,
                        salience=c.get("salience", 0.5),
                        round_num=round_num,
                        turn=turn_num,
                        scope="session",
                    ))

            # Persist agenda votes
            votes = observer_result.get("agenda_votes", {})
            if votes:
                for item_key, vote_data in votes.items():
                    db.add(AgendaVote(
                        session_id=self.session_id,
                        item_key=item_key,
                        speaker_slug=slug,
                        turn=turn_num,  # #171: use captured turn_num, not self.turn_counter
                        round=round_num,
                        stance=vote_data["stance"],
                        confidence=vote_data["confidence"],
                    ))

            db.commit()
        except Exception as e:
            self._log.error("Failed to persist observer DB writes for %s: %s", slug, e, exc_info=True)
            db.rollback()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Agent Memory (CR-010)
    # ------------------------------------------------------------------

    async def _retrieve_memories(self, speaker_slug: str, context_query: str,
                           k: int = 5) -> list[dict]:
        """Retrieve top-k relevant memories for an agent using semantic similarity.

        Uses pgvector cosine distance + salience weighting.
        Falls back to empty list if agent_memory is disabled or S-BERT unavailable.
        """
        from ..analytics.sbert import embed_text
        from ..models import AgentMemory
        from ..database import get_db_session_with_user

        if self.project_id is None:
            return []

        query_embedding = await asyncio.get_running_loop().run_in_executor(
            None, embed_text, context_query
        )
        if query_embedding is None:
            return []

        db = get_db_session_with_user(getattr(self, "user_id", None))
        try:
            # Base filter (shared by pgvector path and fallback)
            base_filter = [
                AgentMemory.speaker_slug == speaker_slug,
                AgentMemory.project_id == self.project_id,
                AgentMemory.embedding.isnot(None),
            ]

            # Use pgvector ordering if available, capturing the cosine distance value
            # so re-ranking can incorporate actual retrieval relevance (#83).
            scored = []
            try:
                dist_col = AgentMemory.embedding.cosine_distance(query_embedding).label("dist")
                rows = (
                    db.query(AgentMemory, dist_col)
                    .filter(*base_filter)
                    .order_by(dist_col)
                    .limit(k * 2)  # over-fetch for composite re-ranking
                    .all()
                )
                for m, dist in rows:
                    relevance = max(0.0, 1.0 - float(dist))  # cosine dist in [0, 2]
                    composite = relevance * 0.5 + (m.salience or 0.5) * 0.3 + (m.decay_factor or 1.0) * 0.2
                    scored.append((composite, m))
            except Exception:
                # Fallback for SQLite or when pgvector ops unavailable
                memories = db.query(AgentMemory).filter(*base_filter).limit(k * 2).all()
                for m in memories:
                    composite = 0.5 + (m.salience or 0.5) * 0.3 + (m.decay_factor or 1.0) * 0.2
                    scored.append((composite, m))

            scored.sort(key=lambda x: x[0], reverse=True)
            # #151: removed db.commit() from read path — access_count increments were
            # causing unnecessary write transactions on every agent turn under RLS

            return [
                {
                    "type": m.memory_type,
                    "content": m.content,
                    "salience": m.salience,
                    "round": m.round_num,
                    "scope": m.scope,
                }
                for _, m in scored[:k]
            ]
        except Exception as e:
            self._log.error("Memory retrieval failed: %s", e)
            return []
        finally:
            db.close()

    def _promote_session_memories(self):
        """Promote high-salience session memories to project scope for cross-session recall.

        Called once at session end. Sets scope='project' on memories with
        salience >= 0.7 so they appear in future sessions for the same agent.
        """
        from ..models import AgentMemory
        from ..database import get_db_session_with_user

        db = get_db_session_with_user(getattr(self, "user_id", None))
        try:
            high_salience = (
                db.query(AgentMemory)
                .filter(
                    AgentMemory.session_id == self.session_id,
                    AgentMemory.salience >= 0.7,
                    AgentMemory.scope == "session",
                )
                .all()
            )
            for mem in high_salience:
                mem.scope = "project"
            db.commit()
            self._log.info("Promoted %d memories to project scope for session %d",
                         len(high_salience), self.session_id)
        except Exception as e:
            self._log.error("Failed to promote session memories: %s", e)
        finally:
            db.close()

    def _decay_memories(self):
        """Apply recency decay to session memories. Called once per round.

        Reduces decay_factor by SESSION_MEMORY_DECAY_RATE per round for session-scope memories.
        Project-scope memories decay slower (PROJECT_MEMORY_DECAY_RATE per round),
        scoped to only this session's speakers to avoid affecting parallel sessions.

        #190: uses server-side bulk UPDATE (sqlalchemy text) instead of loading all rows
        into Python, avoiding O(N) row-level updates and excessive DB connection pressure.
        """
        from sqlalchemy import text
        from ..database import get_db_session_with_user

        from ..models import AgentMemory
        from sqlalchemy import case, func

        db = get_db_session_with_user(getattr(self, "user_id", None))
        try:
            # #190: bulk UPDATE via ORM expression instead of loading rows into Python.
            # Use CASE to clamp at MIN_DECAY_FACTOR (cross-DB compatible; avoids GREATEST).
            def _decay_expr(rate: float):
                """SQLAlchemy expression: MAX(min_decay, coalesce(decay_factor, 1.0) - rate)"""
                current = func.coalesce(AgentMemory.decay_factor, 1.0)
                new_val = current - rate
                return case((new_val > self.MIN_DECAY_FACTOR, new_val), else_=self.MIN_DECAY_FACTOR)

            # Session-scope memories
            (
                db.query(AgentMemory)
                .filter(
                    AgentMemory.session_id == self.session_id,
                    AgentMemory.scope == "session",
                )
                .update(
                    {AgentMemory.decay_factor: _decay_expr(self.SESSION_MEMORY_DECAY_RATE)},
                    synchronize_session=False,
                )
            )

            # Project-scope memories (only agents in this session)
            session_slugs = [s["slug"] for s in self.stakeholders]
            if session_slugs and self.project_id is not None:
                (
                    db.query(AgentMemory)
                    .filter(
                        AgentMemory.project_id == self.project_id,
                        AgentMemory.scope == "project",
                        AgentMemory.speaker_slug.in_(session_slugs),
                    )
                    .update(
                        {AgentMemory.decay_factor: _decay_expr(self.PROJECT_MEMORY_DECAY_RATE)},
                        synchronize_session=False,
                    )
                )

            db.commit()
        except Exception as e:
            self._log.error("Memory decay failed: %s", e)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # CR-011 — Private Threads (Whisper Channels)
    # ------------------------------------------------------------------

    def _init_private_quotas(self):
        """Compute per-agent private thread initiation quotas at session start."""
        limit = self._private_thread_limit
        mode = self._private_thread_quota_mode

        if mode == "power_proportional":
            powers = [s.get("influence", 0.5) for s in self.stakeholders]
            max_power = max(powers) if powers else 1.0
            if max_power == 0:
                max_power = 1.0
            import math
            for s in self.stakeholders:
                power = s.get("influence", 0.5)
                quota = max(1, math.ceil(limit * power / max_power))
                self._private_quotas[s["slug"]] = quota
        else:
            # Fixed quota for all agents
            for s in self.stakeholders:
                self._private_quotas[s["slug"]] = limit

    def _count_initiated_threads(self, slug: str) -> int:
        """Count threads already initiated by this agent (from in-memory tracking)."""
        return getattr(self, "_initiated_threads", {}).get(slug, 0)

    def _record_initiated_thread(self, slug: str):
        """Record that an agent has initiated a thread."""
        if not hasattr(self, "_initiated_threads"):
            self._initiated_threads: dict[str, int] = {}
        self._initiated_threads[slug] = self._initiated_threads.get(slug, 0) + 1

    async def _run_private_opportunity_window(self, round_num: int) -> AsyncGenerator[dict, None]:
        """
        Between-round opportunity window (CR-011 §2.1 Option A).

        All agents are queried in parallel: does anyone want to initiate a private thread?
        Opened threads run their exchange loop before the next public round starts.
        """
        if not self.stakeholders or len(self.stakeholders) < 2:
            return

        # Notify frontend that private negotiations are starting
        yield {
            "event": "whisper_opportunity_start",
            "data": {"round": round_num, "session_id": self.session_id}
        }

        # Build the last round synthesis for context
        prior_synthesis = self.round_syntheses[-1] if self.round_syntheses else ""

        # Query all agents in parallel for initiation decisions
        decision_tasks = []
        for speaker in self.stakeholders:
            slug = speaker["slug"]
            remaining_quota = self._private_quotas.get(slug, 0)
            already_initiated = self._count_initiated_threads(slug)
            if remaining_quota - already_initiated <= 0:
                decision_tasks.append((slug, None))  # no quota left
                continue
            other_agents = [s for s in self.stakeholders if s["slug"] != slug]
            decision_tasks.append((slug, asyncio.create_task(
                self._agent_private_decision(speaker, other_agents, prior_synthesis, round_num)
            )))

        # Gather results
        decisions = {}
        for slug, task in decision_tasks:
            if task is None:
                decisions[slug] = None
                continue
            try:
                decisions[slug] = await task
            except Exception as e:
                self._log.error("Private thread decision failed for %s: %s", slug, e)
                decisions[slug] = None

        # Process initiations (one per agent, first-come-first-served, check for duplicates)
        opened_pairs: set[frozenset] = set()  # avoid duplicate bilateral threads this window

        for slug, decision in decisions.items():
            if not decision or not decision.get("initiate_private"):
                continue
            target_slug = decision.get("target_agent", "")
            if not target_slug or target_slug == slug:
                continue
            # Validate target exists
            target = next((s for s in self.stakeholders if s["slug"] == target_slug), None)
            if not target:
                continue
            pair = frozenset([slug, target_slug])
            if pair in opened_pairs:
                continue  # already opened this window

            # Deduct quota
            self._record_initiated_thread(slug)
            opened_pairs.add(pair)

            initiator = next(s for s in self.stakeholders if s["slug"] == slug)
            opening_msg = decision.get("opening_message", "")
            internal_reason = decision.get("reason", "")

            # Persist thread in DB
            thread_id = await self._persist_private_thread(
                initiator_slug=slug, target_slug=target_slug,
                round_opened=round_num, status="open"
            )

            # #168: skip this thread entirely if DB persist failed — avoids emitting
            # SSE events with thread_id=-1 which causes frontend matching confusion
            if thread_id < 0:
                self._log.error(
                    "Skipping private thread for %s→%s: DB persist failed (thread_id=-1)",
                    slug, target_slug
                )
                continue

            yield {
                "event": "whisper_thread_open",
                "data": {"thread_id": thread_id, "initiator": slug, "initiator_name": initiator["name"],
                         "target": target_slug, "target_name": target["name"], "round": round_num}
            }

            # Persist opening message
            await self._persist_private_message(
                thread_id=thread_id, speaker_slug=slug,
                content=opening_msg, internal_reason=internal_reason,
                round_num=round_num, turn=self.turn_counter,
            )
            yield {
                "event": "whisper_turn_end",
                "data": {"thread_id": thread_id, "speaker": slug, "speaker_name": initiator["name"],
                         "content": opening_msg, "round": round_num}
            }

            # Target responds: first check if they accept
            accept_decision = await self._agent_private_response(
                target, initiator, opening_msg, round_num
            )

            if not accept_decision.get("accept_private", True):
                # Target declined
                await self._update_private_thread_status(thread_id, "declined")
                decline_msg = accept_decision.get("response", "[Declined]")
                await self._persist_private_message(
                    thread_id=thread_id, speaker_slug=target_slug,
                    content=decline_msg, round_num=round_num, turn=self.turn_counter,
                )
                yield {
                    "event": "whisper_turn_end",
                    "data": {"thread_id": thread_id, "speaker": target_slug, "speaker_name": target["name"],
                             "content": decline_msg, "round": round_num}
                }
                yield {
                    "event": "whisper_thread_close",
                    "data": {"thread_id": thread_id, "outcome": "declined"}
                }
                continue

            # Target accepted — run the exchange loop
            current_msg = accept_decision.get("response", "")
            await self._persist_private_message(
                thread_id=thread_id, speaker_slug=target_slug,
                content=current_msg, round_num=round_num, turn=self.turn_counter,
            )
            yield {
                "event": "whisper_turn_end",
                "data": {"thread_id": thread_id, "speaker": target_slug, "speaker_name": target["name"],
                         "content": current_msg, "round": round_num}
            }

            # Exchange loop: up to (depth - 1) additional exchanges after accept
            thread_msgs = [
                {"speaker": slug, "name": initiator["name"], "content": opening_msg},
                {"speaker": target_slug, "name": target["name"], "content": current_msg},
            ]
            for exchange_idx in range(self._private_thread_depth - 1):
                # Alternating: initiator, target, initiator...
                next_speaker = initiator if exchange_idx % 2 == 0 else target
                other_speaker = target if exchange_idx % 2 == 0 else initiator
                next_slug = next_speaker["slug"]

                reply = await self._agent_private_continue(
                    next_speaker, other_speaker, thread_msgs, round_num
                )
                reply_msg = reply.get("content", "")
                await self._persist_private_message(
                    thread_id=thread_id, speaker_slug=next_slug,
                    content=reply_msg, round_num=round_num, turn=self.turn_counter,
                )
                yield {
                    "event": "whisper_turn_end",
                    "data": {"thread_id": thread_id, "speaker": next_slug,
                             "speaker_name": next_speaker["name"],
                             "content": reply_msg, "round": round_num}
                }
                thread_msgs.append({"speaker": next_slug, "name": next_speaker["name"], "content": reply_msg})

            # Close the thread
            # #166: use "completed" (depth exhausted) instead of hardcoded "agreed"
            await self._update_private_thread_status(thread_id, "closed")
            yield {
                "event": "whisper_thread_close",
                "data": {"thread_id": thread_id, "outcome": "completed"}
            }

            # #158: generate perspective-correct summaries for each participant
            self._private_contexts[slug] = self._summarize_private_thread(
                thread_msgs, agent_a=initiator, agent_b=target
            )
            self._private_contexts[target_slug] = self._summarize_private_thread(
                thread_msgs, agent_a=target, agent_b=initiator
            )

            # CR-010 × CR-011 integration: silent observer extraction on private thread
            if self.feature_flags.get("agent_memory", False):
                await self._extract_private_thread_memories(
                    thread_msgs=thread_msgs,
                    initiator=initiator,
                    target=target,
                    round_num=round_num,
                )

        yield {
            "event": "whisper_opportunity_end",
            "data": {"round": round_num, "threads_opened": len(opened_pairs)}
        }

    async def _agent_private_decision(
        self, speaker: dict, others: list[dict], prior_synthesis: str, round_num: int
    ) -> dict:
        """Ask an agent if it wants to initiate a private thread."""
        others_desc = ", ".join(f"{s['name']} ({s.get('role', '')})" for s in others)
        quota = self._private_quotas.get(speaker["slug"], 0)
        initiated = self._count_initiated_threads(speaker["slug"])

        system = (
            f"You are {speaker['name']}, {speaker.get('role', '')}. "
            f"You have {quota - initiated} private conversation initiation(s) remaining.\n"
            "You may optionally open a private bilateral channel with ONE other participant "
            "before the next public round. Private conversations are NOT visible to others or the moderator.\n"
            "Use this strategically: coalition-building, side deals, information gathering.\n\n"
            "IMPORTANT: Respond with ONLY a raw JSON object:\n"
            '{"initiate_private": true/false, "target_agent": "<slug or empty string>", '
            '"reason": "<your internal reasoning, max 30 words>", '
            '"opening_message": "<your opening private message if initiating, otherwise empty>"}'
        )
        user = (
            f"Round {round_num} just ended.\n"
            f"Summary: {prior_synthesis[:500] if prior_synthesis else 'No summary yet.'}\n\n"
            f"Other participants: {others_desc}\n\n"
            "Do you want to open a private conversation? If yes, specify who and your opening message."
        )
        result = await get_completion_json(
            base_url=self.base_url, api_key=self.api_key, model=self.default_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6, max_tokens=512, agent_name=f"whisper-decision-{speaker['slug']}",
        )
        return result

    async def _agent_private_response(
        self, responder: dict, initiator: dict, opening_msg: str, round_num: int
    ) -> dict:
        """Ask an agent whether to accept a private thread and provide first response."""
        system = (
            f"You are {responder['name']}, {responder.get('role', '')}.\n"
            f"{initiator['name']} wants to speak with you privately (round {round_num}).\n"
            "You may accept or decline. If you accept, provide your response.\n\n"
            "IMPORTANT: Respond with ONLY a raw JSON object:\n"
            '{"accept_private": true/false, "reason": "<internal reasoning, max 20 words>", '
            '"response": "<your response message if accepting, or brief decline reason>"}'
        )
        user = f'{initiator["name"]} says privately: "{opening_msg}"'
        result = await get_completion_json(
            base_url=self.base_url, api_key=self.api_key, model=self.default_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6, max_tokens=400, agent_name=f"whisper-response-{responder['slug']}",
        )
        return result

    async def _agent_private_continue(
        self, speaker: dict, other: dict, thread_msgs: list[dict], round_num: int
    ) -> dict:
        """Generate a continuation message in an ongoing private thread."""
        history_text = "\n".join(
            f"{m['name']}: {m['content']}" for m in thread_msgs[-4:]
        )
        system = (
            f"You are {speaker['name']}, {speaker.get('role', '')}.\n"
            f"You are in a private conversation with {other['name']} (round {round_num}).\n"
            "Continue the conversation naturally. Be strategic but authentic.\n\n"
            "IMPORTANT: Respond with ONLY a raw JSON object:\n"
            '{"content": "<your next private message, max 100 words>"}'
        )
        result = await get_completion_json(
            base_url=self.base_url, api_key=self.api_key, model=self.default_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Conversation so far:\n{history_text}\n\nYour next message:"},
            ],
            temperature=0.7, max_tokens=300, agent_name=f"whisper-continue-{speaker['slug']}",
        )
        return result

    def _summarize_private_thread(
        self, thread_msgs: list[dict], agent_a: dict, agent_b: dict
    ) -> str:
        """Build a brief private context summary for injection into next public turns."""
        lines = [f"You spoke privately with {agent_b['name']} before this round."]
        for m in thread_msgs:
            lines.append(f"{m['name']}: {m['content'][:200]}")
        return "\n".join(lines)

    async def _persist_private_thread(
        self, initiator_slug: str, target_slug: str, round_opened: int, status: str = "open"
    ) -> int:
        """Persist a PrivateThread row and return its ID."""
        from ..models import PrivateThread
        from ..database import get_db_session_with_user
        db = get_db_session_with_user(self.user_id)
        try:
            thread = PrivateThread(
                session_id=self.session_id,
                initiator_slug=initiator_slug,
                target_slug=target_slug,
                round_opened=round_opened,
                status=status,
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
            return thread.id
        except Exception as e:
            self._log.error("Failed to persist private thread: %s", e)
            return -1
        finally:
            db.close()

    async def _persist_private_message(
        self, thread_id: int, speaker_slug: str, content: str,
        internal_reason: str = None, round_num: int = None, turn: int = None,
    ):
        """Persist a PrivateMessage row."""
        if thread_id < 0:
            return
        from ..models import PrivateMessage
        from ..database import get_db_session_with_user
        db = get_db_session_with_user(self.user_id)
        try:
            db.add(PrivateMessage(
                thread_id=thread_id, session_id=self.session_id,
                speaker_slug=speaker_slug, content=content,
                internal_reason=internal_reason, round_num=round_num, turn=turn,
            ))
            db.commit()
        except Exception as e:
            self._log.error("Failed to persist private message: %s", e)
        finally:
            db.close()

    async def _update_private_thread_status(self, thread_id: int, status: str):
        """Update a PrivateThread's status."""
        if thread_id < 0:
            return
        from ..models import PrivateThread
        from ..database import get_db_session_with_user
        db = get_db_session_with_user(self.user_id)
        try:
            t = db.query(PrivateThread).filter_by(id=thread_id).first()
            if t:
                t.status = status
                db.commit()
        except Exception as e:
            self._log.error("Failed to update private thread status: %s", e)
        finally:
            db.close()

    async def _extract_private_thread_memories(
        self,
        thread_msgs: list[dict],
        initiator: dict,
        target: dict,
        round_num: int,
    ):
        """CR-010 × CR-011: Silent observer extraction on a completed private thread.

        Sends the full private transcript to the LLM observer and persists
        AgentMemory rows for both participants with memory_type in
        {private_agreement, private_concession, private_intelligence}.
        Only called when feature_flag 'agent_memory' is also enabled.
        """
        if not thread_msgs:
            return

        transcript = "\n".join(
            f"{m['name']}: {m['content']}" for m in thread_msgs
        )
        system = (
            "You are a neutral observer analysing a private bilateral conversation "
            "between two stakeholders in a strategic wargame simulation.\n\n"
            "Extract memory candidates from this transcript. Focus on:\n"
            "- private_agreement: explicit or implicit agreements reached\n"
            "- private_concession: one party conceding a point or softening a position\n"
            "- private_intelligence: valuable information shared that changes the political landscape\n\n"
            "IMPORTANT: Respond with ONLY a raw JSON object:\n"
            '{"memory_candidates": ['
            '{"speaker_slug": "<slug>", "type": "<private_agreement|private_concession|private_intelligence>", '
            '"content": "<concise factual statement, max 50 words>", '
            '"related_agents": ["<slug>"], "salience": <0.5-1.0>}'
            "]}"
        )
        user = (
            f"Round {round_num} private thread between "
            f"{initiator['name']} ({initiator['slug']}) and "
            f"{target['name']} ({target['slug']}):\n\n"
            f"{transcript}"
        )
        try:
            result = await get_completion_json(
                base_url=self.base_url, api_key=self.api_key, model=self.default_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3, max_tokens=600, agent_name="whisper-observer",
            )
        except Exception as e:
            self._log.warning("Private thread observer extraction failed: %s", e)
            return

        candidates = result.get("memory_candidates", [])
        if not candidates:
            return

        from ..analytics.sbert import embed_texts
        from ..models import AgentMemory
        from ..database import get_db_session_with_user, settings as db_settings

        texts = [c["content"] for c in candidates]
        embeddings = await asyncio.get_running_loop().run_in_executor(
            None, embed_texts, texts
        )
        is_sqlite = db_settings.database_url.startswith("sqlite")

        db = get_db_session_with_user(self.user_id)
        try:
            for i, c in enumerate(candidates):
                speaker_slug = c.get("speaker_slug", initiator["slug"])
                raw_emb = embeddings[i] if embeddings else None
                if raw_emb is not None and is_sqlite:
                    raw_emb = json.dumps(raw_emb)
                db.add(AgentMemory(
                    project_id=self.project_id,
                    session_id=self.session_id,
                    speaker_slug=speaker_slug,
                    memory_type=c.get("type", "private_intelligence"),
                    content=c["content"],
                    structured_data=json.dumps({
                        "related_agents": c.get("related_agents", []),
                        "source_round": round_num,
                        "source": "private_thread",
                    }),
                    embedding=raw_emb,
                    salience=c.get("salience", 0.7),
                    round_num=round_num,
                    scope="session",
                ))
            db.commit()
            self._log.info(
                "Persisted %d private-thread memories (round %d, %s ↔ %s)",
                len(candidates), round_num, initiator["slug"], target["slug"],
            )
        except Exception as e:
            self._log.error("Failed to persist private thread memories: %s", e)
            db.rollback()
        finally:
            db.close()
