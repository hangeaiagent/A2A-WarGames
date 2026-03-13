# Claude Code Instructions — A2A War Games (Public)

See **[AGENTS.md](./AGENTS.md)** for architecture overview and build/test/run instructions.

## Quick Summary

- **Repo:** A2A War Games — multi-agent stakeholder debate simulator
- **Backend:** `backend/` — FastAPI + SQLAlchemy (SQLite default, PostgreSQL/Supabase for production)
- **Frontend:** `frontend/` — Vue 3 + Pinia + Vite + Tailwind CSS v4
- **Tests:** 593/593 passing

### Critical Rules

1. **Never commit `.env` files** — use `.env.example` as the template
2. **Commit frequently** — one logical change per commit
3. **Run tests before pushing** — `pytest tests/ -v`
4. **No Co-Authored-By lines** in commits

### LLM Configuration

Set `LLM_BASE_URL` and `LLM_API_KEY` in `.env`. The platform works with any OpenAI-compatible endpoint. Supabase auth is optional for local use.
