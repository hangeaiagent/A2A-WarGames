"""
Self-Reflection — Concordia-inspired pre-turn introspection.

Before generating a response, the agent asks itself configurable questions
about its own recent memories and history, grounding identity and
preventing persona drift.

Inspired by Concordia's ``QuestionOfRecentMemories`` component and its
specialisations ``SelfPerception``, ``SituationPerception``, and
``PersonBySituation``.

Feature flag: ``concordia_engine``
"""

from __future__ import annotations

import logging
from typing import Optional

from ..llm_client import get_completion_content

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Default reflection questions (inspired by Concordia prefab agents)
# ------------------------------------------------------------------

DEFAULT_REFLECTION_QUESTIONS: list[dict] = [
    {
        "label": "position_check",
        "question": (
            "Given everything that has happened in this debate so far, "
            "has {agent_name}'s stance changed from their original position "
            "(\"{baseline}\")? If so, why and how far?"
        ),
        "answer_prefix": "{agent_name}'s current stance: ",
    },
    {
        "label": "concession_review",
        "question": (
            "What concessions has {agent_name} already made in this debate? "
            "What would {agent_name} absolutely refuse to concede?"
        ),
        "answer_prefix": "Concessions so far: ",
    },
    {
        "label": "persona_grounding",
        "question": (
            "What kind of person is {agent_name}? "
            "What would someone in {agent_name}'s role with their fears "
            "and priorities do in this situation?"
        ),
        "answer_prefix": "{agent_name} would: ",
    },
]


async def build_self_reflection(
    *,
    base_url: str,
    api_key: str,
    model: str,
    agent_name: str,
    agent_slug: str,
    baseline_position: str,
    recent_memories: list[str],
    conversation_history: list[dict],
    questions: Optional[list[dict]] = None,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    """Generate a self-reflection block for injection into the agent's context.

    Parameters
    ----------
    base_url, api_key, model:
        LLM connection settings.
    agent_name:
        Display name of the speaking agent.
    agent_slug:
        Slug identifier for the agent.
    baseline_position:
        The agent's original ``signal_cle`` / starting position text.
    recent_memories:
        Formatted list of recent memory strings (e.g. ``["- [concession] …"]``).
    conversation_history:
        The agent's last few dialogue messages (already stored in ``agent_histories``).
    questions:
        Override the default reflection question set.  Each dict should have
        ``label``, ``question`` (with ``{agent_name}`` / ``{baseline}`` placeholders),
        and ``answer_prefix``.
    temperature:
        LLM temperature for introspection (low by default for determinism).
    max_tokens:
        Max tokens per reflection answer.

    Returns
    -------
    str
        A formatted ``[SELF-REFLECTION]`` block ready for system-prompt injection.
        Returns an empty string if LLM calls fail or the agent has no history.
    """
    if not conversation_history:
        return ""

    questions = questions or DEFAULT_REFLECTION_QUESTIONS

    # Build a concise context from recent memories + last statements
    memory_ctx = "\n".join(recent_memories[-10:]) if recent_memories else "(no memories yet)"
    history_ctx = "\n".join(
        f"- {m['role'].upper()}: {m['content'][:200]}"
        for m in conversation_history[-6:]
    )

    reflection_parts: list[str] = []

    for q in questions:
        question_text = q["question"].format(
            agent_name=agent_name,
            baseline=baseline_position or "unknown",
        )
        prefix = q["answer_prefix"].format(agent_name=agent_name)

        system = (
            f"You are analyzing the behavior of {agent_name} in a stakeholder debate. "
            "Answer concisely in 1-2 sentences."
        )
        user_content = (
            f"## Recent Memories\n{memory_ctx}\n\n"
            f"## Recent Statements\n{history_ctx}\n\n"
            f"## Question\n{question_text}\n\n"
            f"Begin your answer with: {prefix}"
        )

        try:
            answer = await get_completion_content(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if answer and answer.strip():
                reflection_parts.append(f"- **{q['label']}**: {answer.strip()}")
        except Exception:
            logger.warning(
                "Self-reflection question '%s' failed for %s — skipping",
                q["label"], agent_slug, exc_info=True,
            )

    if not reflection_parts:
        return ""

    return (
        "[SELF-REFLECTION — Review before responding]\n"
        + "\n".join(reflection_parts)
        + "\n"
    )
