# A2A War Games — Stakeholder Wargame Simulation

> **A2A (Agent-to-Agent) protocol testbed**: each organizational stakeholder is a fully autonomous LLM agent with its own identity, constraints, cognitive biases, and BATNA. Agents debate in structured rounds directed by a Moderator agent — no human scripting the outcome.

**Built by [ArtemisAI](https://github.com/ArtemisAI)**

---

## What This Project Tests

**A2A War Games is a research platform for the A2A (Agent-to-Agent) protocol** — specifically, how multiple LLM agents with conflicting mandates negotiate, challenge, and reach (or fail to reach) consensus in a structured debate.

Each stakeholder is an **autonomous A2A agent**:

- Has a dedicated system prompt encoding its full persona
- Receives the same shared context (moderator framing + transcript)
- Produces independent outputs (arguments, proposals, challenges)
- Can be addressed directly by other agents via `@mention` (upcoming)
- Has configurable LLM model, temperature, token budget, and speaking priority

The **Moderator** is a separate A2A agent with its own mandate: enforce debate rules, prevent groupthink, force dissent when consensus forms prematurely.

This architecture maps directly to the A2A protocol's core primitives:

| A2A Concept             | War Games Implementation                                              |
| ----------------------- | --------------------------------------------------------------------- |
| Agent Card              | `Stakeholder` model — slug, role, persona, constraints                |
| Task                    | A wargame `Session` with a strategic question                         |
| Turn                    | One agent turn — moderator framing → agent response → observer        |
| Message                 | `SessionMessage` persisted to Supabase, streamed live via SSE         |
| Multi-agent coordination| `A2AEngine` in `backend/a2a/engine.py`                                |

---

## A2A Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         A2A ENGINE                               │
│                    backend/a2a/engine.py                         │
│                                                                  │
│   ┌─────────────┐  frames round   ┌───────────────────────┐     │
│   │  Moderator  │ ──────────────► │  Speaker Selection    │     │
│   │  Agent(LLM) │                 │  speaker_selection.py │     │
│   └─────────────┘                 └───────────┬───────────┘     │
│          ▲                                    │ N agents/turn    │
│          │ synthesis                          ▼                  │
│   ┌──────┴──────────────────────────────────────────────────┐   │
│   │         Stakeholder Agents  (parallel LLM calls)        │   │
│   │                                                         │   │
│   │  Michel · Julien · Amélie · Sarah · Marc · Karim · Simon│   │
│   │  (each runs on its own model, persona, and constraints) │   │
│   └─────────────────────────┬───────────────────────────────┘   │
│                             │ turn output                        │
│                             ▼                                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Observer  (observer.py)                                │   │
│   │  Extracts: sentiment · stance · position shift · risk   │   │
│   └─────────────────────────┬───────────────────────────────┘   │
│                             ▼                                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Analytics  (backend/analytics/)                        │   │
│   │  consensus · coalitions · influence map · risk flags    │   │
│   └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                             │ SSE event stream
┌────────────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend  (backend/)                                      │
│  REST API · Supabase PostgreSQL · multi-tenant RLS                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼─────────────────────────────────────┐
│  Vue 3 Frontend  (frontend/)                                      │
│  Live transcript · Consensus gauge · Agent cards · Analytics      │
└───────────────────────────────────────────────────────────────────┘
```

### A2A Module — `backend/a2a/`

The core of the platform. All agent-to-agent orchestration lives here:

| File | Role |
|------|------|
| `engine.py` | `A2AEngine` — main async loop: rounds, turns, moderator calls, SSE streaming |
| `moderator.py` | Moderator agent — frames rounds, challenges weak arguments, synthesizes |
| `prompt_compiler.py` | Builds each agent's full system prompt from structured persona data |
| `speaker_selection.py` | Selects which agents speak each turn (influence-weighted, mute-aware) |
| `observer.py` | Post-turn structured extraction — sentiment, stance, signals |
| `llm_client.py` | Async OAI-compatible HTTP client — any endpoint, streaming support |

### Debate Flow (one round)

```
1.  Moderator intro       → frames the strategic question for this round
2.  Speaker selection     → picks N agents weighted by influence + relevance
3.  Agent turns (A2A)     → each selected agent responds in full persona context
4.  Observer extraction   → structured data extracted from each response
5.  Moderator challenge   → probes weak arguments if consensus > threshold
6.  Agent responses       → challenged agents respond directly
7.  Moderator synthesis   → summarizes: agreements, tensions, next focus
8.  Analytics snapshot    → consensus score, coalitions, risk flags → Supabase
```

### Persona System

Each agent is compiled from a rich structured profile (20+ fields):

```python
{
  "slug": "michel",
  "role": "Fondateur & PDG",
  "cognitive_biases": ["status_quo_bias", "loss_aversion_moderate"],
  "batna": "Do nothing this year, revisit when the children take over",
  "hard_constraints": [
    "NEVER accept a black-box system",
    "NEVER accept total vendor dependency",
  ],
  "anti_sycophancy": "You are the FINAL ARBITER. You do NOT easily agree...",
  "grounding_quotes": ["Ce que je veux : un chemin praticable."],
  "adkar": {"awareness": 4, "desire": 4, "knowledge": 2, "ability": 2},
  ...
}
```

`prompt_compiler.py` assembles this into a coherent system prompt with ADKAR state, salience scores, communication style, and an explicit **anti-sycophancy directive** — preventing agents from capitulating to social pressure mid-debate.

---

## Project Structure

```
A2A-War-Games/
├── backend/
│   ├── a2a/                  ← A2A ENGINE (core orchestration)
│   │   ├── engine.py         A2AEngine — main debate loop
│   │   ├── moderator.py      Moderator LLM agent
│   │   ├── prompt_compiler.py  Persona → system prompt compiler
│   │   ├── speaker_selection.py  Agent turn selection
│   │   ├── observer.py       Post-turn data extraction
│   │   └── llm_client.py     OAI-compatible async client
│   ├── analytics/            Consensus, sentiment, risk, coalitions
│   ├── routers/              REST API — projects, sessions, settings
│   ├── models.py             SQLAlchemy ORM (9 tables)
│   ├── auth.py               Supabase JWT validation + RLS injection
│   ├── database.py           Connection pool + per-request session helpers
│   └── seed.py               Demo: Northbridge City (5 agents)
├── frontend/
│   └── src/
│       ├── pages/            Projects · Stakeholders · Sessions · Live · Analytics · Settings
│       ├── components/       session/ · metrics/ · stakeholder/ · common/
│       ├── stores/           Pinia state (projects, sessions, settings)
│       └── styles/           CSS variables + dark GitHub-inspired theme
├── docs/
│   ├── HANDOVER.md           Architecture reference
│   ├── PRD.md                Product requirements
│   ├── LOCAL_TASKS.md        Tasks for local dev (not delegated to Copilot)
│   └── change-requests/      Active CRs for Copilot SWE agent
├── requirements.txt
└── .env.example
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ArtemisAI/A2A-War-Games.git
cd A2A-War-Games

# 2. Python environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — set LLM_BASE_URL, LLM_API_KEY, LLM_DEFAULT_MODEL
# SQLite works out of the box; see .env.example for Supabase setup

# 4. Start API
uvicorn backend.main:app --reload --port 8000

# 5. Load demo (7 Northbridge stakeholders)
curl -X POST http://localhost:8000/api/projects/seed-demo

# 6. Configure LLM profile
curl -X POST http://localhost:8000/api/settings/ \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://api.openai.com/v1","api_key":"sk-...","default_model":"gpt-4o","chairman_model":"gpt-4o","council_models":["gpt-4o"]}'

# 7. Frontend
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

---

## LLM Compatibility

Any OpenAI-compatible endpoint works. Each agent can run on a **different model**:

| Provider              | Notes                                      |
| --------------------- | ------------------------------------------ |
| OpenAI                | `gpt-4o`, `o1`, `o3` — streaming supported |
| Anthropic (via proxy) | Claude 3.5/4 — extended thinking captured  |
| Ollama                | Local: `llama3`, `mistral`, `qwen2.5`      |
| LM Studio             | Local GUI server                           |
| Groq                  | Fast cloud inference                       |
| Together AI           | Open models at scale                       |

Set `chairman_model` (Moderator) independently from `council_models` (Stakeholder agents).

---

## Database

| Mode                  | Config                                        |
| --------------------- | --------------------------------------------- |
| SQLite (local dev)    | `sqlite:///./wargame.db`                      |
| Supabase (production) | See `.env.example` for connection string      |

Supabase mode enables **Row-Level Security**: each user sees only their own projects + public demo projects. See [docs/HANDOVER.md](docs/HANDOVER.md) for the full RLS policy setup.

---

## API Reference

**Core Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET/POST` | `/api/projects/` | List / create projects |
| `POST` | `/api/projects/seed-demo` | Load demo demo project |
| `GET/POST/PUT` | `/api/projects/{id}/stakeholders` | Stakeholder CRUD |
| `GET/POST` | `/api/sessions/` | List / create sessions |
| `DELETE` | `/api/sessions/{id}` | Delete session |

**Session Control:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{id}/run` | Start A2A simulation with streaming |
| `GET` | `/api/sessions/{id}/stream` | SSE live event stream |
| `POST` | `/api/sessions/{id}/pause` | Pause running session |
| `POST` | `/api/sessions/{id}/resume` | Resume paused session |
| `POST` | `/api/sessions/{id}/recover` | Recover incomplete session |
| `POST` | `/api/sessions/{id}/stop` | Stop session immediately |
| `POST` | `/api/sessions/{id}/inject` | Inject moderator message |
| `POST` | `/api/sessions/{id}/continue` | Continue from checkpoint |

**Analytics & Configuration:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sessions/{id}/analytics` | Consensus, sentiment, coalitions, risk |
| `GET` | `/api/sessions/{id}/pre-warm-status` | Background pre-computation status |
| `GET` | `/api/sessions/{id}/messages` | Full transcript (paginated) |
| `GET/POST/PUT` | `/api/settings/` | LLM profile management |

---

## Roadmap

| Milestone | Status | Focus |
|-----------|--------|-------|
| **v0.3–v0.6** | ✅ COMPLETE | Base scaffolding, simulation quality, voice, auth UI, AI assistant |
| **v0.7** | ✅ COMPLETE | Agent memory (pgvector + S-BERT), private threads (whisper channels), voting matrix, i18n |
| **v0.8–v0.13+** | ✅ COMPLETE | CR-012/CR-013: streaming hardening, CLI runner, security fixes, UI polish, 490/490 tests green |
| **v0.14+** | Backlog | See [GitHub Issues →](https://github.com/ArtemisAI/A2A-War-Games/issues) for current backlog (6 open issues) |

All tracked work and backlog: [GitHub Issues →](https://github.com/ArtemisAI/A2A-War-Games/issues)

---

*FastAPI · Vue 3 · Supabase · Any OAI-compatible LLM*
*© 2026 [ArtemisAI](https://github.com/ArtemisAI) — MIT License*
