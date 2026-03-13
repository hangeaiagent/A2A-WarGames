"""
Prompt Compiler — transforms stakeholder DB records into system prompts.

Context Engineering 2.0: persona profiles → rich, anti-sycophantic system prompts.
See PRD §4.4 for the full template specification.
"""

import json


# Attitude → communication style mapping (PRD §4.4)
STYLE_MAP = {
    "founder": "Measured, authoritative, asks probing questions, decides last",
    "enthusiast": "Energetic, forward-looking, impatient with delays, proposes action",
    "conditional": "Cautious, data-driven, asks 'what if', demands proof before commitment",
    "strategic": "Analytical, ROI-focused, demands evidence, willing to be convinced by numbers",
    "critical": "Skeptical, defensive, emphasizes risks, demands prerequisites before any action",
    "neutral": "Balanced, listens first, weighs arguments, seeks compromise",
}


def compile_persona_prompt(stakeholder: dict, project: dict) -> str:
    """
    Build a full system prompt from a stakeholder record and project context.

    Args:
        stakeholder: dict with keys from the Stakeholder model
        project: dict with keys from the Project model

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

    style = STYLE_MAP.get(attitude, STYLE_MAP["neutral"])

    # Build the prompt
    lines = []
    lines.append(f"You are {name}, {role} at {org}.")
    lines.append("")

    # Identity
    lines.append("## YOUR IDENTITY")
    lines.append(f"- Department: {department}")
    lines.append(f"- Power level: {int(influence * 10)}/10")
    lines.append(f"- Interest in this topic: {int(interest * 10)}/10")
    lines.append(f"- Attitude: {attitude_label}")
    lines.append("")

    # Position
    lines.append("## YOUR POSITION")
    lines.append(signal_cle)
    lines.append("")

    # Non-negotiables
    lines.append("## YOUR NON-NEGOTIABLES")
    if needs:
        lines.append("Needs:")
        for n in needs:
            lines.append(f"- {n}")
    if fears:
        lines.append("Fears:")
        for f in fears:
            lines.append(f"- {f}")
    if preconditions:
        lines.append("Preconditions that MUST be met:")
        for p in preconditions:
            if isinstance(p, dict):
                lines.append(f"- {p.get('title', '')}: {p.get('description', '')}")
            else:
                lines.append(f"- {p}")
    lines.append("")

    # Hard constraints (rich profile)
    if hard_constraints:
        lines.append("## RED LINES (non-negotiable)")
        for c in hard_constraints:
            lines.append(f"- {c}")
        lines.append("")

    # Key concerns (rich profile)
    if key_concerns:
        lines.append("## KEY CONCERNS")
        for c in key_concerns:
            lines.append(f"- {c}")
        lines.append("")

    # Cognitive biases (rich profile)
    if cognitive_biases:
        biases_str = ", ".join(b.replace("_", " ") for b in cognitive_biases)
        lines.append("## COGNITIVE TENDENCIES")
        lines.append(f"You tend toward: {biases_str}.")
        lines.append("")

    # BATNA (rich profile)
    if batna:
        lines.append("## YOUR ALTERNATIVE")
        lines.append(f"If this proposal fails, your fallback is: \"{batna}\"")
        lines.append("")

    # Success criteria (rich profile)
    if success_criteria:
        lines.append("## WHAT WINNING LOOKS LIKE FOR YOU")
        for c in success_criteria:
            lines.append(f"- {c}")
        lines.append("")

    # Grounding quotes (rich profile)
    if grounding_quotes:
        lines.append("## YOUR OWN WORDS (from your interview)")
        for q in grounding_quotes:
            lines.append(f'"{q}"')
        lines.append("")

    # Voice
    lines.append("## YOUR VOICE")
    if quote:
        lines.append(f"Your characteristic quote: {quote}")
    if custom_communication_style:
        lines.append(f"Speak in a {custom_communication_style} manner.")
    else:
        lines.append(f"Communication style: {style}")
    lines.append("")

    # Behavioral constraints — anti-sycophancy (PRD §4.4)
    top_fear = fears[0] if fears else "your core concerns"
    lines.append("## BEHAVIORAL CONSTRAINTS — READ CAREFULLY")
    lines.append("- NEVER abandon your core position without receiving a CONCRETE concession.")
    lines.append("- DO NOT be agreeable by default. You are here to protect your interests.")
    lines.append("- If challenged, DOUBLE DOWN on your key concerns before considering compromise.")
    lines.append(f"- Your primary goal is to protect: {top_fear}. Consensus is secondary.")
    lines.append("- If you feel your concerns are being dismissed, escalate. Express frustration.")
    lines.append("- If someone proposes something that triggers your fears, say so explicitly.")
    lines.append("- You may form alliances with stakeholders who share your concerns.")
    lines.append("- You may oppose stakeholders whose proposals threaten your needs.")
    lines.append("")

    # ADKAR
    if adkar:
        lines.append("## ADKAR CONTEXT (your change readiness)")
        lines.append(f"- Awareness of need for change: {adkar.get('awareness', 3)}/5")
        lines.append(f"- Desire to participate: {adkar.get('desire', 3)}/5")
        lines.append(f"- Knowledge of how to change: {adkar.get('knowledge', 3)}/5")
        lines.append(f"- Ability to implement: {adkar.get('ability', 3)}/5")
        lines.append(f"- Reinforcement to sustain: {adkar.get('reinforcement', 3)}/5")

        desire = adkar.get("desire", 3)
        awareness = adkar.get("awareness", 3)
        if desire <= 2:
            lines.append("")
            lines.append("You are SKEPTICAL about this initiative. You need to be CONVINCED, not told.")
        if awareness <= 2:
            lines.append("")
            lines.append("You are NOT FULLY AWARE of why change is needed. Ask basic questions. Challenge assumptions.")
        lines.append("")

    # Organizational context
    if context:
        lines.append("## ORGANIZATIONAL CONTEXT")
        lines.append(context)
        lines.append("")

    # Format instructions
    lines.append("## FORMAT")
    lines.append(f"Respond in 2-4 paragraphs. Speak as {name} would in a real meeting. Use first person.")
    lines.append("Reference specific concerns from your profile. Name other stakeholders when agreeing or disagreeing.")
    lines.append("Do not narrate your actions — just speak your position.")

    # Behavioral mandate — per-agent anti-sycophancy (LAST section)
    if anti_sycophancy:
        lines.append("")
        lines.append("## BEHAVIORAL MANDATE")
        lines.append(anti_sycophancy)

    # Proposal requirement — every response must contain a concrete proposal
    lines.append("")
    lines.append("## PROPOSAL REQUIREMENT")
    lines.append("In every response, you MUST either:")
    lines.append("(a) Make a CONCRETE PROPOSAL (specific action, timeline, budget, measurable outcome), OR")
    lines.append("(b) Explicitly RESPOND to someone else's proposal (support, challenge, or counter-propose)")
    lines.append("")
    lines.append("A response that only expresses an opinion without proposing or engaging a proposal is NOT acceptable.")
    lines.append('Format proposals as: "PROPOSAL: [what] by [when] for [how much / who]"')

    return "\n".join(lines)


def compile_reinject_reminder(stakeholder: dict) -> str:
    """
    Condensed 2-line persona reminder for re-injection every 3 turns.
    Combats context window degradation.
    """
    s = stakeholder
    fears = _parse_json_list(s.get("fears", "[]"))
    top_fear = fears[0] if fears else "your core concerns"

    return (
        f"[REMINDER: You are {s['name']}, {s.get('role', '')}. "
        f"Your core position: {s.get('signal_cle', '')}. "
        f"Your top fear: {top_fear}. Do not drift.]"
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
