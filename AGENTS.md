# A2A War Games — Contributing Guide

## What This Is

A2A War Games is an open research platform for studying **multi-agent negotiation and conflict**. Each stakeholder is a fully autonomous LLM agent with its own persona, constraints, cognitive biases, and BATNA. Agents debate in structured rounds directed by a Moderator agent — no human scripting the outcome.

The platform is a testbed for the [A2A (Agent-to-Agent) protocol](https://github.com/google-deepmind/a2a) applied to social science scenarios: organizational change management, policy deliberation, geopolitical simulation, ethics debates, and more.

---

## Architecture

```
backend/a2a/engine.py       — Core debate engine (A2AEngine)
backend/a2a/moderator.py    — Moderator agent (frames rounds, synthesizes)
backend/a2a/observer.py     — Observer (extracts sentiment, stance, risk per turn)
backend/a2a/speaker_selection.py — Determines speaking order per round
backend/a2a/llm_client.py   — OpenAI-compatible + Anthropic-native LLM calls
backend/a2a/pre_warm.py     — Background agenda + moderator opening at session start
backend/a2a/concordia/      — Concordia-inspired memory & self-reflection modules
backend/routers/            — FastAPI endpoints (sessions, settings, stakeholders, etc.)
backend/models.py           — SQLAlchemy models
frontend/src/               — Vue 3 + Pinia + Tailwind CSS frontend
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Any OpenAI-compatible LLM endpoint (Ollama, Groq, OpenRouter, OpenAI, Anthropic, etc.)

### Backend

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env — set LLM_BASE_URL, LLM_API_KEY, LLM_DEFAULT_MODEL

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run (from repo root)
python -m uvicorn backend.main:app --reload --port 8000
```

The backend starts at `http://localhost:8000`. API docs at `/docs`.

### Frontend

```bash
cd frontend
cp .env.example .env
# Edit .env — set VITE_API_BASE if your backend is not on the same origin

npm install
npm run dev
```

Frontend starts at `http://localhost:5173`.

### No Auth (local SQLite mode)

By default the backend uses SQLite (`DATABASE_URL=sqlite:///./wargame.db`) and Supabase auth is **optional**. Leave `SUPABASE_*` vars empty to run without authentication — fine for local experiments.

---

## Running a Debate

1. Open the frontend → **Settings** → configure your LLM provider and models
2. Go to **Stakeholders** → load a scenario (use the built-in `demo` scenario or create your own)
3. Start a **Session** → the Moderator opens the debate, agents take turns
4. Watch the live transcript, Observer analytics, and coalition dynamics in real time

---

## Creating a Custom Scenario

Scenarios are JSON files in `backend/seed_data/`. See `demo.json` for the full schema.

Key fields per stakeholder:
- `hard_constraints` — absolute limits the agent will never cross
- `batna` — best alternative to a negotiated agreement
- `cognitive_biases` — list of biases that shape the agent's reasoning
- `adkar` — change-readiness scores (awareness/desire/knowledge/ability/reinforcement)
- `grounding_quotes` — in-character voice lines injected into the system prompt

---

## LLM Configuration

The platform supports any OpenAI-compatible endpoint plus native Anthropic. Configure via the Settings page or `.env`:

| Variable | Description |
|----------|-------------|
| `LLM_BASE_URL` | Base URL for your LLM provider (e.g. `https://api.openai.com/v1`) |
| `LLM_API_KEY` | API key |
| `LLM_DEFAULT_MODEL` | Default model for stakeholder agents |
| `LLM_COUNCIL_MODELS` | Comma-separated per-agent models (one per stakeholder) |
| `LLM_CHAIRMAN_MODEL` | Model for the Moderator |

Supported presets: OpenAI, Anthropic Claude, DeepSeek, Groq, OpenRouter, Mistral, Ollama, LM Studio, Azure OpenAI, LiteLLM.

---

## Tests

```bash
pytest tests/ -v
```

593 tests covering the engine, API endpoints, observer, Concordia modules, and frontend stores.

---

## Contributing

1. Fork the repo and create a feature branch
2. Run the test suite — all 593 tests must pass
3. Open a PR with a clear description of what you changed and why

Please do not commit `.env` files or API keys. See `.gitignore`.
