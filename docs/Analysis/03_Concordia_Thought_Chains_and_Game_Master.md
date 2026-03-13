# Concordia: Thought Chains & Game Master System

**Source:** [google-deepmind/concordia](https://github.com/google-deepmind/concordia)
**Purpose:** How Concordia's moderator-equivalent reasons, resolves events, and manages simulation flow

---

## 1. Thought Chains — Multi-Step LLM Reasoning

### 1.1 Core Concept

Instead of making a single LLM call to decide what happens, Concordia chains multiple reasoning steps. Each step conditions on the previous, building a progressively refined understanding.

### 1.2 `run_chain_of_thought`

```python
def run_chain_of_thought(
    thoughts: Sequence[Callable[[InteractiveDocument, str, str], str]],
    premise: str,
    document: InteractiveDocument,
    active_player_name: str,
) -> tuple[str, InteractiveDocument]
```

**Parameters:**
- `thoughts` — ordered list of reasoning functions
- `premise` — initial event/action to reason about
- `document` — accumulating context (InteractiveDocument)
- `active_player_name` — who initiated the action

**Each thought function signature:**
```python
def thought_fn(doc: InteractiveDocument, event: str, player_name: str) -> str
```
Takes the current event string, asks the LLM questions via `doc`, returns a modified event string.

### 1.3 InteractiveDocument

```python
class InteractiveDocument:
    def __init__(self, model: LanguageModel)
    def open_question(self, question: str) -> str
    def yes_no_question(self, question: str) -> bool
    def multiple_choice_question(self, question: str, options: list[str]) -> str
```

The document accumulates all questions and answers. Each new question sees the full history of prior reasoning. This creates a coherent chain of thought.

---

## 2. Available Thought Chain Functions

### 2.1 Outcome Determination

| Function | What it Does | Example |
|---|---|---|
| `determine_success_and_why` | Asks if an action succeeds; if not, why | "Did Agent_CFO's budget proposal get traction? No, because Agent_CTO raised unfunded mandate concerns." |
| `result_to_causal_statement` | Converts event to cause-and-effect | "Because Agent_CFO proposed phased spending, Agent_HR expressed cautious support." |
| `attempt_to_result` | Determines direct result considering context | "Agent_CEO's call for unity resulted in temporary ceasefire on the budget topic." |
| `attempt_to_most_likely_outcome` | Lists possible consequences, picks most likely | "Possible: (a) group agrees, (b) Agent_CTO escalates, (c) tabled. Most likely: (b)" |

### 2.2 Agency & Fairness

| Function | What it Does | Example |
|---|---|---|
| `AccountForAgencyOfOthers` | Prevents forcing agents into involuntary actions | "Agent_CFO claimed 'we all agree' — checking with Agent_CTO... Agent_CTO disagrees. Revised: 'Most participants expressed support, with notable dissent from Agent_CTO.'" |
| `get_action_category_and_player_capability` | Categorizes action type (Confess, Defy, etc.) and assesses proficiency | "Action type: Negotiate. Agent_CFO's proficiency: High (financial domain)." |

### 2.3 Narrative Control

| Function | What it Does | Example |
|---|---|---|
| `maybe_inject_narrative_push` | Detects repetitive loops; injects complications | "The debate has circled budget 3 times. Injecting: 'Breaking news — the board has moved up the deadline by 2 weeks.'" |
| `maybe_cut_to_next_scene` | Decides if current scene should end | "This scene has reached diminishing returns. Cut to: bilateral negotiation between CFO and CTO." |

### 2.4 Utility Functions

| Function | What it Does |
|---|---|
| `identity` | Pass-through (no modification) |
| `extract_direct_quote` | Extracts and tags direct quotes for preservation |
| `restore_direct_quote` | Re-inserts preserved quotes after processing |
| `RemoveSpecificText(substring)` | Strips specified text from event |

### 2.5 Conversation Resolution

```python
class Conversation:
    def __init__(self, model: LanguageModel,
                 players: Sequence[EntityAgent],
                 verbose: bool = False)
```

Resolves conversational events:
1. Identify who is involved in the conversation
2. Solicit each participant's contribution (from their agent or from GM's LLM)
3. Generate a coherent multi-party conversation
4. Send result as observation to all participants

**This is the key difference from A2A's monologue-based debate.** Instead of Agent A speaks → Agent B speaks → Agent C speaks, the Conversation thought chain produces an actual multi-party exchange within a single resolution step.

---

## 3. EventResolution — The Full Pipeline

### 3.1 How It Works

`EventResolution` is a `ContextComponent` on the Game Master that transforms putative events into canonical outcomes.

**Flow:**
```
Agent attempts action
    → Stored in GM memory with PUTATIVE_EVENT_TAG
    → EventResolution.pre_act() triggered (when action_spec.output_type == RESOLVE)
        → 1. Retrieve latest PUTATIVE_EVENT from memory
        → 2. Create InteractiveDocument with full context:
              - Instructions (GM role)
              - Player characters (who's in the simulation)
              - Relevant memories
        → 3. Run thought chain:
              for thought_fn in event_resolution_steps:
                  event = thought_fn(document, event, active_player)
        → 4. (Optional) Ask LLM: "Which agents are aware of this event?"
              → Queue observations for those agents via MakeObservation
        → 5. Store resolved event with EVENT_TAG
```

### 3.2 Example: Debate Claim Resolution

**Putative event:** "Agent_CFO says: 'The budget committee has agreed to phase the investment over 3 years.'"

**Thought chain:**
1. `AccountForAgencyOfOthers` — "Did the budget committee actually agree? Let me check with each member..." → Agent_CTO says no → Revised: "Agent_CFO proposed phasing over 3 years. Agent_CTO has not agreed."
2. `result_to_causal_statement` — "Because Agent_CFO proposed 3-year phasing, the group is now debating the timeline specifics."
3. `determine_success_and_why` — "Was this proposal accepted? Partially — timeline concept accepted, but duration disputed."

**Canonical event:** "Agent_CFO proposed 3-year budget phasing. The concept of phasing was accepted by the majority, but Agent_CTO disputes the 3-year duration, insisting on 18 months."

---

## 4. Game Master Components

### 4.1 `SwitchAct` — Request Router

The GM's ActingComponent. Routes based on `output_type`:

```python
output_type → handler mapping:
  NEXT_ACTING       → NextActing component (who speaks next?)
  MAKE_OBSERVATION   → MakeObservation (format event for agent perception)
  RESOLVE           → EventResolution (adjudicate what happened)
  TERMINATE         → Terminate (should simulation end?)
```

### 4.2 `NextActing` — Turn Scheduling

Determines which agent acts next. Supports schemes:
- **Round-robin** — predictable, fair
- **Random** — unpredictable, emergent
- **Scene-based** — `NextActingFromSceneSpec` reads from SceneTracker
- **Custom** — any logic that returns an agent name

**A2A comparison:** A2A's `SpeakerSelector` does weighted probabilistic selection. Concordia's `NextActing` is more flexible and can be swapped per scene.

### 4.3 `MakeObservation` — Perception Filter

Formats events into agent-specific observations. Not all agents see all events. The GM decides:
- Who observed this event?
- How would they perceive it?
- What context should accompany the observation?

### 4.4 `SceneTracker` — Phase Management

Manages progression through scenes. Each scene has:
- Participants
- Premise (initial framing)
- Rules (which components are active)
- Transition conditions

### 4.5 `WorldState` — Global Variables

Key-value store for simulation state:
```python
world_state = {
    "budget_proposal_status": "under_debate",
    "deadline": "2026-06-01",
    "coalition_a": ["CFO", "HR"],
    "coalition_b": ["CTO", "Ops"],
}
```

Accessible to all GM components. Updated by EventResolution.

### 4.6 `Terminate` — End Conditions

Checks if simulation should end based on:
- Max steps reached
- Game state condition met (e.g., consensus achieved)
- All scenes completed
- LLM judges "nothing more to discuss"

---

## 5. A2A Moderator Adaptation

### 5.1 Current Moderator (One-Shot)

```
moderator_intro()   → single LLM call → framing text
moderator_challenge() → single LLM call → one interjection
moderator_synthesis() → single LLM call → summary text
```

### 5.2 Proposed: Moderator with Thought Chains

```python
async def moderator_challenge_v2(transcript, analytics, agent_profiles):
    doc = InteractiveDocument(model)

    # Step 1: Assess debate state
    state = doc.open_question(
        f"Given this transcript:\n{transcript}\n\n"
        "Is the debate making progress? Are agents repeating themselves? "
        "Is there premature consensus or unresolved conflict?"
    )

    # Step 2: Identify weak arguments
    weak = doc.open_question(
        "Which arguments in the debate are weakest or unsupported? "
        "Which agent is making claims without evidence?"
    )

    # Step 3: Check for forced consensus
    consensus_real = doc.yes_no_question(
        f"The current consensus score is {analytics['consensus']}. "
        "Based on the actual transcript, does this reflect genuine agreement, "
        "or are agents being sycophantic/going along to avoid conflict?"
    )

    # Step 4: Decide intervention
    if not consensus_real:
        intervention = doc.open_question(
            "The consensus appears artificial. Which agent should be challenged "
            "and what specific question should the moderator ask to expose "
            "the underlying disagreement?"
        )
    elif "repeating" in state.lower():
        intervention = doc.open_question(
            "The debate is going in circles. What new framing, constraint, "
            "or provocative question should the moderator introduce to "
            "break the loop?"
        )
    else:
        intervention = doc.open_question(
            f"The weakest argument is: {weak}\n"
            "Craft a moderator challenge that directly addresses this weakness "
            "and forces the agent to either strengthen their argument or concede."
        )

    return intervention
```

### 5.3 Proposed: Event Resolution for Round Outcomes

```python
async def resolve_round_outcome(transcript, round_num):
    """After each round, produce a canonical outcome statement."""
    doc = InteractiveDocument(model)

    # What was proposed?
    proposals = doc.open_question(
        f"Round {round_num} transcript:\n{transcript}\n\n"
        "List every concrete proposal made in this round."
    )

    # What was agreed?
    agreements = doc.open_question(
        "For each proposal, was it accepted, rejected, or tabled? "
        "Only mark as accepted if there was explicit support from a majority."
    )

    # Verify agency
    verified = doc.open_question(
        "For each agreement, verify: did the agents actually agree, "
        "or did someone claim consensus that wasn't there? "
        "List only verified agreements."
    )

    # Canonical outcome
    outcome = doc.open_question(
        f"Verified agreements: {verified}\n\n"
        "Write the canonical round outcome in 2-3 sentences. "
        "This will be treated as fact for subsequent rounds."
    )

    return {
        "proposals": proposals,
        "agreements": agreements,
        "canonical_outcome": outcome,
    }
```

---

## 6. Narrative Control for A2A

### 6.1 Breaking Loops (inspired by `maybe_inject_narrative_push`)

```python
async def check_for_repetition(transcript, last_n_turns=6):
    """Detect if debate is going in circles and inject disruption."""
    recent = transcript[-last_n_turns:]

    doc = InteractiveDocument(model)
    is_repetitive = doc.yes_no_question(
        f"Recent debate:\n{format_turns(recent)}\n\n"
        "Are the agents repeating similar points without progress?"
    )

    if is_repetitive:
        disruption = doc.open_question(
            "The debate is looping. Suggest a plausible external event "
            "or new constraint that would force agents to rethink their positions. "
            "Examples: deadline moved up, budget reduced, new stakeholder joins, "
            "competitor announced similar initiative."
        )
        return {"inject": True, "event": disruption}

    return {"inject": False}
```

### 6.2 Scene Transitions (inspired by `maybe_cut_to_next_scene`)

```python
async def should_change_phase(transcript, current_phase, round_num):
    """Decide if debate should transition to a new phase."""
    doc = InteractiveDocument(model)

    should_cut = doc.yes_no_question(
        f"Current phase: {current_phase} (round {round_num})\n"
        f"Recent transcript:\n{format_recent(transcript)}\n\n"
        "Has this phase accomplished what it could? Should we move on?"
    )

    if should_cut:
        next_phase = doc.multiple_choice_question(
            "What should the next phase be?",
            ["Bilateral negotiations", "Formal proposals", "Final voting",
             "Open floor debate", "Expert testimony"]
        )
        return {"transition": True, "next_phase": next_phase}

    return {"transition": False}
```

---

## 7. Dialogic Game Master — Most Relevant Prefab

The `dialogic__GameMaster` is Concordia's closest equivalent to A2A's moderator:

- **Conversation management** — enforces turn-taking in dialogue
- **Repetition detection** — automatically ends conversations going in circles
- **Speech-only actions** — constrains agents to verbal actions only (relevant for debate)

Combined with `dialogic_and_dramaturgic__GameMaster`, you get:
- **Scene management** — structured episodes with transitions
- **Premise injection** — each scene opens with a framing statement
- **Participant control** — different agents participate in different scenes

**This is the model for A2A's enhanced moderator:** A debate moderator that manages conversation flow, detects repetition, enforces turn discipline, and transitions between debate phases.

---

*See also:* [04_A2A_Whisper_Channels_Agent_Politics.md](./04_A2A_Whisper_Channels_Agent_Politics.md) for A2A's private communication system.
