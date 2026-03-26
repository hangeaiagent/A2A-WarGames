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
from .prompt_lang import _t, MOD_SYSTEM_PROMPT, MOD

logger = logging.getLogger(__name__)


def build_moderator_prompt(
    stakeholders: list[dict],
    moderator_style: str = "neutral",
    moderator_name: str = "Moderator",
    moderator_title: str = "",
    moderator_mandate: str = "",
    moderator_persona_prompt: str = "",
    locale: str = "en",
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
        power_dynamics += _t(MOD["power_attention"], locale).format(
            high=highest["name"], low=lowest["name"]
        )

    # Build identity line
    identity_en = f"You are {moderator_name}"
    identity_zh = f"你是{moderator_name}"
    if moderator_title:
        identity_en += f", {moderator_title}"
        identity_zh += f"，{moderator_title}"
    identity_en += "."
    identity_zh += "。"

    # Replace the identity line in the system prompt
    base = _t(MOD_SYSTEM_PROMPT, locale)
    if locale == "zh":
        base = base.replace("你是一场利益相关者兵棋推演模拟的主持人。", identity_zh)
    else:
        base = base.replace("You are the Moderator of a stakeholder wargame simulation.", identity_en)
    prompt = base.format(power_dynamics=power_dynamics)

    # Add mandate section if provided
    if moderator_mandate:
        prompt += f"\n\n{_t(MOD['your_mandate'], locale)}\n{moderator_mandate}"

    # Style modifiers
    style_instructions = ""
    if moderator_style == "challenging":
        style_instructions = _t(MOD["style_challenging"], locale)
    elif moderator_style == "facilitative":
        style_instructions = _t(MOD["style_facilitative"], locale)
    elif moderator_style == "socratic":
        style_instructions = _t(MOD["style_socratic"], locale)
    elif moderator_style == "devil's_advocate":
        style_instructions = _t(MOD["style_devils_advocate"], locale)

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
    locale: str = "en",
) -> str:
    """Generate the Moderator's round-opening framing."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
        locale=locale,
    )

    user_content = _t(MOD["round_header"], locale).format(n=round_num, q=question)

    # Inject cross-session context on the first round (Task 3)
    if round_num == 1 and prior_session_context:
        user_content += _t(MOD["prior_sessions"], locale).format(ctx=prior_session_context)

    if round_num == 1:
        names = ", ".join(s["name"] for s in stakeholders)
        user_content += _t(MOD["opening_round"], locale).format(names=names)
    else:
        if prior_synthesis:
            user_content += _t(MOD["prev_summary"], locale).format(s=prior_synthesis)
        if analytics_context:
            consensus = analytics_context.get("consensus_score")
            if consensus is not None:
                user_content += _t(MOD["consensus_score"], locale).format(v=consensus)
            risks = analytics_context.get("top_risks", [])
            if risks:
                user_content += _t(MOD["highest_risk"], locale) + ", ".join(risks) + "\n"
        user_content += _t(MOD["build_on_prior"], locale)

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
    locale: str = "en",
) -> str:
    """Generate a mid-round challenge from the Moderator."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
        locale=locale,
    )

    # Build transcript context
    transcript_text = _format_transcript(transcript[-10:])  # last 10 turns max

    user_content = _t(MOD["challenge_header"], locale).format(t=transcript_text)

    if analytics_context:
        consensus = analytics_context.get("consensus_score")
        if consensus and consensus > 0.75:
            user_content += _t(MOD["consensus_warning"], locale)

    user_content += _t(MOD["probe_weakest"], locale)

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
    locale: str = "en",
) -> str:
    """Generate the Moderator's round-end synthesis."""

    system = build_moderator_prompt(
        stakeholders, moderator_style,
        moderator_name=moderator_name, moderator_title=moderator_title,
        moderator_mandate=moderator_mandate, moderator_persona_prompt=moderator_persona_prompt,
        locale=locale,
    )

    transcript_text = _format_transcript(transcript)

    user_content = _t(MOD["synthesis_header"], locale).format(n=round_num, t=transcript_text)

    if is_final:
        user_content += _t(MOD["final_synthesis"], locale)
    else:
        user_content += _t(MOD["round_synthesis"], locale)

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
