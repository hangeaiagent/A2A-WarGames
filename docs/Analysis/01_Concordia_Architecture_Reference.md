# Concordia Architecture Reference

**Source:** [google-deepmind/concordia](https://github.com/google-deepmind/concordia)
**Purpose:** Technical reference for integrating Concordia patterns into A2A War Games

---

## 1. Entity-Component System (ECS)

Concordia's core design separates **entities** (agents, game masters) from **components** (modular behavior units). Both `EntityAgent` and `GameMaster` are built from the same ECS.

### 1.1 Component Hierarchy

```
BaseComponent
├── ContextComponent          # Provides information during lifecycle phases
│   ├── pre_act(action_spec) -> str
│   ├── post_act(action_attempt) -> str
│   ├── pre_observe(observation) -> str
│   ├── post_observe() -> str
│   └── update() -> None
├── ActingComponent           # Generates actions (exactly one per agent)
│   └── get_action_attempt(context, action_spec) -> str
└── ContextProcessorComponent # Processes aggregated context (optional)
    ├── pre_act(contexts) -> None
    ├── post_act(contexts) -> None
    ├── pre_observe(contexts) -> None
    └── post_observe(contexts) -> None
```

### 1.2 Component Lifecycle Phases

```
Phase Enum: READY → PRE_ACT → POST_ACT → UPDATE → READY
                 → PRE_OBSERVE → POST_OBSERVE → UPDATE → READY
```

Phase transitions are strictly validated by `_set_phase()`. Invalid transitions raise errors.

### 1.3 EntityAgent — The Component Orchestrator

```python
class EntityAgent:
    def __init__(self, agent_name: str,
                 act_component: ActingComponent,
                 context_processor: ContextProcessorComponent | None,
                 context_components: Mapping[str, ContextComponent])
```

**`act()` execution flow:**
1. Acquire `_control_lock` (thread safety)
2. Phase → `PRE_ACT`
3. `_parallel_call_('pre_act', action_spec)` on all ContextComponents
4. ContextProcessorComponent.pre_act(contexts)
5. ActingComponent.get_action_attempt(contexts, action_spec) → **action**
6. Phase → `POST_ACT`
7. `_parallel_call_('post_act', action_attempt)`
8. Phase → `UPDATE`
9. `_parallel_call_('update')`
10. Phase → `READY`, release lock, return action

**`observe()` execution flow:**
1. Acquire lock
2. Phase → `PRE_OBSERVE`
3. `_parallel_call_('pre_observe', observation)`
4. Phase → `POST_OBSERVE`
5. `_parallel_call_('post_observe')`
6. Phase → `UPDATE`
7. `_parallel_call_('update')`
8. Phase → `READY`, release lock

**Key insight:** `_parallel_call_` uses `ThreadPoolExecutor` to run component methods concurrently, with deduplication.

### 1.4 GameMaster

The GameMaster is also an `EntityAgent`. Its `ActingComponent` is a `SwitchAct` that routes requests based on `action_spec.output_type`:

```
output_type == NEXT_ACTING     → NextActing component
output_type == MAKE_OBSERVATION → MakeObservation component
output_type == RESOLVE          → EventResolution component
output_type == TERMINATE        → Terminate component
```

---

## 2. ConcatActComponent — How Actions Are Generated

The most common `ActingComponent`. It concatenates context from all components into a single LLM prompt.

```python
class ConcatActComponent:
    def __init__(self, model: LanguageModel,
                 component_order: Sequence[str] | None = None)

    def get_action_attempt(self, contexts: ComponentContextMapping,
                           action_spec: ActionSpec) -> str
```

**How it works:**
1. Iterate over components in `component_order` (or dict order if None)
2. For each component, get its `pre_act()` return string
3. Skip empty strings
4. Concatenate all non-empty strings with labels: `"{label}: {value}"`
5. Append the action prompt from `action_spec`
6. Send to LLM → return response

**Example assembled prompt:**
```
Instructions: You are Alice, a budget-conscious CFO...
Recent memories: [memory 1], [memory 2], [memory 3]
Current situation: A proposal to increase R&D spending is being debated.
Self-reflection: I've already conceded on the timeline. I should hold firm on budget.
Current plan: Step 1: Acknowledge R&D value. Step 2: Propose phased spending.

What does Alice do next?
```

---

## 3. Prefab Agents

### 3.1 `basic__Entity` — Standard Reasoning Agent
**Components:** AssociativeMemory, Instructions, LastNObservations, "Three Key Questions" (SelfPerception → SituationPerception → PersonBySituation)

### 3.2 `basic_with_plan__Entity` — Strategic Agent
**Components:** basic__Entity + Plan component for multi-turn strategy

### 3.3 `conversational__Entity` — Dialogue-Optimized
**Components:** Optimized for conversation dynamics and history tracking

### 3.4 `minimal__Entity` — Bare Bones
**Components:** Memory + Instructions + Observation only

### 3.5 `puppet__Entity` — Scripted Responses
**Components:** `PuppetActComponent` with fixed responses; LLM fallback if no match

### 3.6 `basic_scripted__Entity` — Script + Internal Thought
**Components:** Three Key Questions for internal reasoning; follows pre-defined script for actions

---

## 4. Prefab Game Masters

### 4.1 `generic__GameMaster`
Highly configurable. Custom thought chains for event resolution. Configurable acting order. General purpose.

### 4.2 `dialogic__GameMaster`
Specialized for conversation. Detects repetitive conversations and ends them. Enforces speech-only action specs. **Most relevant to A2A debate moderation.**

### 4.3 `dialogic_and_dramaturgic__GameMaster`
Dialogue + Scene management. Supports structured conversational episodes (prologues, episodes). **Relevant for multi-phase A2A debates.**

### 4.4 `situated_in_time_and_place__GameMaster`
Extends situated with `GenerativeClock`. Tracks time passage and narrates it. Supports day/night cycles. Could model "meeting dynamics" (morning energy vs. afternoon fatigue).

### 4.5 `game_theoretic_and_dramaturgic__GameMaster`
Matrix games + narrative scenes. Maps joint actions to scores. **Could model stakeholder payoff matrices** — if Agent A concedes and Agent B escalates, what's the payoff?

### 4.6 `formative_memories_initializer__GameMaster`
Runs once at start. Injects shared and player-specific backstory memories. Converts profile fields into experiential memories.

### 4.7 `scripted__GameMaster`
Forces linear event script. Useful for generating training data or regression testing.

### 4.8 `interviewer__GameMaster` / `open_ended_interviewer__GameMaster`
Administers questionnaires. Could be used for post-simulation stakeholder surveys.

---

## 5. Simulation Orchestration

### 5.1 Simulation Class

```python
class Simulation:
    def __init__(self, config: Config, model: LanguageModel,
                 embedder: Callable, engine: Engine)
    def play(self) -> SimulationLog
```

**Lifecycle:**
1. **Configuration** — Config defines prefabs and instances
2. **Initialization** — Creates AssociativeMemoryBank per entity, shared bank for GMs
3. **Formative Memories** — INITIALIZER GMs run first to inject backstories
4. **Execution Loop** — `engine.run_loop()` drives the simulation
5. **Termination** — Based on `max_steps` or game state conditions
6. **Logging** — Structured SimulationLog with entity memories attached

### 5.2 Engines

**Sequential Engine:**
```
GM selects agent → Agent acts → GM resolves immediately → All observe
```
- One agent at a time
- Immediate resolution and observation
- Predictable, easy to follow

**Simultaneous Engine:**
```
GM selects agents → All act in parallel → GM batch-resolves → All observe
```
- Multiple agents act concurrently
- Actions collected, resolved as batch
- Agents don't see others' actions until round ends
- Enables surprise reactions and group dynamics

### 5.3 Scenes and Multi-Phase Simulation

```python
run_scenes(scenes: Sequence[Scene]) -> None

# Each Scene has:
#   - engine: Engine (Sequential or Simultaneous)
#   - game_master: GameMaster
#   - participants: list[EntityAgent]
#   - premise: str
#   - max_steps: int
```

**Example multi-phase debate:**
```
Scene 1: "Opening Statements" (Sequential, all agents, max_steps=N)
Scene 2: "Bilateral Negotiations" (Sequential, pairs, max_steps=M)
Scene 3: "Final Vote" (Simultaneous, all agents, max_steps=1)
```

---

## 6. Key Data Structures

### ActionSpec
```python
@dataclass
class ActionSpec:
    output_type: OutputType    # FREE, CHOICE, FLOAT, RESOLVE, etc.
    call_to_action: str        # Prompt for the agent
    options: tuple[str, ...]   # For CHOICE type
    tag: str                   # Metadata tag
```

### OutputType Enum
```python
class OutputType(enum.Enum):
    FREE = 'free'              # Free-form text response
    CHOICE = 'choice'          # Multiple choice
    FLOAT = 'float'            # Numeric response
    RESOLVE = 'resolve'        # Event resolution (GM only)
    NEXT_ACTING = 'next_acting'
    MAKE_OBSERVATION = 'make_observation'
    TERMINATE = 'terminate'
```

### InteractiveDocument
```python
class InteractiveDocument:
    def __init__(self, model: LanguageModel)
    def open_question(self, question: str) -> str
    def yes_no_question(self, question: str) -> bool
    def multiple_choice_question(self, question: str, options: list[str]) -> str
```

Used throughout thought chains. Accumulates reasoning context. Each question/answer becomes part of the document for subsequent questions.

---

## 7. Mapping to A2A Components

| Concordia | A2A Equivalent | Gap |
|---|---|---|
| `EntityAgent` | Each stakeholder agent | A2A agents are stateless; no component lifecycle |
| `GameMaster` | `moderator.py` | A2A moderator has no SwitchAct routing or event resolution |
| `ActingComponent` | LLM call in `_agent_turn()` | A2A has no pre-act context gathering from components |
| `ContextComponent` | `prompt_compiler.py` (partially) | A2A compiles once at init; Concordia gathers per-turn |
| `AssociativeMemoryBank` | `observer.py` memory_candidates | A2A extracts but never retrieves; Concordia retrieves actively |
| `ConcatActComponent` | System prompt + transcript | A2A concatenates statically; Concordia concatenates dynamically |
| `Simulation` | `A2AEngine` | Structurally similar; A2A lacks scenes and engine switching |
| `Sequential Engine` | Current A2A turn loop | Functionally equivalent |
| `Simultaneous Engine` | Not implemented | A2A has feature flag but no code |

---

*See also:* [02_Concordia_Human_Behavior_Modeling.md](./02_Concordia_Human_Behavior_Modeling.md) for memory, reflection, and planning details.
