# Changelog

All notable changes to A2A War Games are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

## [0.14.0] — 2026-03-10

### Added
- Google OAuth sign-in: Google Cloud project + Web client configured, Supabase provider enabled
- GitHub OAuth sign-in: GitHub OAuth App created, Supabase provider enabled
- Google "G" (4-color) and GitHub mark SVG logos on OAuth buttons in login modal
- Sign-up flow: confirm-password field, post-signup email verification screen, "Back to sign in" link
- `docs/oauth-setup.md`: end-to-end OAuth setup guide for Google and GitHub
- Issues logged: #223 (i18n locale at runtime), #224 (empty agent responses), #225 (resume auth error)

### Fixed
- Issue #226: Google OAuth "unsupported provider" error — root cause was Supabase provider not enabled (now resolved)

---

## [0.13.0] — 2026-03-09

### Added
- CR-012/CR-013 hardening: security audit, auth on all mutating endpoints, SSRF protection, stream-ticket auth
- Code splitting (Vite `manualChunks`), full accessibility (ARIA, keyboard nav, focus traps)
- i18n completeness: EN/FR/ES for all UI strings
- Design token system: `--space-1` to `--space-12`, `--danger`, `--accent`, CSS vars throughout
- `CollapseTransition`, `FadeTransition`, `SlideTransition`, `ScaleTransition` components
- Context usage meter (`GET /api/sessions/{id}/context-usage`)
- Pause/resume/recover session endpoints (`POST /api/sessions/{id}/pause|resume|recover`)
- Compact session endpoint + `compact_session()` logic

### Fixed
- 81+ UI bugs across TurnCard, SessionLiveView, SettingsPage, analytics, modals
- Streaming pipeline: 4 bugs — split data stores, token routing, cleanup, duplicate listeners
- SSE keepalive: `asyncio.wait_for` → `asyncio.wait` to fix cancellation bug

---

## [0.12.0] — 2026-03-05

### Added
- CLI runner: `python -m backend.cli <config_file>` for headless debate execution
- JWT stream-ticket auth for SSE connections (issue #130)
- Security hardening: RLS on all mutating routes, input validation, SSRF guard

---

## [0.11.0] — 2026-03-01

### Added
- CR-011 private threads (whisper): bilateral exchange loop, private context injection
- Observer extraction of private thread insights
- Voting matrix panel + `GET /api/sessions/{id}/voting-summary`
- `whisper_thread_open/close`, `whisper_turn_end`, `whisper_opportunity_end` SSE events

---

## [0.10.0] — 2026-02-20

### Added
- CR-010 agent memory: pgvector extension, S-BERT embeddings, semantic retrieval
- `agent_memories` DB table, `MemoryService`, `retrieve_memories` endpoint
- AI Assistant sidebar: Enhance proposal + Extract stakeholder profile actions
- TTS audio playback (`POST /api/audio/speech`) and STT microphone input (`POST /api/audio/transcriptions`)
- Voice settings per agent profile (nova voice persists across reloads)

---

## [0.7.0] — 2026-02-10

### Added
- `private_threads` + `private_messages` DB tables
- Voting/consensus tracking: `SessionTracker`, observer analytics, position matrix
- Agent memory scaffold: pgvector, S-BERT, semantic search (integrated in v0.10)
- i18n framework: vue-i18n 11.3.0, EN/FR/ES locale files

---

## [0.6.0] — 2026-02-01

### Added
- Auth: Supabase JWT validation (`backend/auth.py`), `get_db_with_rls` RLS context
- Pre-warm: background agenda + moderator opening on session creation
- Model list endpoint: `GET /api/settings/models`
- Feature flags: all gates wired (`feature_flags` table)

### Fixed
- Multiple N+1 queries in `list_sessions`, `_build_prior_session_context`
- Observer sentiment JSON parse failures (markdown fence stripping)
- `round_num in dir()` → `locals()` guard
- `inject_message` hardcoded `round=0` → `self.current_round`

---

## [0.5.0] — 2026-01-20

### Added
- CR-006/CR-007: simulation quality improvements, moderator styles
- Frontend: design system foundation, TurnCard Slack-style bubbles, thinking indicator
- Backend: model fallback (tries other council_models when primary fails)
- Health check: `POST /api/settings/test-connection` bottom-up diagnostic

---

## [0.4.0] — 2026-01-10

### Added
- CR-003/CR-004: initial backend + frontend Copilot SWE delivery
- SSE streaming: `turn_start`, `content_token`, `thinking_token`, `turn_end`, `observer`, `synthesis`, `analytics`, `agenda_init`, `complete`, `error`, `ping`
- Vue 3 + Pinia + Vite frontend scaffold
- FastAPI + SQLAlchemy backend scaffold

---

## [0.3.0] — 2026-01-01

### Added
- Initial repo scaffolding: FastAPI backend, Vue 3 frontend, PostgreSQL/Supabase schema
- A2A debate engine: `engine.py`, `speaker_selection.py`, `moderator.py`
- Basic session CRUD and SSE event loop
