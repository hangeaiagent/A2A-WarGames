"""
Thought Chains — Concordia-inspired multi-step moderator reasoning.

Replaces one-shot ``moderator_challenge()`` and ``moderator_synthesis()``
with chained LLM reasoning steps where each step conditions on the previous,
building an ``InteractiveDocument``-style accumulated Q&A context.

Inspired by Concordia's ``run_chain_of_thought``, ``determine_success_and_why``,
``maybe_inject_narrative_push``, and ``AccountForAgencyOfOthers``.

Feature flag: ``concordia_engine``
"""

from __future__ import annotations

import logging
from typing import Optional

from ..llm_client import get_completion_content

logger = logging.getLogger(__name__)


class ReasoningChain:
    """Accumulates multi-step LLM reasoning (like Concordia's InteractiveDocument).

    Each question sees all prior Q&A, producing increasingly informed answers.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.steps: list[dict] = []  # {"question": ..., "answer": ...}

    @property
    def context(self) -> str:
        """Return accumulated reasoning context."""
        parts = []
        for i, step in enumerate(self.steps, 1):
            parts.append(f"Step {i} — {step['question']}")
            parts.append(f"Answer: {step['answer']}\n")
        return "\n".join(parts)

    async def ask(self, question: str, *, premise: str = "") -> str:
        """Ask a question, conditioning on all prior reasoning steps.

        Parameters
        ----------
        question:
            The question to ask the LLM.
        premise:
            Optional additional context for this specific question.

        Returns
        -------
        str
            The LLM's answer.
        """
        prior = self.context
        user_content = ""
        if premise:
            user_content += f"## Context\n{premise}\n\n"
        if prior:
            user_content += f"## Prior Reasoning\n{prior}\n\n"
        user_content += f"## Current Question\n{question}\n\nAnswer concisely (2-3 sentences):"

        try:
            answer = await get_completion_content(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            answer = (answer or "").strip() or "(no answer)"
        except Exception:
            logger.warning("Thought chain step failed: %s", question, exc_info=True)
            answer = "(reasoning step failed)"

        self.steps.append({"question": question, "answer": answer})
        return answer


def _format_recent_transcript(transcript: list[dict], max_turns: int = 10) -> str:
    """Format the most recent transcript entries for LLM context."""
    recent = transcript[-max_turns:]
    parts = []
    for msg in recent:
        name = msg.get("speaker_name", msg.get("speaker", "Unknown"))
        content = msg.get("content", "")[:500]
        parts.append(f"**{name}:** {content}")
    return "\n\n".join(parts)


async def moderator_challenge_with_reasoning(
    *,
    base_url: str,
    api_key: str,
    model: str,
    transcript: list[dict],
    stakeholders: list[dict],
    analytics_context: Optional[dict] = None,
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
) -> dict:
    """Multi-step moderator challenge with transparent reasoning chain.

    Returns
    -------
    dict
        ``{"intervention": str, "reasoning": list[dict], "should_inject_event": bool}``
    """
    transcript_text = _format_recent_transcript(transcript, max_turns=10)

    consensus_score = (analytics_context or {}).get("consensus_score")
    analytics_note = ""
    if consensus_score is not None:
        analytics_note = f"\nCurrent consensus score: {consensus_score:.2f}"

    system = (
        f"You are {moderator_name}, a rigorous debate moderator. "
        f"Style: {moderator_style}. "
        "You analyze debate dynamics and intervene when needed."
    )

    chain = ReasoningChain(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system,
        temperature=0.3,
    )

    premise = f"## Recent Debate\n{transcript_text}{analytics_note}"

    # Step 1: Assess debate state
    await chain.ask(
        "Is the debate making genuine progress, or are agents repeating "
        "the same arguments without advancing? Are there unaddressed tensions?",
        premise=premise,
    )

    # Step 2: Check consensus genuineness
    await chain.ask(
        "Is any apparent agreement genuine, or could it be sycophantic "
        "agreement? Are agents agreeing to avoid conflict rather than "
        "because they truly accept the position?"
    )

    # Step 3: Identify weakest arguments
    await chain.ask(
        "Which arguments are weakest or lack supporting evidence? "
        "Which claims have gone unchallenged that should be tested?"
    )

    # Step 4: Check for loop/repetition
    loop_answer = await chain.ask(
        "Are agents going in circles on any particular topic? "
        "If so, what new framing or constraint could break the loop?"
    )

    should_inject = "circles" in loop_answer.lower() or "repetit" in loop_answer.lower()

    # Step 5: Generate intervention
    intervention = await chain.ask(
        "Based on your analysis, compose your moderator intervention. "
        "Be direct, specific, and challenge by name if needed. "
        "If the debate is looping, introduce a new constraint or reframe."
    )

    return {
        "intervention": intervention,
        "reasoning": chain.steps,
        "should_inject_event": should_inject,
    }


async def resolve_round_outcome(
    *,
    base_url: str,
    api_key: str,
    model: str,
    transcript: list[dict],
    round_num: int,
    stakeholders: list[dict],
    moderator_name: str = "Moderator",
) -> dict:
    """Resolve canonical round outcomes via thought chain reasoning.

    Inspired by Concordia's ``EventResolution`` component: transforms putative
    events (what agents *tried* to claim) into canonical resolved events
    (what *actually happened*).

    Returns
    -------
    dict
        ``{"canonical_outcome": str, "proposals": str, "reasoning": list[dict]}``
    """
    round_messages = [m for m in transcript if m.get("round") == round_num]
    transcript_text = _format_recent_transcript(round_messages, max_turns=20)

    system = (
        f"You are {moderator_name}, adjudicating the official record of "
        "a stakeholder debate round. Determine what actually happened — "
        "not what agents *claimed* happened."
    )

    chain = ReasoningChain(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system,
        temperature=0.2,
    )

    premise = f"## Round {round_num} Transcript\n{transcript_text}"

    # Step 1: List proposals
    proposals = await chain.ask(
        "List every concrete proposal made in this round. "
        "Include the proposer's name and the specific terms.",
        premise=premise,
    )

    # Step 2: Verify agency — did agents actually agree?
    await chain.ask(
        "For each proposal, verify: did the affected agents actually agree, "
        "or did someone claim consensus that doesn't exist? "
        "Be precise about who agreed and who didn't."
    )

    # Step 3: Canonical outcome
    canonical = await chain.ask(
        "Write the canonical outcome of this round in 2-3 sentences. "
        "Only include what was genuinely agreed or decided. "
        "Clearly state what remains unresolved."
    )

    return {
        "canonical_outcome": canonical,
        "proposals": proposals,
        "reasoning": chain.steps,
    }
