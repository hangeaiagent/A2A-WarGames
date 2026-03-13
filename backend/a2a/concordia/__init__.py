"""
Concordia-inspired cognitive components for A2A War Games.

Inspired by Google DeepMind's Concordia library, these components add
human-like cognitive capabilities to debate agents:

Phase 1 (Quick Wins):
  - Self-Reflection: Pre-turn introspection to ground identity and prevent drift
  - Formative Memories: Convert persona fields into retrievable episodic memories
  - Thought Chains: Multi-step moderator reasoning for richer challenges

See docs/CR-014_Concordia_Integration.md for full integration plan.
"""

from .self_reflection import build_self_reflection
from .formative_memories import generate_formative_memories
from .thought_chains import moderator_challenge_with_reasoning, resolve_round_outcome

__all__ = [
    "build_self_reflection",
    "generate_formative_memories",
    "moderator_challenge_with_reasoning",
    "resolve_round_outcome",
]
