# Concordia: Human Behavior Modeling

**Source:** [google-deepmind/concordia](https://github.com/google-deepmind/concordia)
**Purpose:** Deep reference on how Concordia makes agents behave like humans, and how to adapt these patterns for A2A War Games

---

## 1. Memory Architecture

### 1.1 AssociativeMemoryBank — The Core

Every Concordia agent has an isolated `AssociativeMemoryBank`. Game Masters share a collective one.

```python
class AssociativeMemoryBank:
    def __init__(self,
                 sentence_embedder: Callable[[str], np.ndarray] | None = None,
                 allow_duplicates: bool = False):
        self._memory_bank: pd.DataFrame  # columns: text, embedding
        self._pending_memories: list      # batch buffer for efficiency
```

**Storage:**
- Memories are text strings + their embedding vectors
- Hash-based deduplication (unless `allow_duplicates=True` for GMs)
- Pending memories are flushed to DataFrame in batches
- Newlines stripped from input text

**Retrieval patterns:**

| Method | Mechanism | Use Case |
|---|---|---|
| `retrieve_recent(k)` | Last k entries by insertion order | "What just happened?" |
| `retrieve_associative(query, k)` | Cosine similarity of query embedding vs stored embeddings | "What do I remember about budget proposals?" |

**A2A adaptation:** A2A already has pgvector (CR-010) and sentence-BERT. The infrastructure exists — what's missing is the *per-agent memory bank* and the *active retrieval before each turn*.

### 1.2 ObservationToMemory — Automatic Memory Formation

```python
OBSERVATION_TAG = '[observation]'

class ObservationToMemory:
    def pre_observe(self, observation: str) -> str:
        self.memory.add(f"{OBSERVATION_TAG} {observation}")
        return ''
```

Every observation (what an agent sees/hears) is automatically stored in memory. Tagged with `[observation]` for later filtering.

**A2A adaptation:** After each turn in the debate, store a memory for each agent who "heard" it:
- `"[observation] Round 3: Agent_CFO proposed phased budget increase over 18 months"`
- These become retrievable context for future turns

### 1.3 FormativeMemoriesInitializer — Backstory as Memory

Runs before the simulation starts. Converts character descriptions into episodic memories.

**Shared memories** — events all agents know about:
```
"The company had a major budget overrun in Q3 2025."
"The CEO publicly committed to 15% cost reduction."
```

**Player-specific context** — personal history:
```
"I was blamed for the Q3 overrun even though it was supply chain issues."
"I've been pushing for automation investment for 3 years with no support."
```

These are stored in `AssociativeMemoryBank`, not in system prompts. The agent *remembers* these as experiences, not as instructions.

**A2A adaptation:** Convert these persona fields into episodic memories:
- `fears` → "I'm deeply worried that [fear]. Last time this happened, [consequence]."
- `grounding_quotes` → "I remember saying '[quote]' in the interview because I genuinely believe it."
- `batna` → "If this all falls apart, my fallback is [BATNA]. I explored this option when [context]."
- `key_concerns` → "The thing keeping me up at night is [concern]. I raised it in [context]."

---

## 2. Self-Reflection

### 2.1 QuestionOfRecentMemories — The Core Mechanism

Before generating a response, the agent asks itself questions about its own memories. The answer becomes part of the action context.

```python
class QuestionOfRecentMemories:
    def __init__(self,
                 model: LanguageModel,
                 pre_act_label: str,       # Label in concatenated prompt
                 question: str,            # The reflection question
                 answer_prefix: str,       # Forces answer format
                 add_to_memory: bool,      # Store reflection as new memory?
                 memory_tag: str = '',
                 components: Sequence[str] = (),  # Other component outputs to include
                 num_memories_to_retrieve: int = 25)
```

**How `_make_pre_act_value` works:**
1. Retrieve `num_memories_to_retrieve` recent memories
2. Get outputs from dependent components (if any)
3. Construct prompt: memories + component context + question
4. LLM answers the question with `answer_prefix`
5. Optionally store answer back in memory (for future reflection)
6. Return answer as this component's pre_act value

### 2.2 Built-in Specializations

**SelfPerception:**
```
Question: "What kind of person is {agent_name}?"
Answer prefix: "{agent_name} is "
```
Forces the agent to reflect on its own identity before speaking. Prevents persona drift.

**SituationPerception:**
```
Question: "What kind of situation is {agent_name} in right now?"
Answer prefix: "{agent_name} is currently in "
```
Contextualizes the agent's response within the current debate state.

**PersonBySituation:**
```
Question: "What would a person like {agent_name} do in a situation like this?"
Answer prefix: "{agent_name} would "
```
Bridges identity and situation into action. This is the key anti-sycophancy mechanism — a CFO who is "budget-conscious and risk-averse" wouldn't agree to an expensive proposal just because others have.

**BestOptionPerception:**
```
Question: "Which of {agent_name}'s options has the highest likelihood of causing
           {agent_name} to achieve their goal?"
Answer prefix: "The best option for {agent_name} is "
```
Strategic reasoning before action.

### 2.3 A2A Adaptation: Pre-Turn Reflection

Add to `engine.py` before each `_agent_turn()`:

```python
# Pseudo-code for A2A self-reflection
reflection_questions = [
    f"Given everything that has happened, what is {agent_name}'s current stance "
    f"on the proposal? Has it changed from their original position of '{baseline_position}'?",

    f"What concessions has {agent_name} already made? What would they refuse to concede?",

    f"Who does {agent_name} trust most in this discussion? Who do they distrust? Why?",
]

for question in reflection_questions:
    # Retrieve relevant memories for this agent
    memories = agent_memory.retrieve_associative(question, k=10)
    # Ask LLM the question with memory context
    reflection = await llm_client.get_completion_content(
        messages=[{"role": "system", "content": f"Recent memories:\n{memories}"},
                  {"role": "user", "content": question}]
    )
    # Inject reflection into agent's context for this turn
    agent_context.append(f"Self-reflection: {reflection}")
```

---

## 3. Multi-Turn Planning

### 3.1 Plan Component

```python
class Plan:
    def __init__(self,
                 model: LanguageModel,
                 pre_act_label: str,
                 goal_component_key: str | None = None,  # Component providing the goal
                 components: Sequence[str] = (),          # Other context components
                 force_time_horizon: str | None = None)   # Override time horizon

    self._current_plan: str = ''  # Persisted between turns
```

**How planning works:**
1. Check if agent has a current plan
2. If no plan → generate one from goal + context
3. If has plan → ask LLM: "Should {agent_name} change their current plan?"
4. If yes → regenerate plan
5. If no → keep current plan
6. Return plan as pre_act context

**Re-planning triggers:**
- No existing plan
- LLM judges plan is stale (via `yes_no_question`)
- Goal changes
- Significant new information (via memory updates)

### 3.2 A2A Adaptation: Agent Strategy

```python
# Per-agent plan state
agent_plans: dict[str, str] = {}  # agent_name → current plan

async def update_agent_plan(agent_name: str, round_num: int, context: str):
    current_plan = agent_plans.get(agent_name, "")

    if not current_plan:
        prompt = f"""You are {agent_name}. Your goal is to protect {top_fear}
        while achieving {success_criteria}.

        Given the current state of the debate (round {round_num}):
        {context}

        Create a 3-step plan for how you will achieve your goal
        over the remaining rounds. Be specific about what you'll
        propose, who you'll ally with, and what you'll concede."""
    else:
        prompt = f"""Your current plan: {current_plan}

        Since you made this plan, the following has happened:
        {recent_events}

        Should you change your plan? If yes, what's the new plan?"""

    new_plan = await llm_client.get_completion_content(...)
    agent_plans[agent_name] = new_plan
    return new_plan
```

---

## 4. Relationship Tracking

### 4.1 Concordia's Approach

Concordia tracks relationships between agents as a component. While the exact implementation details are in the changelog, the concept is:

- **Relationship state per pair** — trust, hostility, alliance strength
- **Updated after each interaction** — when Agent A responds to Agent B, their relationship updates
- **Factors into action** — agents consider their relationship with the current speaker

### 4.2 A2A Adaptation: Relationship Matrix

```python
# Relationship matrix: (agent_a, agent_b) → RelationshipState
@dataclass
class RelationshipState:
    trust: float        # -1 (hostile) to +1 (full trust)
    alliance: float     # 0 (none) to 1 (strong)
    recent_interaction: str  # last notable interaction
    history: list[str]  # key moments

# Update after each turn
def update_relationship(speaker: str, mentioned_agents: list[str],
                       behavioral_signals: dict):
    for other in mentioned_agents:
        rel = relationships[(speaker, other)]
        if behavioral_signals.get('agreement'):
            rel.trust += 0.1
            rel.alliance += 0.05
        if behavioral_signals.get('challenge'):
            rel.trust -= 0.05
        if behavioral_signals.get('concession'):
            rel.alliance += 0.1
        # Clamp values
```

**Feed into agent context:**
```
Relationships:
- You trust Agent_CFO (trust: 0.7, alliance: strong) — they supported your proposal in round 2
- You distrust Agent_CTO (trust: -0.3) — they publicly dismissed your concerns in round 1
- Agent_HR is neutral (trust: 0.1) — limited interaction so far
```

---

## 5. Observation Processing — How Agents Perceive Events

### 5.1 Concordia's `MakeObservation`

The Game Master doesn't send raw events to agents. It formats events into **observations** — what the agent would actually perceive.

**Key concept:** Not all agents see all events the same way. The GM asks: "How would Agent X perceive this event?" and generates a tailored observation.

### 5.2 `LastNObservations`

Simple but effective: keeps the N most recent observations available as immediate context. Equivalent to "working memory" — what just happened.

### 5.3 A2A Adaptation: Filtered Perception

Instead of every agent seeing the full transcript, filter what each agent "notices":

```python
def make_observation(event: str, observer: str, observer_profile: dict) -> str:
    """Generate agent-specific perception of an event."""
    prompt = f"""Event: {event}

    Observer: {observer} ({observer_profile['department']}, {observer_profile['attitude']})
    Key concerns: {observer_profile['key_concerns']}
    Cognitive biases: {observer_profile['cognitive_biases']}

    How would {observer} perceive and interpret this event?
    What would they notice? What would they miss or dismiss?
    (1-2 sentences, first person)"""

    return await llm_client.get_completion_content(messages=[...])
```

This makes the same event look different to different agents — confirmation bias, selective attention, motivated reasoning become emergent.

---

## 6. Goal-Oriented Behavior

Concordia agents can have explicit `goal` parameters that drive their behavior through the Plan component and BestOptionPerception.

**A2A already has this conceptually** (success_criteria, needs, BATNA) but these are static prompt text. The adaptation is to make goals **dynamic** — updated based on what's been achieved and what's been blocked.

```python
# Dynamic goal tracking
@dataclass
class AgentGoal:
    primary: str           # From success_criteria
    achieved: list[str]    # Concessions won
    blocked: list[str]     # Proposals rejected
    revised_priority: str  # Updated focus for current round

# After each round, update goals
def update_goals(agent: str, round_outcomes: dict):
    goal = agent_goals[agent]
    for outcome in round_outcomes['agreements']:
        if outcome.relevant_to(goal.primary):
            goal.achieved.append(outcome)
    # Shift focus to remaining unachieved objectives
    goal.revised_priority = compute_next_priority(goal)
```

---

## 7. Component Chaining — The Full Picture

In Concordia, human-like behavior emerges from **chaining components**, not from any single mechanism:

```
Observation arrives
    → ObservationToMemory (stores it)
    → LastNObservations (keeps in working memory)
    → Agent.act() is called
        → AssociativeMemory retrieves relevant past
        → Instructions remind agent of identity
        → SelfPerception: "What kind of person am I?"
        → SituationPerception: "What's happening right now?"
        → PersonBySituation: "What would someone like me do here?"
        → Plan: "What's my multi-step strategy?"
        → ConcatActComponent assembles all of the above
        → LLM generates action
    → Agent.post_act() updates internal state
    → Agent.update() refreshes caches
```

**This is the fundamental difference from A2A:** A2A agents go from `system_prompt + transcript → LLM → response`. Concordia agents go through **6+ cognitive steps** before generating a response.

---

## 8. What This Means for Simulation Quality

| Behavior | A2A (Current) | A2A + Concordia Patterns |
|---|---|---|
| Position consistency | Random; LLM may contradict prior statements | Memory retrieval surfaces past commitments |
| Strategic thinking | One-shot reactions | Multi-turn plans with re-evaluation |
| Self-awareness | None | Pre-turn reflection on own trajectory |
| Social dynamics | Emergent from sentiment averaging | Explicit relationship tracking |
| Persona fidelity | Static prompt; drifts over time | SelfPerception re-grounds identity each turn |
| Information processing | Full transcript dump | Filtered observation + associative retrieval |
| Emotional arc | None | Relationship state + cumulative memory = emergent emotional trajectory |
| Anti-sycophancy | Prompt text only | PersonBySituation: "What would a risk-averse CFO do?" |

---

*See also:* [03_Concordia_Thought_Chains_and_Game_Master.md](./03_Concordia_Thought_Chains_and_Game_Master.md) for moderator-level reasoning.
