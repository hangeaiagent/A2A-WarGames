# Contributing to A2A War Games

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

1. **Fork the repo** and clone your fork
2. **Set up the development environment** — see [Quick Start](README.md#quick-start)
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

## Development Workflow

### Running Tests

All 593 tests must pass before submitting a PR.

```bash
# Backend tests
pytest backend/tests/ -v

# Frontend tests
cd frontend && npx vitest run --reporter=verbose

# Frontend build check
cd frontend && npm run build
```

### Code Style

- **Python**: Follow existing patterns — FastAPI routers, Pydantic models, SQLAlchemy ORM
- **JavaScript/Vue**: Composition API with `<script setup>`, Pinia stores, Tailwind CSS utility classes
- **Commits**: Use conventional commits — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

### Project Structure

- `backend/a2a/` — Core debate engine (engine, moderator, observer, speaker selection)
- `backend/routers/` — FastAPI REST endpoints
- `backend/analytics/` — Consensus, sentiment, coalition analysis
- `frontend/src/pages/` — Vue page components
- `frontend/src/stores/` — Pinia state management
- `frontend/src/components/` — Reusable UI components
- `backend/seed_data/` — Scenario JSON files

## What to Contribute

### Scenarios

One of the easiest ways to contribute is by adding new debate scenarios. Create a JSON file in `backend/seed_data/` following the schema in `demo.json`. Good scenarios have:

- A compelling strategic question with no clear "right answer"
- 4-7 stakeholders with genuinely conflicting interests
- Realistic hard constraints and BATNAs
- Diverse cognitive biases and communication styles

### Features & Bug Fixes

- Check [GitHub Issues](https://github.com/ArtemisAI/A2A-WarGames/issues) for open tasks
- For large features, open an issue first to discuss the approach
- Keep PRs focused — one logical change per PR

### Documentation

- Improve the README, API docs, or deployment guides
- Add inline comments where logic is non-obvious
- Translate i18n strings (currently EN/FR/ES — more languages welcome)

## Submitting a Pull Request

1. Ensure all tests pass (`pytest backend/tests/ -v` and `npx vitest run`)
2. Write a clear PR description explaining _what_ changed and _why_
3. Reference any related issues
4. Keep the diff focused — avoid unrelated formatting changes

## Environment Variables

Never commit `.env` files or API keys. Use `.env.example` as the template.

## Questions?

- Open a [GitHub Discussion](https://github.com/ArtemisAI/A2A-WarGames/discussions) or issue
- Visit [artemis-ai.ca](https://artemis-ai.ca) for commercial inquiries

---

Thank you for helping make A2A War Games better!
