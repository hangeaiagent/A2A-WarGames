<div align="center">

# A2A War Games

**Multi-agent stakeholder debate simulator powered by autonomous LLM agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D.svg?logo=vue.js&logoColor=white)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/Tests-593%20passing-brightgreen.svg)]()

[Live Demo](http://crew-ai.me/) · [Quick Start](#quick-start) · [Architecture](#architecture) · [API Reference](#api-reference) · [Contributing](CONTRIBUTING.md)

</div>

---

A2A War Games is an open research platform for studying **multi-agent negotiation and conflict**. Each stakeholder is a fully autonomous LLM agent with its own persona, constraints, cognitive biases, and BATNA (Best Alternative to a Negotiated Agreement). Agents debate in structured rounds directed by a Moderator agent — no human scripts the outcome.

Built as a testbed for the [A2A (Agent-to-Agent) protocol](https://github.com/google/a2a-spec) applied to real-world scenarios: organizational change management, policy deliberation, geopolitical simulation, ethics debates, and more.

> **Try it live at [crew-ai.me](http://crew-ai.me/)**

---

## Why A2A War Games?

- **Fully autonomous agents** — each stakeholder has a rich persona (20+ fields), hard constraints it will _never_ cross, cognitive biases that shape reasoning, and a BATNA it falls back to when negotiation fails
- **Structured debate protocol** — a Moderator agent frames rounds, challenges weak arguments, forces dissent when consensus forms too quickly, and synthesizes outcomes
- **Real-time Observer** — an independent analysis agent extracts sentiment, stance shifts, coalition formation, and risk signals after every turn
- **Any LLM, any model** — works with OpenAI, Anthropic Claude, Ollama, Groq, Together, LM Studio, DeepSeek, Mistral, or any OpenAI-compatible endpoint. Each agent can run on a _different_ model
- **Live streaming UI** — Vue 3 frontend with SSE-powered real-time transcript, thinking indicators, analytics panels, and consensus gauges
- **Built-in scenarios** — four ready-to-run scenarios covering smart city governance, geopolitics, philosophy, and psychology
- **Concordia-inspired memory** — optional formative memories, self-reflection, and thought chains for deeper agent behavior (feature-flagged)
- **Production-ready** — Supabase auth with Row-Level Security, i18n (EN/FR/ES), full accessibility, 593 tests passing

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Any OpenAI-compatible LLM endpoint (or a local model via Ollama / LM Studio)

### Backend

```bash
# Clone the repo
git clone https://github.com/ArtemisAI/A2A-WarGames.git
cd A2A-WarGames

# Set up Python environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — set LLM_BASE_URL, LLM_API_KEY, LLM_DEFAULT_MODEL
# SQLite works out of the box for local development

# Start the API server
uvicorn backend.main:app --reload --port 8000

# Load a demo scenario
curl -X POST http://localhost:8000/api/projects/seed-demo
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Configure your LLM

Open **Settings** in the UI (or use the API) to connect your LLM provider:

```bash
curl -X POST http://localhost:8000/api/settings/ \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "default_model": "gpt-4o",
    "chairman_model": "gpt-4o",
    "council_models": ["gpt-4o"]
  }'
```

That's it. Go to **Sessions** → create a new session → hit **Run** and watch the debate unfold.

---

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                          A2A ENGINE                              │
│                     backend/a2a/engine.py                        │
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
│   │  Mayor Chen · Dir. Okafor · Cllr. Vasquez · CFO Hartley│   │
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
│  REST API · SQLite / PostgreSQL · optional Supabase auth + RLS   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼─────────────────────────────────────┐
│  Vue 3 Frontend  (frontend/)                                      │
│  Live transcript · Consensus gauge · Agent cards · Analytics      │
└───────────────────────────────────────────────────────────────────┘
```

### Core Modules — `backend/a2a/`

| File | Purpose |
|------|---------|
| `engine.py` | `A2AEngine` — main async loop: rounds, turns, moderator calls, SSE streaming |
| `moderator.py` | Moderator agent — frames rounds, challenges weak arguments, synthesizes |
| `prompt_compiler.py` | Builds each agent's system prompt from structured persona data |
| `speaker_selection.py` | Selects agents per turn (influence-weighted, mute-aware) |
| `observer.py` | Post-turn structured extraction — sentiment, stance, signals |
| `llm_client.py` | Async OpenAI-compatible HTTP client with streaming support |
| `pre_warm.py` | Background agenda + moderator opening at session creation |
| `concordia/` | Concordia-inspired memory: formative memories, self-reflection, thought chains |

### Debate Flow (one round)

```text
1.  Moderator intro       → frames the strategic question for this round
2.  Speaker selection      → picks N agents weighted by influence + relevance
3.  Agent turns (A2A)      → each selected agent responds in full persona context
4.  Observer extraction    → structured data extracted from each response
5.  Moderator challenge    → probes weak arguments if consensus > threshold
6.  Agent responses        → challenged agents respond directly
7.  Moderator synthesis    → summarizes: agreements, tensions, next focus
8.  Analytics snapshot     → consensus score, coalitions, risk flags persisted
```

---

## Persona System

Each agent is compiled from a rich structured profile (20+ fields):

```json
{
  "slug": "mayor_chen",
  "name": "Mayor Chen",
  "role": "Mayor",
  "attitude": "champion",
  "cognitive_biases": ["optimism_bias", "planning_fallacy"],
  "batna": "Scale back to a pilot in one district only",
  "hard_constraints": [
    "NEVER approve anything that puts citizen data at risk of a breach",
    "NEVER exceed the $40M budget cap without explicit council approval"
  ],
  "adkar": { "awareness": 5, "desire": 5, "knowledge": 3, "ability": 2 },
  "grounding_quotes": [
    "I did not run for mayor to manage the status quo."
  ]
}
```

`prompt_compiler.py` assembles this into a system prompt with ADKAR change-readiness scores, salience dimensions, communication style, and an explicit **anti-sycophancy directive** — preventing agents from capitulating to social pressure mid-debate.

---

## Built-in Scenarios

| Scenario | File | Agents | Domain |
|----------|------|--------|--------|
| **Northbridge City** | `demo.json` | 5 | Smart city infrastructure — AI governance, budget, equity, labour |
| **The World Stage** | `geopolitics.json` | — | Geopolitical negotiations — trade, sovereignty, AI regulation |
| **Philosophy** | `philosophy.json` | — | Ethics debates — competing moral frameworks |
| **Psychology** | `psychology.json` | — | Behavioral science scenarios |

Load any scenario:

```bash
# Seed the demo scenario
curl -X POST http://localhost:8000/api/projects/seed-demo

# Or create your own — see backend/seed_data/ for the JSON schema
```

### Create Your Own Scenario

Scenarios are JSON files in `backend/seed_data/`. See `demo.json` for the full schema. Key persona fields:

| Field | Purpose |
|-------|---------|
| `hard_constraints` | Absolute limits the agent will _never_ cross |
| `batna` | Best alternative if negotiation fails |
| `cognitive_biases` | Biases that shape the agent's reasoning |
| `adkar` | Change-readiness scores (awareness / desire / knowledge / ability / reinforcement) |
| `grounding_quotes` | In-character voice lines injected into the system prompt |
| `communication_style` | How the agent expresses itself (e.g., `analytical_risk_focused`, `adversarial_protective`) |

---

## LLM Compatibility

Any OpenAI-compatible endpoint works. Each agent can run on a **different model**:

| Provider | Setup |
|----------|-------|
| **OpenAI** | `https://api.openai.com/v1` — `gpt-4o`, `o1`, `o3` |
| **Anthropic** | Native support — `claude-sonnet-4-6`, `claude-opus-4-6` |
| **Ollama** | `http://localhost:11434/v1` — `llama3`, `mistral`, `qwen2.5` |
| **LM Studio** | `http://localhost:1234/v1` — any GGUF model |
| **Groq** | `https://api.groq.com/openai/v1` — fast cloud inference |
| **Together AI** | `https://api.together.xyz/v1` — open models at scale |
| **DeepSeek** | `https://api.deepseek.com/v1` — reasoning models |
| **OpenRouter** | `https://openrouter.ai/api/v1` — multi-provider gateway |

Set `chairman_model` (Moderator) independently from `council_models` (stakeholder agents).

---

## Database

| Mode | Config |
|------|--------|
| **SQLite** (local dev) | `DATABASE_URL=sqlite:///./wargame.db` — works out of the box |
| **PostgreSQL** (production) | `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname` |
| **Supabase** (auth + RLS) | Set `SUPABASE_*` vars in `.env` — enables multi-tenant Row-Level Security |

Supabase auth is **optional**. Leave `SUPABASE_*` vars empty to run without authentication — perfect for local experiments and development.

---

## API Reference

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET/POST` | `/api/projects/` | List / create projects |
| `POST` | `/api/projects/seed-demo` | Load demo scenario |
| `GET/POST/PUT` | `/api/projects/{id}/stakeholders` | Stakeholder CRUD |
| `GET/POST` | `/api/sessions/` | List / create sessions |

### Session Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{id}/run` | Start A2A simulation (streaming) |
| `GET` | `/api/sessions/{id}/stream` | SSE live event stream |
| `POST` | `/api/sessions/{id}/pause` | Pause running session |
| `POST` | `/api/sessions/{id}/resume` | Resume paused session |
| `POST` | `/api/sessions/{id}/recover` | Recover incomplete session |
| `POST` | `/api/sessions/{id}/inject` | Inject moderator message |

### Analytics & Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sessions/{id}/analytics` | Consensus, sentiment, coalitions, risk |
| `GET` | `/api/sessions/{id}/messages` | Full transcript (paginated) |
| `GET/POST/PUT` | `/api/settings/` | LLM profile management |
| `POST` | `/api/settings/test-connection` | Test LLM provider connectivity |

Full interactive docs available at `/docs` when the server is running.

---

## Project Structure

```text
A2A-WarGames/
├── backend/
│   ├── a2a/                   Core A2A engine
│   │   ├── engine.py          A2AEngine — main debate loop
│   │   ├── moderator.py       Moderator LLM agent
│   │   ├── prompt_compiler.py Persona → system prompt compiler
│   │   ├── speaker_selection.py  Agent turn selection
│   │   ├── observer.py        Post-turn data extraction
│   │   ├── llm_client.py      Async OpenAI-compatible client
│   │   └── concordia/         Memory & self-reflection modules
│   ├── analytics/             Consensus, sentiment, risk, coalitions
│   ├── routers/               REST API endpoints
│   ├── seed_data/             Scenario JSON files
│   ├── models.py              SQLAlchemy ORM
│   ├── auth.py                Supabase JWT + RLS
│   └── seed.py                Scenario loader
├── frontend/
│   └── src/
│       ├── pages/             Projects · Stakeholders · Sessions · Live · Settings
│       ├── components/        Session, metrics, stakeholder, common components
│       ├── stores/            Pinia state management
│       ├── i18n/              EN / FR / ES translations
│       └── styles/            CSS design tokens
├── docs/                      Architecture and deployment docs
├── .github/workflows/         CI, secret scanning, PR quality gates
├── .env.example               Environment variable template
├── requirements.txt           Python dependencies
└── vercel.json                Frontend deployment config
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+ · FastAPI · SQLAlchemy · Pydantic |
| **Frontend** | Vue 3 · Pinia · Vite · Tailwind CSS v4 |
| **Database** | SQLite (dev) · PostgreSQL + pgvector (prod) |
| **Auth** | Supabase (optional) — JWT + Row-Level Security |
| **Streaming** | Server-Sent Events (SSE) |
| **LLM** | Any OpenAI-compatible endpoint + native Anthropic |
| **i18n** | vue-i18n — English, French, Spanish |
| **Testing** | pytest + Vitest — 593 tests |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Community & Links

| Resource | Link |
|----------|------|
| **Live Demo** | [crew-ai.me](http://crew-ai.me/) |
| **GitHub** | [github.com/ArtemisAI/A2A-WarGames](https://github.com/ArtemisAI/A2A-WarGames) |
| **HuggingFace** | [huggingface.co/ArtemisAI](https://huggingface.co/ArtemisAI) |
| **Company** | [artemis-ai.ca](https://artemis-ai.ca) — Building exceptional AI solutions |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Built with care by [Artemis AI](https://artemis-ai.ca).
