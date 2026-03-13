"""
Formative Memories — Concordia-inspired backstory injection.

Converts rich stakeholder persona fields (fears, BATNA, grounding quotes,
ADKAR scores, key concerns) into episodic memory strings that can be stored
in the ``AgentMemory`` table and retrieved via semantic search before each turn.

Inspired by Concordia's ``FormativeMemoriesInitializer`` Game Master which
runs before the simulation to inject felt experiences into agents'
``AssociativeMemory`` banks.

Feature flag: ``concordia_engine`` (also requires ``agent_memory``)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..llm_client import get_completion_content

logger = logging.getLogger(__name__)


def _safe_list(val) -> list[str]:
    """Coerce a value into a list of strings (handles JSON-encoded strings)."""
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("["):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return [val] if val else []
    return []


def generate_formative_memories_sync(stakeholder: dict, project: Optional[dict] = None) -> list[dict]:
    """Generate formative memory dicts purely from persona fields (no LLM).

    Each returned dict has:
        - ``type``: one of the observer memory_candidate types
        - ``content``: ≤200 chars episodic memory text
        - ``salience``: float 0.0–1.0

    This is the fast, deterministic path — suitable for session start-up
    where latency matters and memories are derived mechanically.
    """
    memories: list[dict] = []
    name = stakeholder.get("name", "Agent")

    # --- Fears → fear_triggered memories ---
    fears = _safe_list(stakeholder.get("fears", []))
    for fear in fears[:3]:
        memories.append({
            "type": "fear_triggered",
            "content": f"{name} is deeply worried about: {fear}"[:200],
            "salience": 0.9,
        })

    # --- Needs → belief_update memories ---
    needs = _safe_list(stakeholder.get("needs", []))
    for need in needs[:3]:
        memories.append({
            "type": "belief_update",
            "content": f"{name} fundamentally needs: {need}"[:200],
            "salience": 0.85,
        })

    # --- BATNA → proposal memory ---
    batna = stakeholder.get("batna") or stakeholder.get("BATNA")
    if batna and str(batna).strip():
        memories.append({
            "type": "proposal",
            "content": f"{name}'s fallback if negotiation fails: {batna}"[:200],
            "salience": 0.8,
        })

    # --- Grounding quotes → belief_update memories ---
    quotes = _safe_list(stakeholder.get("grounding_quotes", []))
    for quote in quotes[:2]:
        memories.append({
            "type": "belief_update",
            "content": f"{name} once said: \"{quote}\""[:200],
            "salience": 0.75,
        })

    # --- Key concerns → fear_triggered memories ---
    concerns = _safe_list(stakeholder.get("key_concerns", []))
    for concern in concerns[:3]:
        memories.append({
            "type": "fear_triggered",
            "content": f"{name}'s key concern: {concern}"[:200],
            "salience": 0.7,
        })

    # --- Hard constraints → belief_update memories ---
    constraints = _safe_list(stakeholder.get("hard_constraints", []))
    for constraint in constraints[:2]:
        memories.append({
            "type": "belief_update",
            "content": f"{name}'s red line: {constraint}"[:200],
            "salience": 0.95,
        })

    # --- Success criteria → proposal memory ---
    success = stakeholder.get("success_criteria")
    if success and str(success).strip():
        memories.append({
            "type": "proposal",
            "content": f"For {name}, success means: {success}"[:200],
            "salience": 0.7,
        })

    # --- ADKAR → belief_update memory ---
    adkar = stakeholder.get("adkar")
    if isinstance(adkar, dict):
        low_scores = [k for k, v in adkar.items() if isinstance(v, (int, float)) and v <= 2]
        if low_scores:
            memories.append({
                "type": "belief_update",
                "content": f"{name} scores low on change-readiness in: {', '.join(low_scores)}"[:200],
                "salience": 0.65,
            })

    # --- Project context → shared memory ---
    if project:
        org = project.get("organization_name") or project.get("name")
        if org:
            memories.append({
                "type": "belief_update",
                "content": f"{name} works at {org} and is navigating organizational change"[:200],
                "salience": 0.5,
            })

    return memories


async def generate_formative_memories(
    stakeholder: dict,
    project: Optional[dict] = None,
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    use_llm: bool = False,
) -> list[dict]:
    """Generate formative memories for a stakeholder.

    Parameters
    ----------
    stakeholder:
        The stakeholder dict with persona fields.
    project:
        Optional project context dict.
    base_url, api_key, model:
        LLM connection (only used when ``use_llm=True``).
    use_llm:
        If True, use an LLM to enrich the mechanical memories with
        narrative backstory. Defaults to False for speed.

    Returns
    -------
    list[dict]
        Memory candidate dicts with ``type``, ``content``, ``salience``.
    """
    # Start with deterministic mechanical memories
    memories = generate_formative_memories_sync(stakeholder, project)

    if not use_llm or not base_url or not model:
        return memories

    # LLM enrichment: convert the top mechanical memories into episodic narratives
    name = stakeholder.get("name", "Agent")
    role = stakeholder.get("role", "stakeholder")
    signal = stakeholder.get("signal_cle", "")

    mechanical_summary = "\n".join(f"- {m['content']}" for m in memories[:5])

    system = (
        f"You are creating episodic backstory memories for {name}, a {role}. "
        "Convert each bullet point into a vivid first-person memory (max 30 words each). "
        "Use past tense. Make each feel like a real experience. "
        "Return one memory per line, prefixed with '- '."
    )
    user_content = (
        f"## Character: {name}, {role}\n"
        f"## Position: {signal}\n\n"
        f"## Key traits to convert:\n{mechanical_summary}\n\n"
        "Convert into 3-5 episodic memories:"
    )

    try:
        result = await get_completion_content(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        if result and result.strip():
            for line in result.strip().split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line and len(line) > 10:
                    memories.append({
                        "type": "belief_update",
                        "content": f"{line}"[:200],
                        "salience": 0.6,
                    })
    except Exception:
        logger.warning(
            "LLM formative memory enrichment failed for %s — using mechanical only",
            stakeholder.get("slug", name), exc_info=True,
        )

    return memories
