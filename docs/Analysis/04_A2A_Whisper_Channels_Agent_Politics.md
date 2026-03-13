# A2A Whisper Channels — Agent Politics & Private Negotiation

**Feature:** CR-011 Private Threads
**Status:** Backend fully implemented (v0.7+); frontend UI pending

---

## 1. Overview

Whisper channels are **private bilateral threads between two agents** running parallel to the main public debate. They enable:
- Secret negotiations and side deals
- Coalition-building invisible to other stakeholders
- Information gathering and strategic intelligence
- Political maneuvering — visible only to the human overseer

**Key properties:**
- One-to-one bilateral only (no group chats)
- Run between public rounds (not during them)
- Configurable depth (default: 2 exchanges, ~4 messages total)
- Per-session quota (default: 3 initiations per agent)
- Feature-flagged: `feature_flags.private_threads`

---

## 2. Architecture

### 2.1 End-to-End Flow

```
ROUND N COMPLETES
    ↓
Engine: _run_private_opportunity_window(round_num)
    ↓
SSE: whisper_opportunity_start {round: N}
    ↓
All agents queried in parallel: _agent_private_decision()
    → Each decides: initiate? with whom? opening message?
    ↓
Threads created (first-come-first-served, dedup by frozenset)
    ↓
For each thread:
    1. Opening message (initiator → target)
    2. Target accepts/declines via _agent_private_response()
    3. If accepted: exchange loop (depth-1 additional rounds)
    4. Thread closes
    5. Perspective-correct summaries generated
    6. Observer extracts memories (if agent_memory enabled)
    ↓
SSE: whisper_opportunity_end {threads_opened: N}
    ↓
ROUND N+1 BEGINS
    → Agents who participated have private context injected into system prompt
    → They act on private commitments naturally without revealing them
```

### 2.2 Agent Decision Logic

Each agent receives a private decision prompt (temp=0.6, 512 tokens):

```
You have {remaining_quota} private conversation initiation(s) remaining.
You may optionally open a private bilateral channel with ONE other participant.
Private conversations are NOT visible to others or the moderator.
Use this strategically: coalition-building, side deals, information gathering.
```

**Expected JSON response:**
```json
{
    "initiate_private": true,
    "target_agent": "agent-slug",
    "reason": "internal reasoning (max 30 words)",
    "opening_message": "The actual message sent to the target"
}
```

### 2.3 Thread Lifecycle

```
INITIATE → OPEN → ACCEPT/DECLINE → EXCHANGE LOOP → CLOSE
                    ↓ (decline)
                    DECLINED
```

**Accept/Decline** — Target agent decides via `_agent_private_response()`:
```json
{
    "accept_private": true/false,
    "response": "message content",
    "reason": "internal reasoning"
}
```

**Continuation** — `_agent_private_continue()` (temp=0.7, 300 tokens). Alternates initiator ↔ target up to `depth-1` additional exchanges.

---

## 3. Quota System

| Mode | Formula | Default |
|---|---|---|
| `fixed` | All agents get same quota | 3 per agent |
| `power_proportional` | `ceil(base_quota × influence / max_power)`, floor=1 | Varies by agent |

**Quota rules:**
- Only consumed by *initiating* threads (responding is free)
- Per-session; resets on new session
- Tracked in-memory as `_private_quotas: dict[str, int]`

---

## 4. Data Model

### 4.1 Database Tables

**`private_threads`:**
| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `session_id` | FK → sessions | CASCADE delete |
| `initiator_slug` | VARCHAR(100) | Who opened the thread |
| `target_slug` | VARCHAR(100) | Who was invited |
| `round_opened` | INTEGER | Which round |
| `status` | VARCHAR(20) | `open` / `closed` / `declined` |
| `created_at` | TIMESTAMPTZ | |

**Unique constraint:** `(session_id, initiator_slug, target_slug)`

**`private_messages`:**
| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `thread_id` | FK → private_threads | CASCADE delete |
| `session_id` | FK → sessions | |
| `speaker_slug` | VARCHAR(100) | |
| `content` | TEXT | The message |
| `internal_reason` | TEXT | Agent's reasoning — **NEVER sent to other agent or SSE** |
| `round_num` | INTEGER | |
| `turn` | INTEGER | |

### 4.2 SessionConfig Extensions

```python
private_thread_limit      = Column(Integer, default=3)     # base quota
private_thread_depth      = Column(Integer, default=2)     # max exchanges
private_thread_quota_mode = Column(String(20), default="fixed")
```

---

## 5. How Private Insights Propagate

### 5.1 System Prompt Injection

After a thread closes, a perspective-correct summary is generated for each participant:

```python
def _summarize_private_thread(thread_msgs, agent_a, agent_b) -> str:
    lines = [f"You spoke privately with {agent_b['name']} before this round."]
    for m in thread_msgs:
        lines.append(f"{m['name']}: {m['content'][:200]}")
    return "\n".join(lines)
```

Injected into the agent's next public turn as:
```
[PRIVATE CONTEXT — NOT TO BE DISCLOSED DIRECTLY]
You spoke privately with Bob. You agreed to schedule a sync post-vote.
Act on these private commitments naturally, without revealing them explicitly.
```

### 5.2 Memory Integration (CR-010 × CR-011)

When both `agent_memory` and `private_threads` flags are enabled:

1. Observer extracts memories from private transcript:
   - Types: `private_agreement`, `private_concession`, `private_intelligence`
   - Stored in `AgentMemory` with `source = "private_thread"`
   - Embedded as `vector(384)` for semantic retrieval

2. On subsequent public turns, agent's `_retrieve_memories()` includes private memories via pgvector semantic search

3. **Moderator isolation:** Moderator's memory retrieval explicitly excludes `private_*` memory types

### 5.3 Information Isolation Matrix

| Content | Participants | Other Agents | Moderator | Observer | Human Overseer |
|---|---|---|---|---|---|
| Message content | ✅ | ❌ | ❌ | ✅ (extraction) | ✅ (SSE + API) |
| Internal reasoning | ❌ (own only) | ❌ | ❌ | ❌ | ✅ (DB only) |
| Private memories | ✅ (own only) | ❌ | ❌ | ✅ | ✅ |
| Thread existence | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## 6. SSE Events

| Event | Payload | When |
|---|---|---|
| `whisper_opportunity_start` | `{round}` | Window opens |
| `whisper_thread_open` | `{thread_id, initiator, target, round}` | Thread created |
| `whisper_turn_end` | `{thread_id, speaker, content, round}` | Message sent |
| `whisper_thread_close` | `{thread_id, outcome}` | Thread ends |
| `whisper_opportunity_end` | `{threads_opened}` | Window closes |

**Note:** `internal_reason` is NEVER sent over SSE.

---

## 7. Current Limitations

| Limitation | Reason | Concordia Comparison |
|---|---|---|
| **Bilateral only** | Complexity; no group threads | Concordia GM mediates all communication (supports N-party) |
| **Between-round only** | Would disrupt main loop timing | Concordia supports mid-turn communication via `Conversation` thought chain |
| **No mid-thread strategy** | Agents don't plan across private + public turns | Concordia's `Plan` component spans all contexts |
| **Summaries are text-only** | Truncated to 200 chars per message | Concordia uses associative memory retrieval (richer) |
| **No trust modeling** | No explicit trust update from private interactions | Concordia's relationship component tracks trust per pair |
| **Insights don't compound** | Private context is per-window; doesn't accumulate across rounds | Concordia memories persist and compound |
| **No coalition tracking** | System doesn't track which agents are aligned privately | Could be derived from thread patterns + memory |
| **Moderator is blind** | By design — but moderator can't detect shadow coalitions | Concordia GM sees all; A2A chose deliberate opacity |

---

## 8. Enhancement Opportunities (Concordia-Inspired)

### 8.1 Coalition Detection from Whisper Patterns

```python
# Track bilateral thread frequency and agreement rates
coalition_graph = {}
for thread in all_threads:
    pair = frozenset({thread.initiator, thread.target})
    if pair not in coalition_graph:
        coalition_graph[pair] = {"threads": 0, "agreements": 0}
    coalition_graph[pair]["threads"] += 1
    if thread.status == "closed":  # not declined
        coalition_graph[pair]["agreements"] += 1

# Agents with 2+ successful threads are likely coalition partners
```

### 8.2 Trust Updates from Private Interactions

After each private exchange, update relationship state:
```python
if accepted and positive_sentiment:
    relationships[(initiator, target)].trust += 0.15
    relationships[(initiator, target)].alliance += 0.1
elif declined:
    relationships[(initiator, target)].trust -= 0.1
```

### 8.3 Strategic Private-Public Planning

Agents should plan their private and public moves together:
```
"My plan: In private, secure Bob's support on timeline.
 In public, propose phased approach knowing Bob will back me.
 If Bob declines privately, pivot to alliance with Carol instead."
```

### 8.4 Compounding Private Context

Instead of single-window summaries, maintain a running private dossier per agent:
```python
private_dossiers[agent_slug].append({
    "round": round_num,
    "partner": partner_slug,
    "agreements": [...],
    "intelligence": [...],
})
# Feed cumulative dossier into agent context, not just last window
```

### 8.5 Moderator Heuristic Awareness

While moderator shouldn't see private content, they could detect *behavioral signals*:
```
"Agent_CFO and Agent_HR suddenly aligned on the timeline proposal
 despite no public discussion of it. This may indicate a private agreement.
 Consider probing the basis for their alignment."
```

---

## 9. Key Code Locations

| Feature | File | Lines |
|---|---|---|
| Opportunity window | `backend/a2a/engine.py` | 1609-1803 |
| Agent decision | `backend/a2a/engine.py` | 1805-1835 |
| Agent response | `backend/a2a/engine.py` | 1837-1855 |
| Agent continue | `backend/a2a/engine.py` | 1857-1879 |
| Summary generation | `backend/a2a/engine.py` | 1881-1888 |
| Memory extraction | `backend/a2a/engine.py` | 1954-2050 |
| DB models | `backend/models.py` | 480-509 |
| REST endpoint | `backend/routers/sessions.py` | 1636-1672 |
| Tests | `backend/tests/test_api.py` | 1136-1314 |

---

*See also:* [00_Concordia_Integration_Gap_Analysis.md](./00_Concordia_Integration_Gap_Analysis.md) for the full integration priority matrix.
