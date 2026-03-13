import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings as app_settings
from .database import init_db
from .routers import settings, projects, sessions, compact, assistant, audio as audio_router, providers
from .a2a.llm_client import close_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle.

    DEPLOYMENT NOTE — Single-Worker Requirement:
    The running-engine registry (_running_engines in routers/sessions.py) is an
    in-process dict. All stream/stop/pause/inject/resume requests for a session
    MUST land on the same worker process that started the session. Deploy with:
      uvicorn backend.main:app --workers 1
    or use a load balancer with session-affinity (sticky sessions) if you need
    multiple workers. Multi-worker without sticky sessions will cause 404 errors
    on /stream, /stop, /pause, /resume, and /inject endpoints.
    """
    init_db()
    # #193: reset any sessions stuck in "warming" from a previous server run.
    # asyncio tasks from the old loop are gone; reset so the next /run re-warms.
    _reset_stuck_warming_sessions()
    # CR-019: seed model registry from JSON on first startup
    _seed_model_registry()
    logging.info("OpenClaw backend started — database initialized")
    yield
    await close_client()
    logging.info("OpenClaw backend shutdown — LLM client closed")


def _reset_stuck_warming_sessions() -> None:
    """Reset pre_warm_status='warming' sessions to null on startup (#193).

    Sessions stuck in 'warming' from a previous server run (e.g., hot reload or
    crash) will never complete — their asyncio tasks were lost with the old loop.
    Reset to None so the engine triggers a fresh pre-warm on the next /run.
    """
    try:
        from .database import SessionLocal
        from .models import Session
        db = SessionLocal()
        try:
            count = (
                db.query(Session)
                .filter(Session.pre_warm_status == "warming")
                .update({"pre_warm_status": None}, synchronize_session=False)
            )
            if count:
                db.commit()
                logging.info(
                    "Startup: reset %d session(s) stuck in pre_warm_status='warming'", count
                )
        finally:
            db.close()
    except Exception as exc:
        logging.warning("Could not reset stuck warming sessions at startup: %s", exc)


def _seed_model_registry() -> None:
    """Seed model_registry from JSON if the table is empty (CR-019).

    Only runs on first startup — if rows already exist, this is a no-op.
    """
    import json
    import pathlib
    try:
        from .database import SessionLocal
        from .models import ModelRegistryEntry
        db = SessionLocal()
        try:
            count = db.query(ModelRegistryEntry).count()
            if count > 0:
                return  # already seeded

            seed_path = pathlib.Path(__file__).parent / "model_registry_seed.json"
            if not seed_path.exists():
                logging.warning("model_registry_seed.json not found — skipping seed")
                return

            with open(seed_path, "r", encoding="utf-8") as f:
                seed_data = json.load(f)

            total = 0
            for provider_id, models in seed_data.items():
                for m in models:
                    entry = ModelRegistryEntry(
                        provider_id=provider_id,
                        model_id=m["model_id"],
                        display_name=m["display_name"],
                        tier=m.get("tier", "balanced"),
                        context_window=m.get("context_window"),
                        supports_vision=m.get("supports_vision", False),
                        supports_thinking=m.get("supports_thinking", False),
                        supports_streaming=m.get("supports_streaming", True),
                        supports_json_mode=m.get("supports_json_mode", True),
                        is_deprecated=False,
                    )
                    db.add(entry)
                    total += 1
            db.commit()
            logging.info("Startup: seeded model_registry with %d models from JSON", total)
        finally:
            db.close()
    except Exception as exc:
        logging.warning("Could not seed model registry at startup: %s", exc)


app = FastAPI(
    title="A2A War Games — Stakeholder Wargame Simulation",
    description="Multi-agent stakeholder simulation platform",
    version="0.6.0",
    lifespan=lifespan,
)

_origins = (
    [o.strip() for o in app_settings.allowed_origins.split(",")]
    if app_settings.allowed_origins != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router)
app.include_router(providers.router)
app.include_router(projects.router)
app.include_router(sessions.router)
app.include_router(compact.router)
app.include_router(assistant.router)
app.include_router(audio_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "a2a-wargames", "version": "0.6.0"}
