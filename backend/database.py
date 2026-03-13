from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings
import json
import logging

logger = logging.getLogger(__name__)

# Conditional connect_args: check_same_thread is SQLite-only
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    **({"pool_size": 10, "max_overflow": 20, "pool_recycle": 1800}
       if not settings.database_url.startswith("sqlite") else {}),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_fresh_db():
    """Get a fresh DB session for one-shot writes. Closes immediately after use.

    Use this instead of get_db() when the session is needed for a single
    write operation after a long-running async task (e.g., after an LLM call).
    """
    return SessionLocal()


def get_db_session_with_user(user_id: str = None):
    """Create a standalone DB session with RLS context.

    Used by _persist_message / _finalize_session which run outside
    the FastAPI request lifecycle.
    """
    db = SessionLocal()
    if user_id and not settings.database_url.startswith("sqlite"):
        db.execute(text("SET LOCAL app.user_id = :uid"), {"uid": user_id})
    return db


def init_db():
    from . import models  # noqa: F401 — registers all models
    # Enable pgvector extension before create_all so the VECTOR type is available
    if not settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception as e:
                logger.warning("pgvector extension creation skipped: %s", e)
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _ensure_seed_data()


def _ensure_columns():
    """Add columns that may be missing from existing tables (lightweight migration).

    ``create_all()`` only creates *new* tables — it will not add columns to
    tables that already exist.  This helper inspects the live schema and issues
    ``ALTER TABLE`` statements for any columns that were added after the initial
    deployment.
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.exc import NoSuchTableError

    inspector = sa_inspect(engine)

    # --- llm_settings --------------------------------------------------
    try:
        llm_cols = [c["name"] for c in inspector.get_columns("llm_settings")]
    except NoSuchTableError:
        llm_cols = []  # table doesn't exist yet; create_all will handle it

    with engine.begin() as conn:
        if llm_cols and "feature_flags" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN feature_flags TEXT DEFAULT '{}'"))
        if llm_cols and "max_tokens_per_turn" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN max_tokens_per_turn INTEGER DEFAULT 4096"))
        # Voice columns (CR-008)
        if llm_cols and "tts_enabled" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_enabled BOOLEAN DEFAULT FALSE"))
        if llm_cols and "tts_model" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_model VARCHAR(100) DEFAULT 'tts-1'"))
        if llm_cols and "tts_voice" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_voice VARCHAR(100) DEFAULT 'alloy'"))
        if llm_cols and "tts_speed" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_speed FLOAT DEFAULT 1.0"))
        if llm_cols and "tts_auto_play" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_auto_play BOOLEAN DEFAULT FALSE"))
        if llm_cols and "tts_language" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN tts_language VARCHAR(10) DEFAULT 'auto'"))
        if llm_cols and "stt_enabled" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN stt_enabled BOOLEAN DEFAULT FALSE"))
        if llm_cols and "stt_model" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN stt_model VARCHAR(100) DEFAULT 'whisper-1'"))
        if llm_cols and "stt_language" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN stt_language VARCHAR(10) DEFAULT 'auto'"))
        if llm_cols and "stt_auto_send" not in llm_cols:
            conn.execute(text("ALTER TABLE llm_settings ADD COLUMN stt_auto_send BOOLEAN DEFAULT FALSE"))

    # --- projects -----------------------------------------------------
    try:
        proj_cols = [c["name"] for c in inspector.get_columns("projects")]
    except NoSuchTableError:
        proj_cols = []

    with engine.begin() as conn:
        if proj_cols and "is_demo" not in proj_cols:
            conn.execute(text("ALTER TABLE projects ADD COLUMN is_demo BOOLEAN DEFAULT FALSE"))

    # --- sessions ------------------------------------------------------
    try:
        sess_cols = [c["name"] for c in inspector.get_columns("sessions")]
    except NoSuchTableError:
        sess_cols = []

    # --- stakeholders (CR-008) -----------------------------------------
    try:
        stk_cols = [c["name"] for c in inspector.get_columns("stakeholders")]
    except NoSuchTableError:
        stk_cols = []

    with engine.begin() as conn:
        if stk_cols and "tts_voice" not in stk_cols:
            conn.execute(text("ALTER TABLE stakeholders ADD COLUMN tts_voice VARCHAR(100)"))
        # CR-019: per-agent provider override
        if stk_cols and "llm_provider" not in stk_cols:
            conn.execute(text("ALTER TABLE stakeholders ADD COLUMN llm_provider VARCHAR(50)"))
        if stk_cols and "llm_model" not in stk_cols:
            conn.execute(text("ALTER TABLE stakeholders ADD COLUMN llm_model VARCHAR(200)"))
        if stk_cols and "llm_model_display" not in stk_cols:
            conn.execute(text("ALTER TABLE stakeholders ADD COLUMN llm_model_display VARCHAR(200)"))

    with engine.begin() as conn:
        # Pause/resume checkpoint column
        if sess_cols and "checkpoint" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN checkpoint TEXT"))
        if sess_cols and "moderator_name" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN moderator_name VARCHAR(100) DEFAULT 'Moderator'"))
        if sess_cols and "moderator_title" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN moderator_title VARCHAR(200) DEFAULT ''"))
        if sess_cols and "moderator_mandate" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN moderator_mandate TEXT DEFAULT ''"))
        if sess_cols and "moderator_persona_prompt" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN moderator_persona_prompt TEXT DEFAULT ''"))
        # Pre-warm columns
        if sess_cols and "pre_warm_status" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN pre_warm_status VARCHAR(20)"))
        if sess_cols and "pre_warm_data" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN pre_warm_data TEXT"))
        if sess_cols and "config_changed_at" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN config_changed_at TIMESTAMP"))
        if sess_cols and "compact_summary" not in sess_cols:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN compact_summary TEXT"))

    # --- session_config (CR-011) -------------------------------------------
    try:
        sc_cols = [c["name"] for c in inspector.get_columns("session_config")]
    except NoSuchTableError:
        sc_cols = []

    with engine.begin() as conn:
        if sc_cols and "private_thread_limit" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN private_thread_limit INTEGER DEFAULT 3"))
        if sc_cols and "private_thread_depth" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN private_thread_depth INTEGER DEFAULT 2"))
        if sc_cols and "private_thread_quota_mode" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN private_thread_quota_mode VARCHAR(20) DEFAULT 'fixed'"))
        # #201: missing columns for anti_groupthink, devil_advocate_round, temperature_override
        if sc_cols and "anti_groupthink" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN anti_groupthink BOOLEAN DEFAULT TRUE"))
        if sc_cols and "devil_advocate_round" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN devil_advocate_round INTEGER DEFAULT 0"))
        if sc_cols and "temperature_override" not in sc_cols:
            conn.execute(text("ALTER TABLE session_config ADD COLUMN temperature_override FLOAT"))

    # --- messages ---------------------------------------------------------
    try:
        msg_cols = [c["name"] for c in inspector.get_columns("messages")]
    except NoSuchTableError:
        msg_cols = []

    with engine.begin() as conn:
        if msg_cols and "round_num" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN round_num INTEGER DEFAULT 0"))
        if msg_cols and "compacted" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN compacted BOOLEAN DEFAULT FALSE"))
        if msg_cols and "finish_reason" not in msg_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN finish_reason VARCHAR(20)"))

    # --- session_agenda + agenda_votes (CR-006) ----------------------------
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS session_agenda (
                id          SERIAL PRIMARY KEY,
                session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                item_key    VARCHAR(50) NOT NULL,
                label       TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agenda_votes (
                id           SERIAL PRIMARY KEY,
                session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                item_key     VARCHAR(50) NOT NULL,
                speaker_slug VARCHAR(100) NOT NULL,
                turn         INTEGER NOT NULL,
                round        INTEGER NOT NULL,
                stance       VARCHAR(20) NOT NULL,
                confidence   FLOAT DEFAULT 0.5,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # #169: composite indexes for fast per-session agenda/vote lookups
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_session_agenda_session ON session_agenda (session_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_session_agenda_session_key ON session_agenda (session_id, item_key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agenda_votes_session ON agenda_votes (session_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agenda_votes_session_key ON agenda_votes (session_id, item_key)"))

    # --- agent_memories (CR-010) -------------------------------------------
    is_pg = not settings.database_url.startswith("sqlite")
    with engine.begin() as conn:
        if is_pg:
            # Enable pgvector extension (idempotent)
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception as e:
                logger.warning("Could not create pgvector extension (may already exist): %s", e)

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id          SERIAL PRIMARY KEY,
                    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    session_id  INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                    speaker_slug VARCHAR(100) NOT NULL,
                    memory_type VARCHAR(30) NOT NULL,
                    content     TEXT NOT NULL,
                    structured_data TEXT,
                    embedding   vector(384),
                    salience    FLOAT DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    decay_factor FLOAT DEFAULT 1.0,
                    round_num   INTEGER,
                    turn        INTEGER,
                    scope       VARCHAR(20) DEFAULT 'session',
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            # Index for vector similarity search
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_agent_memories_embedding
                    ON agent_memories USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 50)
                """))
            except Exception:
                logger.info("ivfflat index creation skipped (requires sufficient rows)")
            # Index for scoped queries
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_memories_scope
                ON agent_memories (speaker_slug, project_id, scope)
            """))
        else:
            # SQLite fallback — no vector column, store embedding as TEXT
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    session_id  INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                    speaker_slug VARCHAR(100) NOT NULL,
                    memory_type VARCHAR(30) NOT NULL,
                    content     TEXT NOT NULL,
                    structured_data TEXT,
                    embedding   TEXT,
                    salience    FLOAT DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    decay_factor FLOAT DEFAULT 1.0,
                    round_num   INTEGER,
                    turn        INTEGER,
                    scope       VARCHAR(20) DEFAULT 'session',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))


def _ensure_seed_data():
    """Backfill success_criteria for stakeholders seeded before the field was added."""
    from .models import Stakeholder

    CRITERIA_BY_SLUG = {
        "julien": [
            "Client chatbot live within 6 months",
            "CRM exploitation above 50% in 12 months",
            "Measurable revenue impact within 12 months",
        ],
        "amelie": [
            "Data quality baseline before AI goes live",
            "Production team leads accept the tool",
            "Decision support, not autopilot",
        ],
        "sarah": [
            "Zero legal exposure — ESA Ontario 2025 compliant",
            "Bias audit completed before any hiring-adjacent AI",
            "Admin workload reduced without automating hiring decisions",
        ],
        "marc": [
            "ROI demonstrated case-by-case before expansion",
            "Full reversibility clause in all AI contracts",
            "No cosmetic spend — every dollar tied to measurable outcome",
        ],
        "karim": [
            "All 3 infrastructure preconditions met before AI touches production",
            "Tech debt cleanup funded as part of AI budget",
            "No new software layer without readiness assessment",
        ],
        "simon": [
            "Floor workers consulted BEFORE any tool is chosen",
            "Zero increase in data entry burden for production staff",
            "Tacit knowledge integrated, not replaced",
        ],
        "michel": [
            "AI initiative delivers measurable ROI within 12 months",
            "No disruption to current year revenue or client commitments",
            "Board-level alignment before any commitment > $50K",
        ],
    }

    db = SessionLocal()
    try:
        for slug, criteria in CRITERIA_BY_SLUG.items():
            stk = db.query(Stakeholder).filter_by(slug=slug).first()
            if stk:
                existing = stk.success_criteria
                if isinstance(existing, str):
                    try:
                        existing = json.loads(existing)
                    except (ValueError, TypeError):
                        existing = []
                if not existing:
                    stk.success_criteria = json.dumps(criteria)
        db.commit()
    except Exception as e:
        logger.error("Failed to backfill success_criteria: %s", e)
    finally:
        db.close()
