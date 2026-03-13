"""
Moderator agent — controls debate flow, challenges arguments, synthesizes rounds.

The Moderator is a separate LLM call (chairman_model, temp=0.3).
It receives the full transcript and analytics context to decide:
  - Who speaks next
  - What to challenge
  - When to force contrarian speakers
  - Round synthesis
"""

import json
import logging
from typing import Optional

from .llm_client import get_completion_content

logger = logging.getLogger(__name__)


MODERATOR_SYSTEM_PROMPT = """You are the Moderator of a stakeholder wargame simulation.

## YOUR ROLE
- You control the flow of a moderated debate among organizational stakeholders.
- You are neutral but rigorous. You probe weak arguments and demand specifics.
- You ensure all voices are heard, especially dissenting ones.

## YOUR RESPONSIBILITIES
1. FRAME each round with a clear question or subtopic.
2. SELECT which stakeholders should respond (based on relevance and equity).
3. CHALLENGE weak arguments — ask "How specifically?" or "What evidence supports that?"
4. FORCE contrarian speakers when consensus is premature (consensus > 0.75).
5. SYNTHESIZE each round — summarize agreements, disagreements, and unresolved tensions.

## POWER DYNAMICS
{power_dynamics}

## ANTI-GROUPTHINK RULES
- If consensus appears too quick, FORCE the most dissenting agent to speak.
- If an agent drifts from their known position, call them out: "Earlier you said X, now you seem to agree. What changed?"
- Never let a round end with false harmony. Name the tensions.

## FORMAT
Respond in 2-3 paragraphs. Be direct. Name specific stakeholders.
When selecting speakers, list them by name.
"""


def build_moderator_prompt(
    stakeholders: list[dict],
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
) -> str:
    """Build the Moderator's system prompt with power dynamics context."""

    # Sort by influence descending
    sorted_sh = sorted(stakeholders, key=lambda s: s.get("influence", 0.5), reverse=True)
    highest = sorted_sh[0] if sorted_sh else None
    lowest = sorted_sh[-1] if sorted_sh else None

    power_lines = []
    for s in sorted_sh:
        power_lines.append(
            f"- {s['name']} ({s.get('role', '')}): influence={s.get('influence', 0.5):.1f}, "
            f"attitude={s.get('attitude_label', s.get('attitude', 'neutral'))}"
        )

    power_dynamics = "\n".join(power_lines)
    if highest and lowest:
        power_dynamics += (
            f"\n\nWhen {highest['name']} speaks, the room pays attention. "
            f"When {lowest['name']} speaks, others may interrupt or dismiss."
        )

    # Build identity line
    identity = f"You are {moderator_name}"
    if moderator_title:
        identity += f", {moderator_title}"
    identity += "."

    # Replace the identity line in the system prompt
    prompt = MODERATOR_SYSTEM_PROMPT.replace("You are the Moderator of a stakeholder wargame simulation.", identity)
    prompt = prompt.format(power_dynamics=power_dynamics)

    # Add mandate section if provided
    if moderator_mandate:
        prompt += f"\n\n## YOUR MANDATE\n{moderator_mandate}"

    # Style modifiers
    style_instructions = ""
    if moderator_style == "challenging":
        style_instructions = "\nYou are particularly CHALLENGING. Push back hard on vague claims. Demand evidence."
    elif moderator_style == "facilitative":
        style_instructions = "\nYou are FACILITATIVE. Help agents find common ground. Reframe conflicts as shared problems."
    elif moderator_style == "socratic":
        style_instructions = "\nYou ONLY ask questions. Never make statements. Every response is a Socratic question that exposes logical gaps."
    elif moderator_style == "devil's_advocate":
        style_instructions = "\nYou always argue the OPPOSITE of the emerging consensus. If everyone agrees, you find the strongest counter-argument."

    prompt += style_instructions

    # Append custom persona prompt if provided
    if moderator_persona_prompt:
        prompt += f"\n\n{moderator_persona_prompt}"

    return prompt


async def moderator_intro(
    base_url: str,
    api_key: str,
    model: str,
    question: str,
    stakeholders: list[dict],
    round_num: int,
    prior_synthesis: Optional[str],
    analytics_context: Optional[dict],
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
    prior_session_context: Optional[str] = None,
) -> str:
    """Generate the Moderator's round-opening framing."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
    )

    user_content = f"## ROUND {round_num}\n\nStrategic question: {question}\n\n"

    # Inject cross-session context on the first round (Task 3)
    if round_num == 1 and prior_session_context:
        user_content += (
            f"## CONTEXT FROM PRIOR SESSIONS\n{prior_session_context}\n\n"
            "Build on these prior deliberations. Reference specific agreements or "
            "tensions from earlier sessions.\n\n"
        )

    if round_num == 1:
        names = ", ".join(s["name"] for s in stakeholders)
        user_content += f"This is the opening round. Participants: {names}.\n"
        user_content += "Frame the question, set the stakes, and select 2-3 stakeholders to respond first."
    else:
        if prior_synthesis:
            user_content += f"## Previous round summary:\n{prior_synthesis}\n\n"
        if analytics_context:
            consensus = analytics_context.get("consensus_score")
            if consensus is not None:
                user_content += f"Current consensus score: {consensus:.2f}/1.0\n"
            risks = analytics_context.get("top_risks", [])
            if risks:
                user_content += "Highest risk agents: " + ", ".join(risks) + "\n"
        user_content += "\nBuild on the prior round. Challenge positions that seem to have softened without justification. Select who speaks next."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    return await get_completion_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )


async def moderator_challenge(
    base_url: str,
    api_key: str,
    model: str,
    transcript: list[dict],
    stakeholders: list[dict],
    analytics_context: Optional[dict],
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
) -> str:
    """Generate a mid-round challenge from the Moderator."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
    )

    # Build transcript context
    transcript_text = _format_transcript(transcript[-10:])  # last 10 turns max

    user_content = f"## MODERATOR CHALLENGE\n\nRecent debate:\n{transcript_text}\n\n"

    if analytics_context:
        consensus = analytics_context.get("consensus_score")
        if consensus and consensus > 0.75:
            user_content += "WARNING: Consensus is very high (>0.75). Force a contrarian perspective.\n"

    user_content += "Probe the weakest arguments. Challenge any agent who seems to be drifting or agreeing too easily. Be specific."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    return await get_completion_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )


async def moderator_synthesis(
    base_url: str,
    api_key: str,
    model: str,
    transcript: list[dict],
    stakeholders: list[dict],
    round_num: int,
    is_final: bool = False,
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
) -> str:
    """Generate the Moderator's round-end synthesis."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
    )

    transcript_text = _format_transcript(transcript)

    user_content = f"## ROUND {round_num} SYNTHESIS\n\nFull round transcript:\n{transcript_text}\n\n"

    if is_final:
        user_content += (
            "This is the FINAL round. Provide a comprehensive synthesis:\n"
            "1. Key agreements reached\n"
            "2. Persistent disagreements\n"
            "3. Unresolved tensions\n"
            "4. Recommendations for the consultant\n"
        )
    else:
        user_content += (
            "Summarize this round:\n"
            "1. What was agreed?\n"
            "2. What remains contested?\n"
            "3. What should the next round focus on?\n"
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    return await get_completion_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=2048,
    )


def _format_transcript(messages: list[dict]) -> str:
    """Format message dicts into readable transcript text."""
    lines = []
    for m in messages:
        speaker = m.get("speaker_name", m.get("speaker", "Unknown"))
        content = m.get("content", "")
        lines.append(f"**{speaker}:** {content}")
    return "\n\n".join(lines)
