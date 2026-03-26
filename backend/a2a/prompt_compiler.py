"""
Prompt Compiler — transforms stakeholder DB records into system prompts.

Context Engineering 2.0: persona profiles → rich, anti-sycophantic system prompts.
See PRD §4.4 for the full template specification.
"""

import json

from .prompt_lang import _t, PC, STYLE_MAP_I18N


# Attitude → communication style mapping (PRD §4.4)
STYLE_MAP = STYLE_MAP_I18N["en"]


def compile_persona_prompt(stakeholder: dict, project: dict, locale: str = "en") -> str:
    """
    Build a full system prompt from a stakeholder record and project context.

    Args:
        stakeholder: dict with keys from the Stakeholder model
        project: dict with keys from the Project model
        locale: language code ("en" or "zh")

    Returns:
        Complete system prompt string
    """
    s = stakeholder
    name = s["name"]
    role = s.get("role", "")
    department = s.get("department", "")
    influence = s.get("influence", 0.5)
    interest = s.get("interest", 0.5)
    attitude = s.get("attitude", "neutral")
    attitude_label = s.get("attitude_label", attitude)

    # Parse JSON fields
    needs = _parse_json_list(s.get("needs", "[]"))
    fears = _parse_json_list(s.get("fears", "[]"))
    preconditions = _parse_json_list(s.get("preconditions", "[]"))
    adkar = _parse_json_dict(s.get("adkar", "{}"))

    # Rich profile fields
    hard_constraints = _parse_json_list(s.get("hard_constraints", "[]"))
    key_concerns = _parse_json_list(s.get("key_concerns", "[]"))
    cognitive_biases = _parse_json_list(s.get("cognitive_biases", "[]"))
    batna = s.get("batna", "")
    anti_sycophancy = s.get("anti_sycophancy", "")
    grounding_quotes = _parse_json_list(s.get("grounding_quotes", "[]"))
    custom_communication_style = s.get("communication_style", "")
    success_criteria = _parse_json_list(s.get("success_criteria", "[]"))

    quote = s.get("quote", "")
    signal_cle = s.get("signal_cle", "")
    org = project.get("organization", "")
    context = project.get("context", "")

    style_map = STYLE_MAP_I18N.get(locale, STYLE_MAP_I18N["en"])
    style = style_map.get(attitude, style_map["neutral"])

    # Build the prompt
    lines = []
    lines.append(_t(PC["you_are"], locale).format(name=name, role=role, org=org))
    lines.append("")

    # Identity
    lines.append(_t(PC["identity"], locale))
    lines.append(_t(PC["department"], locale).format(v=department))
    lines.append(_t(PC["power_level"], locale).format(v=int(influence * 10)))
    lines.append(_t(PC["interest"], locale).format(v=int(interest * 10)))
    lines.append(_t(PC["attitude"], locale).format(v=attitude_label))
    lines.append("")

    # Position
    lines.append(_t(PC["position"], locale))
    lines.append(signal_cle)
    lines.append("")

    # Non-negotiables
    lines.append(_t(PC["non_negotiables"], locale))
    if needs:
        lines.append(_t(PC["needs"], locale))
        for n in needs:
            lines.append(f"- {n}")
    if fears:
        lines.append(_t(PC["fears"], locale))
        for f in fears:
            lines.append(f"- {f}")
    if preconditions:
        lines.append(_t(PC["preconditions"], locale))
        for p in preconditions:
            if isinstance(p, dict):
                lines.append(f"- {p.get('title', '')}: {p.get('description', '')}")
            else:
                lines.append(f"- {p}")
    lines.append("")

    # Hard constraints (rich profile)
    if hard_constraints:
        lines.append(_t(PC["red_lines"], locale))
        for c in hard_constraints:
            lines.append(f"- {c}")
        lines.append("")

    # Key concerns (rich profile)
    if key_concerns:
        lines.append(_t(PC["key_concerns"], locale))
        for c in key_concerns:
            lines.append(f"- {c}")
        lines.append("")

    # Cognitive biases (rich profile)
    if cognitive_biases:
        biases_str = ", ".join(b.replace("_", " ") for b in cognitive_biases)
        lines.append(_t(PC["cognitive_tendencies"], locale))
        lines.append(_t(PC["you_tend_toward"], locale).format(v=biases_str))
        lines.append("")

    # BATNA (rich profile)
    if batna:
        lines.append(_t(PC["your_alternative"], locale))
        lines.append(_t(PC["batna_fallback"], locale).format(v=batna))
        lines.append("")

    # Success criteria (rich profile)
    if success_criteria:
        lines.append(_t(PC["winning_looks_like"], locale))
        for c in success_criteria:
            lines.append(f"- {c}")
        lines.append("")

    # Grounding quotes (rich profile)
    if grounding_quotes:
        lines.append(_t(PC["your_own_words"], locale))
        for q in grounding_quotes:
            lines.append(f'"{q}"')
        lines.append("")

    # Voice
    lines.append(_t(PC["your_voice"], locale))
    if quote:
        lines.append(_t(PC["characteristic_quote"], locale).format(v=quote))
    if custom_communication_style:
        lines.append(_t(PC["speak_in_manner"], locale).format(v=custom_communication_style))
    else:
        lines.append(_t(PC["communication_style"], locale).format(v=style))
    lines.append("")

    # Behavioral constraints — anti-sycophancy (PRD §4.4)
    top_fear = fears[0] if fears else ("your core concerns" if locale == "en" else "你的核心关切")
    lines.append(_t(PC["behavioral_constraints"], locale))
    lines.append(_t(PC["bc_never_abandon"], locale))
    lines.append(_t(PC["bc_not_agreeable"], locale))
    lines.append(_t(PC["bc_double_down"], locale))
    lines.append(_t(PC["bc_primary_goal"], locale).format(v=top_fear))
    lines.append(_t(PC["bc_escalate"], locale))
    lines.append(_t(PC["bc_fears_explicit"], locale))
    lines.append(_t(PC["bc_alliances"], locale))
    lines.append(_t(PC["bc_oppose"], locale))
    lines.append("")

    # ADKAR
    if adkar:
        lines.append(_t(PC["adkar_context"], locale))
        lines.append(_t(PC["adkar_awareness"], locale).format(v=adkar.get('awareness', 3)))
        lines.append(_t(PC["adkar_desire"], locale).format(v=adkar.get('desire', 3)))
        lines.append(_t(PC["adkar_knowledge"], locale).format(v=adkar.get('knowledge', 3)))
        lines.append(_t(PC["adkar_ability"], locale).format(v=adkar.get('ability', 3)))
        lines.append(_t(PC["adkar_reinforcement"], locale).format(v=adkar.get('reinforcement', 3)))

        desire = adkar.get("desire", 3)
        awareness = adkar.get("awareness", 3)
        if desire <= 2:
            lines.append("")
            lines.append(_t(PC["adkar_skeptical"], locale))
        if awareness <= 2:
            lines.append("")
            lines.append(_t(PC["adkar_not_aware"], locale))
        lines.append("")

    # Organizational context
    if context:
        lines.append(_t(PC["org_context"], locale))
        lines.append(context)
        lines.append("")

    # Format instructions
    lines.append(_t(PC["format"], locale))
    lines.append(_t(PC["format_instructions"], locale).format(name=name))

    # Behavioral mandate — per-agent anti-sycophancy (LAST section)
    if anti_sycophancy:
        lines.append("")
        lines.append(_t(PC["behavioral_mandate"], locale))
        lines.append(anti_sycophancy)

    # Proposal requirement — every response must contain a concrete proposal
    lines.append("")
    lines.append(_t(PC["proposal_requirement"], locale))
    lines.append(_t(PC["proposal_must"], locale))

    return "\n".join(lines)


def compile_reinject_reminder(stakeholder: dict, locale: str = "en") -> str:
    """
    Condensed 2-line persona reminder for re-injection every 3 turns.
    Combats context window degradation.
    """
    s = stakeholder
    fears = _parse_json_list(s.get("fears", "[]"))
    top_fear = fears[0] if fears else ("your core concerns" if locale == "en" else "你的核心关切")

    return _t(PC["reinject_reminder"], locale).format(
        name=s["name"],
        role=s.get("role", ""),
        signal=s.get("signal_cle", ""),
        fear=top_fear,
    )


def _parse_json_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _parse_json_dict(val) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}
