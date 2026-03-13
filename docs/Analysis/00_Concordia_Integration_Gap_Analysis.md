# Concordia Integration Gap Analysis

**Date:** 2026-03-11
**Status:** Technical Analysis
**Scope:** What Google DeepMind Concordia offers that A2A War Games currently lacks

---

## Executive Summary

A2A War Games is operationally sophisticated (async streaming, SSE, analytics pipelines, private threads) but **cognitively simplistic** — agents don't learn, the moderator can't enforce, consensus is averaging, and positions are transient. Google DeepMind's Concordia library addresses many of these gaps through a modular Entity-Component System designed to produce human-like agent behavior.

This document maps Concordia's capabilities to specific A2A limitations and identifies integration opportunities ranked by impact and effort.

---

## 1. A2A War Games: Current Limitations

### 1.1 Engine (`engine.py` — 2055 lines)

| Limitation | Detail |
|---|---|
| **Naive memory decay** | Linear `0.1 per round` with floor — no episodic recall or relevance scoring |
| **Positions never harden** | 2D embedding space but no notion of commitment; agents can flip in one turn |
| **Consensus is mean-based** | Simple average of sentiment scores; doesn't weight by influence or conviction |
| **Anti-groupthink is one-shot** | Triggers at consensus > 0.75, forces single most dissenting agent — crude |
| **No memory integration** | Observer extracts memories but they never feed back into agent re-prompting |
| **No learning across sessions** | `prior_session_context` is flat text; no episodic memory retrieval |
| **Parallel agents not implemented** | Feature flag reserved but code is "NOT YET IMPLEMENTED" |
| **No emotional contagion** | One agent's frustration doesn't propagate; sentiment is isolated per turn |

### 1.2 Moderator (`moderator.py` — 290 lines)

| Limitation | Detail |
|---|---|
| **No speaker enforcement** | Moderator *recommends* speakers but `SpeakerSelector` actually picks |
| **Challenge is one-shot** | Single interjection; no sustained follow-up if agent resists |
| **No memory of own interventions** | Doesn't track whether past challenges were effective |
| **Synthesis is summative** | Doesn't propose next-round direction or force priority-setting |
| **No meta-discussion** | Never says "we're going in circles on X; suggest we table it" |
| **No debate mechanics** | No rebuttal slots, open forum modes, or structured negotiation phases |

### 1.3 Observer (`observer.py` — 231 lines)

| Limitation | Detail |
|---|---|
| **No temporal integration** | Each turn analyzed in isolation; can't detect position drift |
| **Sentiment is coarse** | 5 dimensions only; misses frustration, desperation, hope, betrayal |
| **No claim verification** | Extracts claims but never checks cross-turn factual consistency |
| **Memory candidates are heuristic** | LLM decides salience; no validation of actual memorability |
| **Falls back to all zeros** | LLM failure → neutral silence — masks extraction failure |

### 1.4 Prompt Compiler (`prompt_compiler.py` — 252 lines)

| Limitation | Detail |
|---|---|
| **Anti-sycophancy is prompt-only** | No code enforcement if LLM decides to ignore constraints |
| **ADKAR is static** | Change readiness scores never update based on agent behavior |
| **Cognitive biases are decoration** | Listed but never triggered procedurally |
| **BATNA is passive** | Listed as fallback but never drives urgency dynamically |
| **No persona drift detection** | Agent can slowly shift personality; no re-grounding mechanism |

### 1.5 Speaker Selection (`speaker_selection.py` — 203 lines)

| Limitation | Detail |
|---|---|
| **No strategic pairing** | Doesn't pair complementary agents (alliance vs. opposition) |
| **Diversity bonus is binary** | 1.5x if different attitude, 1.0x if same — no gradation |
| **No fatigue modeling** | Agents who speak 5 times in a row don't get "tired" |
| **Doesn't track speaker patterns** | Only looks at `last_speaker_attitude`; misses multi-turn patterns |

### 1.6 Cross-Cutting Weaknesses

1. **Agents are stateless opinion generators** — each turn regenerated from scratch
2. **No face-saving** — agents never refuse to speak or protect dignity when challenged publicly
3. **No side coalition propagation** — whisper channel insights don't strengthen alliances in main debate
4. **No tiredness/frustration arc** — agents don't escalate or shut down after repeated dismissals
5. **Proposals are optional** — "PROPOSAL REQUIREMENT" is prompt text; no enforced consequence
6. **No social proof** — agents don't react to "majority has shifted"

---

## 2. Concordia Components That Address These Gaps

### 2.1 `AssociativeMemory` → Fixes: Memory, Position Hardening, Learning

**What it does:** Each agent has an `AssociativeMemoryBank` backed by a pandas DataFrame. Memories are embedded via a `sentence_embedder` and retrieved by:
- **Recency** — `retrieve_recent(k)`
- **Semantic similarity** — `retrieve_associative(query, k)` using cosine similarity
- **Deduplication** — hash-based, prevents identical memories

**Why A2A needs it:** Currently agents see the full raw transcript but hold no persistent beliefs. With associative memory, agents would:
- Remember their own past concessions and commitments
- Retrieve relevant context before responding ("what happened last time someone proposed budget cuts?")
- Naturally harden positions — past commitments are recalled, making flip-flopping feel inconsistent

**Class signature:**
```python
class AssociativeMemoryBank:
    def __init__(self, sentence_embedder: Callable[[str], np.ndarray] | None = None,
                 allow_duplicates: bool = False)
    def add(self, text: str) -> None
    def retrieve_recent(self, k: int) -> list[str]
    def retrieve_associative(self, query: str, k: int) -> list[str]
```

---

### 2.2 `QuestionOfRecentMemories` → Fixes: Self-Reflection, Persona Drift

**What it does:** Before generating a response, the agent asks itself configurable questions about its own recent memories. The answer feeds into action generation.

**Built-in specializations:**
- `SelfPerception` — "What kind of person is {name}?"
- `SituationPerception` — "What kind of situation is {name} in right now?"
- `PersonBySituation` — "What would a person like {name} do in a situation like this?"
- `BestOptionPerception` — "Which option has the highest likelihood of achieving {name}'s goal?"

**Why A2A needs it:** Agents currently have zero introspection. With self-reflection:
- "Have I drifted from my original position?" → Prevents persona drift
- "What concessions have I already made?" → Prevents contradicting past commitments
- "Am I being too agreeable?" → Programmatic anti-sycophancy enforcement

**Class signature:**
```python
class QuestionOfRecentMemories:
    def __init__(self, model: LanguageModel, pre_act_label: str, question: str,
                 answer_prefix: str, add_to_memory: bool,
                 memory_tag: str = '', components: Sequence[str] = (),
                 num_memories_to_retrieve: int = 25)
    def _make_pre_act_value(self, action_spec: ActionSpec) -> str
```

---

### 2.3 `Plan` Component → Fixes: Stateless Responses, No Strategy

**What it does:** Agents formulate multi-step plans spanning multiple turns. The plan is re-evaluated each turn — the LLM is asked "should you change your current plan?" and if yes, generates a new one.

**Why A2A needs it:** Currently each agent turn is a one-shot reaction. With planning:
- Agent can strategize: "Concede on budget in round 3 to gain leverage on timeline in round 4"
- Re-planning happens when circumstances change (an ally defects, a new proposal appears)
- Plans can be time-aware (knowing what round it is, what's been decided)

**Class signature:**
```python
class Plan:
    def __init__(self, model: LanguageModel, pre_act_label: str,
                 goal_component_key: str | None = None,
                 components: Sequence[str] = (),
                 force_time_horizon: str | None = None)
```

---

### 2.4 `thought_chains` → Fixes: One-Shot Moderator, No Reasoning Pipeline

**What it does:** Sequential chain of LLM-driven reasoning steps. Each step conditions on the previous via `InteractiveDocument`. Available thought functions:

| Function | Purpose |
|---|---|
| `determine_success_and_why` | Did the action succeed? Why/why not? |
| `result_to_causal_statement` | Convert event to cause-and-effect |
| `attempt_to_most_likely_outcome` | Analyze goal, list consequences, pick most likely |
| `AccountForAgencyOfOthers` | Prevent forcing other agents into involuntary actions |
| `Conversation` | Resolve multi-party conversations between agents |
| `maybe_inject_narrative_push` | Break repetitive loops with new complications |
| `maybe_cut_to_next_scene` | Detect when scene should end |
| `get_action_category_and_player_capability` | Classify action type and assess proficiency |

**Why A2A needs it:** The moderator currently makes one-shot decisions. With thought chains:
- "Was Agent X's claim challenged?" → "Did anyone actually change position?" → "Is the group circling?" → "Therefore I should redirect to Y"
- `maybe_inject_narrative_push` directly solves the "going in circles" problem A2A has no mechanism for
- `AccountForAgencyOfOthers` prevents agents from claiming consensus that doesn't exist

**Core function:**
```python
def run_chain_of_thought(
    thoughts: Sequence[Callable[[InteractiveDocument, str, str], str]],
    premise: str,
    document: InteractiveDocument,
    active_player_name: str,
) -> tuple[str, InteractiveDocument]
```

---

### 2.5 `EventResolution` → Fixes: No Canonical Outcomes, Competing Claims

**What it does:** Transforms putative events (what agents *tried* to do/claim) into canonical resolved events (what *actually happened*) through thought chain reasoning.

**Flow:**
1. Retrieve putative event from memory (tagged `PUTATIVE_EVENT_TAG`)
2. Initialize `InteractiveDocument` with world context
3. Run `event_resolution_steps` (configurable thought chain)
4. Determine which agents are aware of the resolved event
5. Store canonical event with `EVENT_TAG`

**Why A2A needs it:** Currently if Agent A claims "we agreed on X" and Agent B disputes it, nothing resolves it. With event resolution:
- Moderator adjudicates: "Round 3 outcome: Budget was conditionally agreed pending Agent C's review"
- Canonical outcomes feed into next-round context
- No more competing narratives

---

### 2.6 `FormativeMemoriesInitializer` → Fixes: Flat Persona Prompts

**What it does:** A special Game Master that runs before the simulation to inject episodic backstory memories into agents. Converts profile fields into felt experiences stored in AssociativeMemory.

**Why A2A needs it:** A2A has rich persona fields (BATNA, fears, grounding quotes, ADKAR scores) but they're all declarative text in the system prompt. With formative memories:
- "I was in the meeting where the last budget overrun happened. I was blamed." → stored as retrievable memory
- Grounding quotes become experiences the agent "lived through"
- BATNA becomes a story: "Last time this failed, we went with Plan B and it was painful"

---

### 2.7 `SceneTracker` + `run_scenes` → Fixes: Identical Round Structure

**What it does:** Enables multi-phase simulations where each phase (Scene) has:
- Different Engine (Sequential vs Simultaneous)
- Different Game Master components active
- Different participation rules
- Explicit transitions

**Why A2A needs it:** All A2A rounds are structurally identical (intro → turns → synthesis). With scenes:
- Phase 1: Information sharing (all agents, simultaneous observations)
- Phase 2: Bilateral negotiations (whisper channels, sequential)
- Phase 3: Formal voting (structured, simultaneous)
- Each phase has different moderator behavior and rules

---

### 2.8 Sequential vs Simultaneous Engine → Fixes: Rigid Turn Order

**What it does:**
- `Sequential` — one agent acts at a time, immediate resolution
- `Simultaneous` — multiple agents act in parallel, batch resolution

**Why A2A needs it:** A2A only supports sequential turns. With simultaneous mode:
- All agents react to a surprise announcement at once
- Group reactions to a proposal (everyone votes simultaneously before seeing others' votes)
- Floor-crossing moments where multiple agents shift allegiance at once

---

### 2.9 `AccountForAgencyOfOthers` → Fixes: Forced Consensus, Agent Overreach

**What it does:** A thought chain class that detects when one agent's action implies involuntary action by another. It asks the affected agent directly: "Would you actually do this?" If no, it generates an alternative outcome.

**Why A2A needs it:** Currently agents can claim "we all agree" or "the group has decided" without verification. This component enforces that no agent can speak for another.

---

### 2.10 `Conversation` Thought Chain → Fixes: Monologue-Based Debate

**What it does:** Resolves conversational events by identifying participants, soliciting individual contributions, and generating a coherent multi-party conversation. Sends the result as observations to all participants.

**Why A2A needs it:** A2A debate is serial monologues. Agents don't actually converse — they make statements in sequence. The Conversation thought chain enables actual back-and-forth within a single resolution step.

---

### 2.11 Prefab Agents → Models for Richer Agent Archetypes

| Prefab | Components | Relevance to A2A |
|---|---|---|
| `basic__Entity` | Memory + Instructions + "Three Key Questions" | Standard reasoning agent; better than A2A's single-prompt agents |
| `basic_with_plan__Entity` | Above + Plan component | Strategic stakeholder with multi-turn planning |
| `conversational__Entity` | Dialogue-optimized, conversation dynamics | Better for debate format than generic agents |
| `minimal__Entity` | Memory + Instructions + Observation only | Baseline for comparison benchmarking |
| `puppet__Entity` | Fixed responses with LLM fallback | Could model rigid/scripted stakeholders |

### 2.12 Prefab Game Masters → Models for Richer Moderation

| Prefab | Purpose | Relevance to A2A |
|---|---|---|
| `generic__GameMaster` | Configurable thought chains, flexible | Base for A2A moderator enhancement |
| `dialogic__GameMaster` | Conversation management, repetition detection | Directly applicable to debate moderation |
| `dialogic_and_dramaturgic__GameMaster` | Scenes + dialogue | Multi-phase debates with narrative structure |
| `situated_in_time_and_place__GameMaster` | Time tracking, location awareness | Could model "negotiation room" dynamics |
| `game_theoretic_and_dramaturgic__GameMaster` | Matrix games + narrative | Model stakeholder payoff matrices |

---

## 3. Integration Priority Matrix

### Tier 1: Low Effort, High Impact (~50-100 lines each)

| Component | What to Build | Estimated Effort |
|---|---|---|
| **Self-Reflection (inspired by `QuestionOfRecentMemories`)** | Add pre-turn introspection step in `engine.py` — agent asks itself 2-3 questions before responding | 1-2 days |
| **Formative Memories (inspired by `FormativeMemoriesInitializer`)** | Convert persona fields → episodic backstory at session start, inject into agent context | 1-2 days |
| **Moderator Thought Chains (inspired by `thought_chains`)** | Replace one-shot `moderator_challenge()` with multi-step reasoning chain | 2-3 days |

### Tier 2: Medium Effort, High Impact (~200-500 lines each)

| Component | What to Build | Estimated Effort |
|---|---|---|
| **Associative Memory per Agent** | Embed & store key moments per agent; retrieve relevant memories before each turn | 1-2 weeks |
| **Agent Planning** | Add multi-turn plan state per agent; re-plan when circumstances change | 1 week |
| **Event Resolution for Moderator** | Moderator adjudicates canonical round outcomes; feeds into next-round context | 1-2 weeks |
| **Relationship Matrix** | Track trust/hostility between agent pairs; update after each interaction | 1 week |

### Tier 3: High Effort, Transformative (~500+ lines, architectural)

| Component | What to Build | Estimated Effort |
|---|---|---|
| **Scene-Based Debate Phases** | Multi-phase debates (information → negotiation → voting) with different rules per phase | 2-3 weeks |
| **Simultaneous Engine** | All agents react in parallel to key events; batch resolution | 2-3 weeks |
| **Agency Verification** | Before publishing consensus claims, verify with each affected agent | 1-2 weeks |
| **Full Conversation Resolution** | Replace serial monologues with actual multi-party conversation resolution | 2-3 weeks |

---

## 4. Recommended Implementation Order

```
Phase 1 (Quick Wins):
  ├── Self-Reflection pre-turn step
  ├── Formative memory injection
  └── Moderator thought chains

Phase 2 (Core Cognitive Upgrade):
  ├── Associative memory per agent
  ├── Agent planning component
  └── Relationship matrix

Phase 3 (Structural Transformation):
  ├── Event resolution / canonical outcomes
  ├── Scene-based debate phases
  └── Simultaneous agent reactions

Phase 4 (Full Concordia Parity):
  ├── Agency verification
  ├── Conversation resolution
  └── Benchmark framework (A2A vs Concordia-enhanced)
```

---

## 5. What Concordia Does NOT Have That A2A Does

A2A has several production features Concordia lacks:

| A2A Feature | Concordia Equivalent |
|---|---|
| Real-time SSE streaming | None (batch execution) |
| Vue 3 frontend with live analytics | None (CLI/notebook only) |
| Anti-sycophancy behavioral constraints | None (agents are fully autonomous) |
| ADKAR change readiness model | None (no organizational psychology) |
| Rich stakeholder profiles (BATNA, cognitive biases, fears) | Basic character descriptions |
| Consensus scoring & coalition detection | None (no analytics) |
| Production API (FastAPI + PostgreSQL) | None (research library) |
| Whisper channels for bilateral negotiation | GM-mediated observation routing (similar concept) |

**The goal is not to replace A2A with Concordia, but to adopt Concordia's cognitive architecture to make A2A's agents think more like humans.**

---

*Next:* See companion documents for detailed Concordia technical reference and A2A whisper channel documentation.
