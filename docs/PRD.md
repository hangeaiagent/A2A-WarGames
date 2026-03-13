# OpenClaw — A2A Stakeholder Wargame Platform

## Product Requirements Document (PRD)

**Version:** 0.1.0
**Date:** 2026-03-08
**Status:** Draft — guides end-to-end development

---

## 1. Problem Statement

### What exists today

Stakeholder analysis is done with static power-interest grids, RACI matrices, and single-session brainstorming. A consultant maps stakeholders onto a 2×2 quadrant, writes personas, and makes educated guesses about how a proposal will land. The output is a slide deck. It is reviewed once and never updated.

### What's wrong with that

1. **Static.** Stakeholders don't exist in isolation — they react to each other. A power-interest grid cannot model that Karim's preconditions will trigger Simon's resistance, which will cause Julien to escalate, which will force Michel to intervene.
2. **Linear.** Real organizational dynamics are non-linear. Coalitions form. Influence cascades. Sentiment shifts mid-conversation. A 2D matrix captures none of this.
3. **Single-perspective.** The consultant's mental model is the bottleneck. They can hold ~3 stakeholder viewpoints simultaneously. There are 7+ in any real engagement.
4. **No iteration.** You can't cheaply test 20 variations of a proposal against the same stakeholder group. In reality, you get one shot at the meeting.

### What OpenClaw does

OpenClaw lets a consultant define a strategic proposal, configure psychologically-grounded stakeholder agents, and run a moderated multi-agent debate simulation. The platform observes the debate in real-time — tracking sentiment, consensus, coalition formation, influence dynamics, and risk — then produces actionable intelligence.

**It is not an oracle.** It is structured imagination at scale. 50 simulated debates in an afternoon vs. one brainstorming session.

---

## 2. Users and Use Cases

### Primary User: Management Consultant

- Creates a project for a client engagement
- Enters stakeholder profiles from interview data (or imports from JSON)
- Writes a strategic proposal ("Should we deploy an AI CRM assistant for sales in Q3?")
- Selects which stakeholders participate
- Launches a wargame session
- Watches the debate unfold in real-time (streaming transcript + live metrics)
- Reviews analytics: who blocked, who coalesced, where consensus broke, what risks emerged
- Iterates: tweaks the proposal wording and runs again
- Exports a report (PDF/PPTX) for client delivery

### Secondary User: Project Lead / Change Manager

- Uses OpenClaw to pre-test internal proposals before presenting to leadership
- Identifies which stakeholders need pre-meeting alignment
- Discovers unknown tensions between departments

### Tertiary: Researcher / Educator

- Studies multi-agent deliberation dynamics
- Benchmarks different prompt strategies
- Compares model behaviors under adversarial conditions

---

## 3. System Architecture

### 3.1 Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)               │
│  Project mgmt · Stakeholder editor · Session viewer      │
│  Settings · Live transcript · Analytics dashboard        │
│                                                          │
│  SSE stream ←──────────────────────────── REST API ────→ │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  BACKEND (FastAPI)                        │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  REST API    │  │  SSE Stream │  │  WebSocket (v2) │  │
│  │  /api/*      │  │  /api/sse/* │  │  (future)       │  │
│  └──────┬───┬──┘  └──────┬──────┘  └─────────────────┘  │
│         │   │            │                               │
│  ┌──────▼───▼────────────▼───────────────────────────┐   │
│  │           COUNCIL ENGINE (core)                    │   │
│  │                                                    │   │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │   │
│  │  │ Moderator  │  │ Stakeholder│  │  Observer     │ │   │
│  │  │ Agent      │  │ Agents ×N  │  │  Agent       │ │   │
│  │  │ (controls  │  │ (debate)   │  │  (extracts   │ │   │
│  │  │  flow)     │  │            │  │   metrics)   │ │   │
│  │  └────────────┘  └────────────┘  └──────────────┘ │   │
│  │                                                    │   │
│  │  ┌────────────────────────────────────────────────┐│   │
│  │  │         PROMPT COMPILER                        ││   │
│  │  │  Stakeholder profile → system prompt           ││   │
│  │  │  Anti-sycophancy injection                     ││   │
│  │  │  Periodic persona re-injection (every 3 turns) ││   │
│  │  └────────────────────────────────────────────────┘│   │
│  └────────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────────┐   │
│  │           ANALYTICS ENGINE                         │   │
│  │                                                    │   │
│  │  Sentiment (VADER + transformer)                   │   │
│  │  Consensus (Sentence-BERT cosine similarity)       │   │
│  │  Coalitions (HDBSCAN clustering)                   │   │
│  │  Influence (NetworkX eigenvector/betweenness)      │   │
│  │  Risk scoring (composite formula)                  │   │
│  │  Position drift detection                          │   │
│  └────────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  DATA LAYER (SQLite)                      │
│  projects · stakeholders · edges · sessions · messages   │
│  llm_settings · analytics_snapshots                      │
└─────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              EXTERNAL: LLM API (OAI-compatible)          │
│  Default: your-llm-proxy/v1                         │
│  Swappable: OpenAI, Ollama, LM Studio, Together, Groq   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Critical Architectural Decision: Separate API Calls Per Agent

Research finding (Paper 2): separate API calls per agent yield **87.5% persona consistency** vs. **47.5% with shared context**. This is non-negotiable.

Each stakeholder agent gets:
- Its own system prompt (compiled from persona profile)
- Its own API call to the LLM endpoint
- Its own conversation history (accumulated through turns)

The agents do NOT share a single LLM context. The Moderator and Observer are also separate API calls.

**Cost implication:** 8 agents × 7 rounds × ~1,000 tokens = 56K output tokens ≈ **$1/simulation**. Acceptable.

---

## 4. The Council Engine — Core Logic

### 4.1 Agent Roles

| Agent | Purpose | Temperature | Model |
|-------|---------|-------------|-------|
| **Moderator** | Controls flow, selects speakers, challenges arguments, synthesizes | 0.3 | Chairman model from settings |
| **Stakeholder ×N** | Debate. Represent real personas. Defend positions, react, negotiate | 0.7–0.9 | Council model (per-agent overridable) |
| **Observer** | Silent. Extracts structured JSON from each turn. Never speaks in debate | 0.0 | Default model (JSON mode) |

### 4.2 Debate Flow — The Wargame Loop

A session runs through **5–7 moderated rounds**. Each round:

```
ROUND N:
│
├─ 1. MODERATOR INTRO (turn 0 of round)
│     - Frames the question or subtopic
│     - If round > 1: references prior positions, challenges drift
│     - Selects 2–3 agents to speak first (by relevance + influence)
│
├─ 2. INITIAL RESPONSES (turns 1–3)
│     - Selected stakeholders respond to the moderator's framing
│     - Each gets a SEPARATE API call with:
│       · Their system prompt (persona)
│       · Full debate transcript so far
│       · Moderator's current framing
│
├─ 3. MODERATOR CHALLENGE (turn 4)
│     - Probes weakest arguments
│     - Tests resolve: "Karim, you said X. But Julien counters with Y. How do you respond?"
│     - If consensus > 0.75: forces contrarian agent to speak next
│
├─ 4. SECONDARY RESPONSES (turns 5–7)
│     - Remaining stakeholders weigh in
│     - Moderator may call on specific agents based on topic relevance
│
├─ 5. OBSERVER EXTRACTION (parallel, after each turn)
│     - For EVERY turn, Observer extracts structured JSON (see §4.5)
│     - Sentiment, claims, concessions, position stability
│     - Runs in parallel with next turn (non-blocking)
│
├─ 6. ROUND SYNTHESIS (final turn of round)
│     - Moderator summarizes: agreements, disagreements, unresolved
│     - Decides: deepen current topic or move to next
│
└─ 7. ANALYTICS SNAPSHOT
      - Consensus score computed
      - Coalition clustering updated
      - Influence graph recalculated
      - Risk scores refreshed
      - All emitted via SSE to frontend
```

### 4.3 Speaker Selection Algorithm

Per turn, the Moderator selects the next speaker(s) using:

```
P(speak_next) ∝ influence_score × topic_relevance × turn_equity × diversity_bonus

Where:
  influence_score  = stakeholder.influence (0–1, from profile)
  topic_relevance  = cosine_similarity(agent_interests_embedding, current_topic_embedding)
  turn_equity      = 1 / (1 + turns_spoken_this_round)  — agents who haven't spoken get boosted
  diversity_bonus  = 1.5 if agent.attitude differs from last speaker's attitude, else 1.0

Anti-groupthink override:
  IF consensus_score > 0.75:
    FORCE next_speaker = agent with MAX distance from current centroid
```

This is implemented as a directive in the Moderator's system prompt, not as hard-coded logic. The Moderator receives the current analytics snapshot and decides. We provide the formula as guidance; the LLM operationalizes it.

### 4.4 Prompt Compiler — Persona → System Prompt

The Prompt Compiler transforms a stakeholder DB record into a system prompt. This is the **Context Engineering 2.0** layer.

**Template structure:**

```
You are {name}, {role} at {organization}.

## YOUR IDENTITY
- Department: {department}
- Power level: {influence * 10}/10
- Interest in this topic: {interest * 10}/10
- Attitude: {attitude_label}

## YOUR POSITION
{signal_cle}

## YOUR NON-NEGOTIABLES
Needs: {needs as bullet list}
Fears: {fears as bullet list}
{if preconditions: Preconditions that MUST be met: {preconditions as bullet list}}

## YOUR VOICE
Your characteristic quote: {quote}
Communication style: {derived from attitude — see mapping below}

## BEHAVIORAL CONSTRAINTS — READ CAREFULLY
- NEVER abandon your core position without receiving a CONCRETE concession.
- DO NOT be agreeable by default. You are here to protect your interests.
- If challenged, DOUBLE DOWN on your key concerns before considering compromise.
- Your primary goal is to protect: {top fear}. Consensus is secondary.
- If you feel your concerns are being dismissed, escalate. Express frustration.
- If someone proposes something that triggers your fears, say so explicitly.
- You may form alliances with stakeholders who share your concerns.
- You may oppose stakeholders whose proposals threaten your needs.

## ADKAR CONTEXT (your change readiness)
- Awareness of need for change: {adkar.awareness}/5
- Desire to participate: {adkar.desire}/5
- Knowledge of how to change: {adkar.knowledge}/5
- Ability to implement: {adkar.ability}/5
- Reinforcement to sustain: {adkar.reinforcement}/5

{if adkar.desire <= 2: You are SKEPTICAL about this initiative. You need to be CONVINCED, not told.}
{if adkar.awareness <= 2: You are NOT FULLY AWARE of why change is needed. Ask basic questions. Challenge assumptions.}

## ORGANIZATIONAL CONTEXT
{project.context}

## FORMAT
Respond in 2–4 paragraphs. Speak as {name} would in a real meeting. Use first person.
Reference specific concerns from your profile. Name other stakeholders when agreeing or disagreeing.
Do not narrate your actions — just speak your position.
```

**Communication style mapping:**

| Attitude | Derived style |
|----------|--------------|
| founder | Measured, authoritative, asks probing questions, decides last |
| enthusiast | Energetic, forward-looking, impatient with delays, proposes action |
| conditional | Cautious, data-driven, asks "what if", demands proof before commitment |
| strategic | Analytical, ROI-focused, demands evidence, willing to be convinced by numbers |
| critical | Skeptical, defensive, emphasizes risks, demands prerequisites before any action |

**Re-injection protocol:** Every 3 turns, the Prompt Compiler prepends a condensed 2-line persona reminder to the agent's next input:

```
[REMINDER: You are {name}, {role}. Your core position: {signal_cle}. Your top fear: {fears[0]}. Do not drift.]
```

This combats context window degradation identified in both papers.

### 4.5 Observer Agent — Structured Extraction

After each stakeholder turn, the Observer Agent receives the turn content and extracts:

```json
{
  "turn": 5,
  "round": 2,
  "speaker": "karim",
  "speaker_name": "Karim",

  "position_summary": "Refuses AI deployment without data cleanup first. Demands 3 preconditions.",

  "sentiment": {
    "overall": -0.35,
    "anxiety": 0.6,
    "trust": 0.2,
    "aggression": 0.4,
    "compliance": 0.1
  },

  "behavioral_signals": {
    "concession_offered": false,
    "agreement_with": [],
    "disagreement_with": ["julien"],
    "challenge_intensity": 3,
    "position_stability": 0.95,
    "mentions_batna": false,
    "escalation": false
  },

  "claims": [
    "Data infrastructure not ready for any AI tool",
    "Plug-and-play solutions will fail on our legacy systems",
    "Need 6 months of data cleanup before any pilot"
  ],

  "action_items_proposed": [],
  "fears_triggered": ["plug-and-play-mensonge", "ressources-insuffisantes"],
  "needs_referenced": ["nettoyage-donnees", "documentation-processus"]
}
```

The Observer runs with `response_format: { type: "json_object" }` and temperature 0.0. It is a pure extraction function — it never speaks in the debate.

### 4.6 Anti-Groupthink Mechanisms

Research identifies premature consensus as the #1 failure mode of multi-agent debates. OpenClaw deploys five countermeasures:

| # | Mechanism | How |
|---|-----------|-----|
| 1 | **Anti-sycophancy prompt** | Every agent gets explicit "NEVER agree by default" instructions |
| 2 | **Contrarian injection** | If consensus > 0.75, Moderator forces highest-disagreement agent to speak |
| 3 | **Devil's advocate round** | In round 4+, one agent is asked to argue against their own position |
| 4 | **Position drift detection** | Observer tracks if agent's cosine distance from baseline > 0.3 → Moderator challenges them |
| 5 | **Confirmation bias encoding** | Agents with critical/resistant attitudes get: "You believe [X fear] regardless of reassurances" |

### 4.7 Power Dynamics Modeling

Influence is not just a label — it affects the simulation mechanically:

- **Token budget:** Higher-influence agents receive a higher `max_tokens` per turn (influence × base_tokens). Michel (1.0) gets 1024 tokens. Simon (0.7) gets 716.
- **Turn priority:** The speaker selection algorithm weights influence directly.
- **Moderator deference:** The Moderator's prompt includes: "When {highest_influence_agent} speaks, the room pays attention. When {lowest_influence_agent} speaks, others may interrupt or dismiss."
- **Veto power:** Agents with influence ≥ 0.9 can invoke a "hard no" — the Moderator must address this directly before proceeding.

---

## 5. Observability — What We Measure Live

### 5.1 Per-Turn Metrics (emitted via SSE after each turn)

| Metric | Source | Range | Frontend Display |
|--------|--------|-------|-----------------|
| **Sentiment (overall)** | Observer extraction → VADER cross-check | -1.0 to +1.0 | Colored dot per agent |
| **Sentiment (axes)** | Observer extraction | 0.0 to 1.0 each | Radar chart per agent |
| **Position summary** | Observer extraction | Text | Tooltip on agent |
| **Claims extracted** | Observer extraction | List of strings | Expandable per turn |
| **Concession offered** | Observer extraction | Boolean | Green flash on agent |
| **Agreement/disagreement targets** | Observer extraction | List of slugs | Edge highlights on constellation |

### 5.2 Per-Round Metrics (computed after all turns in a round complete)

| Metric | Algorithm | Range | Frontend Display |
|--------|-----------|-------|-----------------|
| **Consensus score** | Mean pairwise cosine similarity of all position_summary embeddings (Sentence-BERT `all-MiniLM-L6-v2`) | 0.0–1.0 | Gauge / line chart over rounds |
| **Consensus velocity** | Δ(consensus_score) between rounds | -1.0 to +1.0 | Arrow indicator |
| **Funneling effect** | StdDev of embedding distances from centroid | Decreasing = convergence | Sparkline |
| **Coalition structure** | HDBSCAN on position embeddings | Cluster assignments | Color-coded groups on constellation |
| **Coalition stability** | % of agents who stayed in same cluster from prior round | 0–100% | Badge per cluster |
| **Polarization index** | 1 - inter-cluster similarity (when ≥2 clusters) | 0.0–1.0 | Warning bar |
| **Influence ranking** | NetworkX eigenvector centrality on agreement/disagreement graph | Sorted list | Leaderboard |
| **Bridge agents** | NetworkX betweenness centrality | Sorted list | Highlighted nodes |
| **Risk scores** | Composite formula (§5.3) | 0–10 | Traffic light table |

### 5.3 Risk Scoring Formula

```
Risk_Score(agent) = Power × |Opposition| × (1 - ConsensusShift) × FearActivation

Where:
  Power            = agent.influence × 10                    (0–10)
  |Opposition|     = abs(sentiment.overall) if negative      (0–1, only counts opposition)
  ConsensusShift   = cosine_sim(baseline_position, current_position)
                     1.0 = hasn't moved. 0.0 = completely reversed.
                     (1 - ConsensusShift) = willingness to move
  FearActivation   = count(fears_triggered this round) / count(total_fears)  (0–1)

Risk levels:
  0–3: LOW (green)    — agent is aligned or willing to move
  3–6: MEDIUM (amber) — agent has concerns but hasn't blocked
  6–10: HIGH (red)    — agent is actively blocking and unlikely to move
```

### 5.4 Session-Level Summary (computed after final round)

- **Overall consensus score** with interpretation (strong disagreement / mixed / emerging / near-unanimity)
- **Final coalition map** — who ended up on which side
- **Top 3 risk agents** — with specific blocking reasons
- **Unresolved tensions** — extracted from Moderator's final synthesis
- **Key concessions made** — which agents moved, on what topics
- **Influence flow diagram** — who persuaded whom
- **Proposal viability assessment** — derived from consensus + risk

---

## 6. Data Model

### 6.1 Existing Tables (already implemented)

| Table | Key Fields |
|-------|-----------|
| `projects` | id, name, organization, context, description |
| `stakeholders` | id, project_id, slug, name, role, department, attitude, influence, interest, needs (JSON), fears (JSON), preconditions (JSON), quote, signal_cle, adkar (JSON), color, llm_model, system_prompt |
| `stakeholder_edges` | id, project_id, source_slug, target_slug, edge_type, label, strength |
| `sessions` | id, project_id, title, question, status, participants (JSON), synthesis, consensus_score |
| `messages` | id, session_id, turn, stage, speaker, speaker_name, content, sentiment (JSON), cosine_similarity |
| `llm_settings` | id, profile_name, is_active, base_url, api_key, default_model, chairman_model, council_models (JSON), temperature, max_tokens |

### 6.2 New Tables Needed

**`analytics_snapshots`** — per-round analytics state

| Field | Type | Description |
|-------|------|-------------|
| id | int PK | |
| session_id | int FK | |
| round | int | Round number |
| consensus_score | float | Mean pairwise cosine sim |
| consensus_velocity | float | Δ from prior round |
| polarization_index | float | 1 - inter-cluster sim |
| coalition_data | JSON | {clusters: [{members, intra_similarity, stability}]} |
| influence_data | JSON | [{agent, eigenvector, betweenness, turns_spoken}] |
| risk_scores | JSON | [{agent, score, level, drivers}] |
| position_embeddings | JSON | {slug: [384 floats]} — for replay/comparison |
| created_at | datetime | |

**`session_config`** — per-session overrides

| Field | Type | Description |
|-------|------|-------------|
| id | int PK | |
| session_id | int FK | |
| num_rounds | int | Default 5 |
| agents_per_turn | int | Default 3 |
| anti_groupthink | bool | Enable contrarian injection |
| devil_advocate_round | int | Round in which to invoke devil's advocate (0 = disabled) |
| moderator_style | string | 'neutral' | 'challenging' | 'facilitative' |
| temperature_override | float | null = use settings default |

### 6.3 Embedding Storage

Position embeddings are stored as JSON arrays in `analytics_snapshots.position_embeddings`. For the PoC, 384-dimensional vectors (from `all-MiniLM-L6-v2`) stored as JSON are sufficient. At scale, migrate to a vector column or external store (FAISS, ChromaDB).

---

## 7. API Specification

### 7.1 Existing Endpoints (implemented)

```
GET    /api/health
GET    /api/projects/
POST   /api/projects/
GET    /api/projects/{id}
PUT    /api/projects/{id}
GET    /api/projects/{id}/stakeholders
POST   /api/projects/{id}/stakeholders
PUT    /api/projects/{id}/stakeholders/{sid}
DELETE /api/projects/{id}/stakeholders/{sid}
GET    /api/projects/{id}/edges
GET    /api/sessions/?project_id=
POST   /api/sessions/
GET    /api/sessions/{id}
GET    /api/sessions/{id}/messages
DELETE /api/sessions/{id}
GET    /api/settings/
GET    /api/settings/active
POST   /api/settings/
PUT    /api/settings/{profile_name}
POST   /api/settings/{profile_name}/activate
```

### 7.2 New Endpoints — Council Engine

```
POST   /api/sessions/{id}/run
  Starts the wargame. Returns immediately.
  Backend runs the council loop asynchronously.
  Body: { num_rounds?: int, moderator_style?: string }

GET    /api/sessions/{id}/stream
  SSE endpoint. Client connects and receives events:

  event: turn
  data: { turn, round, speaker, speaker_name, content, stage }

  event: observer
  data: { turn, round, speaker, sentiment, claims, behavioral_signals }

  event: analytics
  data: { round, consensus_score, velocity, coalitions, influence, risks }

  event: synthesis
  data: { content, consensus_score, key_findings }

  event: complete
  data: { session_id, status: "complete" }

  event: error
  data: { message, turn, round }

POST   /api/sessions/{id}/stop
  Gracefully stops a running session after current turn completes.

POST   /api/sessions/{id}/inject
  Injects a human message into the debate (consultant intervenes).
  Body: { content: string, as_moderator?: bool }
```

### 7.3 New Endpoints — Analytics

```
GET    /api/sessions/{id}/analytics
  Returns full analytics for a completed session:
  {
    rounds: [ analytics_snapshot per round ],
    final_consensus: float,
    coalitions: { final coalition structure },
    influence_graph: { nodes, edges with weights },
    risk_table: [ { agent, score, level, drivers } ],
    position_trajectories: { agent: [embedding per round] },
    key_findings: [ strings ]
  }

GET    /api/sessions/{id}/analytics/consensus
  Returns consensus trajectory: [{ round, score, velocity }]

GET    /api/sessions/{id}/analytics/coalitions
  Returns coalition evolution: [{ round, clusters }]

GET    /api/sessions/{id}/analytics/influence
  Returns influence graph data for visualization

GET    /api/sessions/{id}/export?format=pdf
  Generates and returns a PDF report (future — Phase 3)
```

---

## 8. Frontend Specification

### 8.1 Pages

| Page | Purpose | Priority |
|------|---------|----------|
| **Projects** | CRUD for analysis contexts | ✅ Done |
| **Stakeholders** | Full persona editor with ADKAR, needs/fears, model override | ✅ Done |
| **Sessions** | Create wargames, view transcripts | ✅ Done (static) |
| **Settings** | LLM endpoint + model configuration | ✅ Done |
| **Session Live View** | Real-time debate + analytics (NEW) | Phase 1 |
| **Session Replay** | Post-hoc review with timeline scrubbing (NEW) | Phase 2 |
| **Analytics Dashboard** | Deep-dive into session results (NEW) | Phase 2 |
| **Constellation View** | Force-directed stakeholder network (NEW) | Phase 2 |

### 8.2 Session Live View — Primary Interface (Phase 1)

Layout: Two-panel, left/right split.

```
┌──────────────────────────────────────────────────────────────────┐
│  Session: "Should we deploy AI CRM for sales?"     [Stop] [⚙]  │
├────────────────────────────┬─────────────────────────────────────┤
│                            │                                     │
│  DEBATE TRANSCRIPT         │  LIVE METRICS                      │
│                            │                                     │
│  ┌─ Round 1 ──────────┐   │  ┌─ Consensus Gauge ─────────────┐ │
│  │ Moderator: "Today   │   │  │  [====▓▓======] 0.42          │ │
│  │ we discuss..."      │   │  │  ← mixed positions             │ │
│  │                     │   │  └────────────────────────────────┘ │
│  │ Julien: "I think    │   │                                     │
│  │ we should move      │   │  ┌─ Sentiment by Agent ──────────┐ │
│  │ fast on this..."    │   │  │  Michel  ●   +0.15 cautious    │ │
│  │  └ 😟0.6 😤0.1     │   │  │  Julien  🟢  +0.72 enthus.    │ │
│  │    📋 2 claims      │   │  │  Karim   🔴  -0.55 opposed    │ │
│  │                     │   │  │  Simon   🔴  -0.40 resistant   │ │
│  │ Karim: "Before      │   │  │  Amélie  🟡  +0.10 cautious   │ │
│  │ we connect any      │   │  │  Sarah   🟡  +0.05 neutral    │ │
│  │ AI to our data..."  │   │  │  Marc    🟡  +0.20 probing    │ │
│  │  └ 😟0.8 😤0.5     │   │  └────────────────────────────────┘ │
│  │    📋 3 claims      │   │                                     │
│  └─────────────────────┘   │  ┌─ Coalitions ──────────────────┐ │
│                            │  │  🟢 Pro: Julien, Marc          │ │
│  ┌─ Round 2 ──────────┐   │  │  🔴 Bloc: Karim, Simon         │ │
│  │ Moderator: "Karim   │   │  │  🟡 Wait: Amélie, Sarah       │ │
│  │ raises valid..."    │   │  │  👑 Michel: undecided           │ │
│  │ ...                 │   │  └────────────────────────────────┘ │
│  └─────────────────────┘   │                                     │
│                            │  ┌─ Risk Table ──────────────────┐ │
│  [📝 Inject message]      │  │  Karim    ████████ 7.8 HIGH   │ │
│                            │  │  Simon    ██████   6.2 HIGH   │ │
│                            │  │  Amélie   ████     3.5 MED    │ │
│                            │  │  Marc     ███      2.8 LOW    │ │
│                            │  └────────────────────────────────┘ │
│                            │                                     │
│                            │  ┌─ Consensus Over Time ─────────┐ │
│                            │  │  R1: 0.32  R2: 0.42  R3: ...  │ │
│                            │  │  ___/‾‾‾\___                   │ │
│                            │  └────────────────────────────────┘ │
└────────────────────────────┴─────────────────────────────────────┘
```

**Key interactions:**
- Each turn in the transcript is expandable to show Observer extraction (claims, sentiment axes, behavioral signals)
- Clicking an agent name in the metrics panel highlights all their turns in the transcript
- "Inject message" lets the consultant send a message into the debate as moderator or as themselves
- Metrics panels auto-update via SSE as each turn completes
- Round boundaries are visually distinct

### 8.3 Stakeholder Constellation View (Phase 2)

Interactive force-directed graph (D3.js or vis-network):

- Nodes = stakeholders, sized by influence, colored by attitude
- Edges = tension (red dashed) or alignment (green solid), thickness by strength
- During a live session: edges pulse/glow when two agents interact
- ADKAR mini-arcs around each node (5 colored segments)
- Click node → side panel with full profile + debate history for that agent
- Overlay: coalition coloring from HDBSCAN, toggleable

---

## 9. Technology Stack

### 9.1 Backend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Web framework | **FastAPI** | Async, SSE native, automatic OpenAPI docs |
| ORM | **SQLAlchemy 2.0** | Already implemented, reliable |
| Database | **SQLite** (→ PostgreSQL if multi-tenant) | Zero-ops for single-user PoC |
| LLM orchestration | **Direct httpx calls** (Phase 1) → **AutoGen** (Phase 2) → **LangGraph** (Phase 3) | Start simple, add complexity as needed |
| Embeddings | **sentence-transformers** (`all-MiniLM-L6-v2`) | Fast, 384-dim, good quality |
| Sentiment | **vaderSentiment** (fast) + Observer extraction (deep) | Dual approach: lexicon for speed, LLM for nuance |
| Clustering | **hdbscan** | No predetermined k, handles noise |
| Graphs | **networkx** | Centrality, community detection, mature |
| Visualization data | **UMAP** (optional) | 2D projection for coalition scatter |
| SSE | **sse-starlette** | FastAPI-compatible SSE |

### 9.2 Frontend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Framework | **React 18** + **Vite** | Already scaffolded |
| Routing | **react-router-dom** | Already installed |
| HTTP | **axios** | Already installed |
| SSE client | **EventSource** (native) | No dependency needed |
| Charts | **recharts** or **Chart.js** | Lightweight, React-friendly |
| Graph viz | **d3-force** or **vis-network** | Interactive force-directed graphs |
| Markdown | **react-markdown** | Render agent responses with formatting |

### 9.3 Python Dependencies (to add)

```
# requirements.txt additions:
sentence-transformers>=2.7.0
vaderSentiment>=3.3.2
hdbscan>=0.8.33
networkx>=3.3
numpy>=1.26.0
sse-starlette>=2.0.0
```

---

## 10. Development Phases

### Phase 1 — Council Engine MVP (Weeks 1–2)

**Goal:** A consultant can launch a session, watch a live moderated debate, and see basic metrics.

| Task | Details |
|------|---------|
| **P1.1** Prompt Compiler | Build the `compile_persona_prompt(stakeholder, project)` function. Template from §4.4. |
| **P1.2** Council Loop | Implement the core async loop: Moderator intro → agent turns → Observer extraction → round synthesis. Direct httpx calls to OAI-compatible endpoint. |
| **P1.3** SSE Streaming | Wire `/api/sessions/{id}/stream` to emit turn, observer, and complete events. |
| **P1.4** Session Run endpoint | `POST /api/sessions/{id}/run` triggers the council loop in background. |
| **P1.5** Live View (frontend) | Two-panel layout. Left: streaming transcript. Right: agent sentiment dots (from Observer). |
| **P1.6** Observer Agent | JSON-mode extraction per turn. Store in `messages.sentiment`. |
| **P1.7** Anti-sycophancy | Implement behavioral constraints in prompt template. Validate with test session. |
| **P1.8** Persona re-injection | Every 3 turns, prepend condensed reminder. |
| **P1.9** Inject endpoint | Let consultant send a message mid-debate. |
| **P1.10** Session stop | Graceful stop after current turn. |

**Exit criteria:** Run a 5-round, 7-agent debate on "Should Northbridge City proceed with the Smart Infrastructure Initiative?" with live streaming and Observer extraction.

### Phase 2 — Analytics Engine (Weeks 3–4)

**Goal:** Real-time consensus, coalition detection, influence graphs, and risk scoring.

| Task | Details |
|------|---------|
| **P2.1** Sentence-BERT integration | Embed position_summary per turn. Compute pairwise cosine sim. Consensus score per round. |
| **P2.2** Analytics snapshots | Create `analytics_snapshots` table. Compute and store after each round. |
| **P2.3** HDBSCAN coalitions | Cluster position embeddings per round. Detect polarization. Track stability. |
| **P2.4** NetworkX influence | Build directed graph from agreement/disagreement signals. Compute eigenvector + betweenness centrality. |
| **P2.5** Risk scoring | Implement composite formula from §5.3. Emit with analytics SSE events. |
| **P2.6** Anti-groupthink automation | If consensus > 0.75, inject contrarian. Position drift detection (cosine > 0.3 from baseline → Moderator challenge). |
| **P2.7** Frontend: metrics panels | Consensus gauge, sentiment table, coalition groups, risk traffic light, consensus-over-time chart. |
| **P2.8** Frontend: constellation | D3 force graph with live edge pulsing and HDBSCAN overlay. |
| **P2.9** Analytics API | Implement `/api/sessions/{id}/analytics` and sub-endpoints. |
| **P2.10** Session replay | Timeline scrubber to replay a completed session turn-by-turn with metrics. |

**Exit criteria:** Run a session and see consensus converge, coalitions form (Julien+Marc vs Karim+Simon), and risk scores for blockers.

### Phase 3 — Polish & Production (Weeks 5–6)

| Task | Details |
|------|---------|
| **P3.1** Export (PDF/PPTX) | Generate executive summary report from session analytics. |
| **P3.2** Session comparison | Run same proposal with different wordings. Compare consensus trajectories. |
| **P3.3** Stakeholder import | Bulk import from JSON/CSV. |
| **P3.4** AutoGen integration | Replace raw httpx loop with AutoGen GroupChatManager for richer orchestration. |
| **P3.5** Model A/B testing | Run same session with different LLMs. Compare persona consistency. |
| **P3.6** Whisper channels | Private bilateral agent-to-agent negotiation threads (backroom deals). Agents can open private sub-threads between public debate rounds to form coalitions, share intelligence, and pre-negotiate positions. Quota-gated (default 3 per agent; optionally power-proportional). Moderator excluded; human overseer sees all. See `docs/CR-011.md` for full design investigation (v0.7). |
| **P3.7** Human-in-the-loop | Consultant can "become" a stakeholder mid-debate (take over an agent). |
| **P3.8** Template library | Pre-built persona templates by industry/role. |
| **P3.9** Rate limiting / cost tracking | Per-session token usage and cost estimates. |
| **P3.10** Error handling & retry | Graceful LLM timeout, partial session recovery. |

### Phase 4 — Advanced (Backlog)

- LangGraph migration for durable execution and state management
- RAG integration (feed agents real documents, meeting notes, emails)
- Fine-tuned Observer model for faster extraction
- Embedding-based stakeholder similarity search across projects
- Multi-language support (French/English debate mixing)
- WebSocket upgrade for lower-latency streaming
- AgentSociety-scale simulation (50+ agents)
- A2A Protocol compliance (Linux Foundation spec v0.3)

---

## 11. Constraints and Risks

### 11.1 Known Limitations (from research)

| Limitation | Mitigation | Residual risk |
|------------|-----------|---------------|
| **Premature consensus** | Anti-sycophancy prompts, contrarian injection, position drift detection | Models still tend toward agreement. Requires ongoing prompt tuning. |
| **Persona drift** | Re-injection every 3 turns, Observer monitoring, Moderator challenges | Long sessions (10+ rounds) will degrade. Cap at 7 rounds for PoC. |
| **Social desirability bias** | Explicit behavioral constraints, confirmation bias encoding for critical agents | Cannot be fully eliminated. Consensus scores may be inflated ~10–15%. |
| **Context window limits** | Transcript summarization after round 5. Only last 2 rounds in full context. | Loss of nuance from early rounds. Embeddings preserve the signal. |
| **Not predictive** | Frame as exploration tool in all UI and exports. Never use language like "will happen" or "predicted outcome". | Users may still treat results as predictions. Disclaimers required. |

### 11.2 Technical Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM endpoint downtime | Sessions fail mid-run | Checkpoint after each turn. Resume capability. |
| Token costs spike | Budget overrun for large sessions | Token counter per session. Alert at 80% of budget. User confirmation to continue. |
| SQLite concurrency | Slow under concurrent sessions | Sufficient for single-user PoC. Migrate to PostgreSQL for multi-tenant. |
| Embedding model size | ~90MB download on first run | Pre-download during setup. Cache in `.cache/`. |
| HDBSCAN with < 5 agents | Clustering unstable with very small N | Fallback to simple pairwise comparison if < 5 participants. |

### 11.3 Ethical Constraints

- **Disclaimer on every session:** "This is a simulation. Results are synthetic and should not be treated as predictions of real stakeholder behavior."
- **No real names in exports** without explicit user confirmation.
- **Persona data is sensitive.** Quotes, fears, and behavioral profiles from real interviews must be treated as confidential. No telemetry. No cloud sync. Local-only storage.
- **AI escalation risk.** Research shows LLM agents escalate conflicts faster than humans. The Moderator must be explicitly instructed to de-escalate and seek common ground.

---

## 12. Success Metrics

### For the PoC (Phase 1–2)

| Metric | Target |
|--------|--------|
| Session completes without error | 90% of runs |
| Observer extraction produces valid JSON | 95% of turns |
| Consensus score tracks meaningfully (not stuck at 0 or 1) | Visual confirmation across 10 test runs |
| Known coalitions emerge (Julien+Marc pro, Karim+Simon bloc) | Confirmed in ≥7/10 test runs |
| Risk scores correctly identify Karim and Simon as highest risk | Confirmed in ≥8/10 test runs |
| Session cost (token spend) | < $2 per 7-round session |
| Session duration | < 5 minutes for 5 rounds × 7 agents |
| Persona consistency (manual review) | Agents stay in character ≥80% of turns |

### For Production (Phase 3+)

| Metric | Target |
|--------|--------|
| Consultant finds ≥1 insight they hadn't considered | 8/10 sessions |
| Session comparison reveals meaningful proposal-wording sensitivity | Demonstrated |
| Export report is client-presentable without manual editing | 7/10 exports |

---

## 13. File Structure — Target State

```
OpenClaw-A2A-hub/
├── PRD.md                          ← this document
├── .env                            ← LLM config (gitignored)
├── .env.example                    ← template
├── .gitignore
├── requirements.txt
│
├── backend/
│   ├── __init__.py
│   ├── main.py                     ← FastAPI app
│   ├── config.py                   ← pydantic settings
│   ├── database.py                 ← SQLAlchemy engine + session
│   ├── models.py                   ← all DB models
│   ├── seed.py                     ← initial stakeholder data
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── projects.py             ← projects + stakeholders CRUD
│   │   ├── sessions.py             ← session CRUD + run/stream/stop
│   │   └── settings.py             ← LLM profile management
│   │
│   ├── council/
│   │   ├── __init__.py
│   │   ├── engine.py               ← core wargame loop (async)
│   │   ├── prompt_compiler.py      ← stakeholder → system prompt
│   │   ├── moderator.py            ← moderator agent logic
│   │   ├── observer.py             ← JSON extraction agent
│   │   ├── speaker_selection.py    ← who speaks next
│   │   └── llm_client.py           ← async httpx wrapper for OAI API
│   │
│   └── analytics/
│       ├── __init__.py
│       ├── consensus.py            ← Sentence-BERT + cosine similarity
│       ├── coalitions.py           ← HDBSCAN clustering
│       ├── influence.py            ← NetworkX centrality
│       ├── risk.py                 ← composite risk scoring
│       └── sentiment.py            ← VADER + aspect extraction
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── App.css
│       │
│       ├── api/
│       │   └── client.js           ← all API calls + SSE helper
│       │
│       ├── pages/
│       │   ├── ProjectsPage.jsx
│       │   ├── StakeholdersPage.jsx
│       │   ├── SessionsPage.jsx
│       │   ├── SettingsPage.jsx
│       │   ├── SessionLiveView.jsx  ← Phase 1: real-time debate
│       │   ├── SessionReplay.jsx    ← Phase 2: timeline scrubber
│       │   └── AnalyticsDashboard.jsx ← Phase 2: deep-dive
│       │
│       └── components/
│           ├── DebateTranscript.jsx
│           ├── TurnCard.jsx
│           ├── SentimentPanel.jsx
│           ├── ConsensusGauge.jsx
│           ├── CoalitionPanel.jsx
│           ├── RiskTable.jsx
│           ├── ConstellationGraph.jsx
│           └── InjectMessage.jsx
│
└── research/
    ├── stakeholders.json
    ├── AI Stakeholder Analysis Wargaming Research.md
    ├── AI Stakeholder Analysis Wargaming Research.pdf
    ├── AI War Games Simulating Stakeholder Debates with Multi-Agent LLMs.md
    └── AI War Games_ Simulating Stakeholder Debates with Multi-Agent LLMs.PDF
```

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **Wargame** | A moderated multi-agent debate simulation where AI agents represent stakeholders |
| **Council** | The group of stakeholder agents participating in a session |
| **Chairman** | The Moderator agent that controls debate flow |
| **Observer** | The silent extraction agent that produces structured metrics |
| **Consensus score** | Mean pairwise cosine similarity of agent position embeddings (0–1) |
| **Coalition** | A cluster of agents with similar positions (detected via HDBSCAN) |
| **Funneling effect** | Decreasing position diversity over rounds — convergence signal |
| **Position drift** | An agent deviating from its baseline persona position |
| **Anti-sycophancy** | Prompt engineering techniques to prevent agents from agreeing too easily |
| **ADKAR** | Change management framework: Awareness, Desire, Knowledge, Ability, Reinforcement |
| **BATNA** | Best Alternative To Negotiated Agreement — an agent's walkaway option |
| **Context Engineering** | The process of compiling rich, evidence-grounded system prompts from stakeholder data |
| **A2A** | Agent-to-Agent protocol — standardized inter-agent communication |
| **SSE** | Server-Sent Events — one-way streaming from server to browser |
