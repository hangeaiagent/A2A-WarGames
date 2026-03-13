"""
SQLAlchemy models for the OpenClaw wargame platform.

Tables:
  projects              — a stakeholder analysis context (org + topic)
  stakeholders          — personas attached to a project
  sessions              — a wargame run (question posed to the council)
  messages              — individual agent turns within a session
  llm_settings          — persistent LLM configuration (one active row)
  private_threads       — CR-011: bilateral private agent-to-agent threads
  private_messages      — CR-011: individual turns within a private thread
  provider_keys         — CR-019: per-user encrypted API keys per provider
  model_registry        — CR-019: static + dynamic model catalog
  user_model_preferences — CR-019: per-user model activation & defaults
"""

import datetime
import json
from datetime import timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, LargeBinary, Uuid, func,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base

# pgvector — optional (only available when using PostgreSQL with pgvector extension)
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


def _now():
    return datetime.datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# LLM Settings (singleton-ish — one row per named profile)
# ---------------------------------------------------------------------------
class LLMSettings(Base):
    __tablename__ = "llm_settings"

    id            = Column(Integer, primary_key=True, index=True)
    profile_name  = Column(String(120), unique=True, default="default")
    is_active     = Column(Boolean, default=True)

    base_url      = Column(String(500), nullable=False)
    api_key       = Column(String(500), nullable=False)
    default_model = Column(String(200), nullable=False)
    chairman_model = Column(String(200), nullable=False)
    # JSON list of model names used for council agents
    council_models = Column(Text, default='["gpt-4o"]')

    user_id       = Column(Uuid, nullable=True)  # multi-tenancy: owner

    temperature   = Column(Float, default=0.8)
    max_tokens    = Column(Integer, default=1024)
    max_tokens_per_turn = Column(Integer, default=4096, nullable=True)
    feature_flags = Column(Text, nullable=False, default="{}")

    # TTS settings
    tts_enabled   = Column(Boolean, default=False)
    tts_model     = Column(String(100), default="tts-1")
    tts_voice     = Column(String(100), default="alloy")
    tts_speed     = Column(Float, default=1.0)
    tts_auto_play = Column(Boolean, default=False)
    tts_language  = Column(String(10), default="auto")

    # STT settings
    stt_enabled   = Column(Boolean, default=False)
    stt_model     = Column(String(100), default="whisper-1")
    stt_language  = Column(String(10), default="auto")
    stt_auto_send = Column(Boolean, default=False)

    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)

    @property
    def council_models_list(self):
        return json.loads(self.council_models or "[]")

    @council_models_list.setter
    def council_models_list(self, value):
        self.council_models = json.dumps(value)

    @property
    def feature_flags_dict(self) -> dict:
        try:
            return json.loads(self.feature_flags or "{}")
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(200), nullable=False)
    description   = Column(Text, default="")
    organization  = Column(String(200), default="")
    context       = Column(Text, default="")   # free-text org context for agents
    user_id       = Column(Uuid, nullable=True)  # multi-tenancy: owner
    is_public     = Column(Boolean, default=False)  # visible to all users
    is_demo       = Column(Boolean, default=False)  # seeded demo project (read-only)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)

    stakeholders  = relationship("Stakeholder", back_populates="project", cascade="all, delete-orphan")
    sessions      = relationship("Session", back_populates="project", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Stakeholders
# ---------------------------------------------------------------------------
class Stakeholder(Base):
    __tablename__ = "stakeholders"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, ForeignKey("projects.id"), nullable=False)

    slug          = Column(String(80), nullable=False)   # e.g. 'michel'
    name          = Column(String(200), nullable=False)
    role          = Column(String(200), default="")
    department    = Column(String(200), default="")

    # Attitude: enthusiast | conditional | critical | strategic | founder | neutral
    attitude      = Column(String(80), default="neutral")
    attitude_label = Column(String(200), default="")

    # Power/interest 0-1
    influence     = Column(Float, default=0.5)
    interest      = Column(Float, default=0.5)

    # Persona rich fields (stored as JSON text)
    needs         = Column(Text, default="[]")    # list of strings
    fears         = Column(Text, default="[]")
    preconditions = Column(Text, default="[]")    # list of {title, description}
    quote         = Column(Text, default="")
    signal_cle    = Column(Text, default="")      # key signal / summary

    # ADKAR scores (JSON: {awareness, desire, knowledge, ability, reinforcement})
    adkar         = Column(Text, default="{}")

    # Relationships to other stakeholders (JSON list of edge objects)
    # Stored at project level too — see StakeholderEdge
    color         = Column(String(20), default="#888888")

    # Avatar image URL (relative path like /avatars/01_michel_tremblay.png or external URL)
    avatar_url    = Column(String(500), nullable=True)

    # Per-stakeholder TTS voice override (null = use global TTS voice)
    tts_voice     = Column(String(100), nullable=True)

    # CR-019: per-stakeholder LLM override (null = use project default)
    llm_provider      = Column(String(50), nullable=True)    # provider preset id (e.g. "openai", "anthropic")
    llm_model         = Column(String(200), nullable=True)   # model id (e.g. "gpt-4o")
    llm_model_display = Column(String(200), nullable=True)   # cached display name for UI badges

    # Full system prompt override (null = auto-generated from persona)
    system_prompt = Column(Text, nullable=True)

    # --- Rich profile fields (from PRD §4.2) ---
    # Salience model (Mitchell, Agle & Wood)
    salience_power      = Column(Integer, default=5)        # 1-10
    salience_legitimacy = Column(Integer, default=5)        # 1-10
    salience_urgency    = Column(Integer, default=5)        # 1-10
    salience_type       = Column(String(40), default="")    # definitive, dependent, dormant, etc.
    mendelow_quadrant   = Column(String(40), default="")    # manage_closely, keep_satisfied, keep_informed, monitor

    # Behavioral profile
    communication_style = Column(String(200), default="")   # e.g. "direct_paternal_pragmatic"
    attitude_baseline   = Column(String(200), default="")   # e.g. "pragmatic_cautious"
    interest_alignment  = Column(Integer, default=0)        # -5 to +5 (toward the AI adoption proposal)
    cognitive_biases    = Column(Text, default="[]")        # JSON list of strings

    # Strategic profile
    batna               = Column(Text, default="")          # Best Alternative to Negotiated Agreement
    hard_constraints    = Column(Text, default="[]")        # JSON list of strings — absolute non-negotiables
    success_criteria    = Column(Text, default="[]")        # JSON list of strings — what "win" looks like
    key_concerns        = Column(Text, default="[]")        # JSON list of strings — detailed worries

    # Grounding
    grounding_quotes    = Column(Text, default="[]")        # JSON list of full interview quotes
    anti_sycophancy     = Column(Text, default="")          # Per-agent anti-sycophancy prompt instructions

    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)

    project       = relationship("Project", back_populates="stakeholders")

    @property
    def needs_list(self):
        return json.loads(self.needs or "[]")

    @property
    def fears_list(self):
        return json.loads(self.fears or "[]")

    @property
    def adkar_dict(self):
        return json.loads(self.adkar or "{}")

    @property
    def cognitive_biases_list(self):
        return json.loads(self.cognitive_biases or "[]")

    @property
    def hard_constraints_list(self):
        return json.loads(self.hard_constraints or "[]")

    @property
    def success_criteria_list(self):
        return json.loads(self.success_criteria or "[]")

    @property
    def key_concerns_list(self):
        return json.loads(self.key_concerns or "[]")

    @property
    def grounding_quotes_list(self):
        return json.loads(self.grounding_quotes or "[]")


# ---------------------------------------------------------------------------
# Stakeholder Edges (relationships / tensions)
# ---------------------------------------------------------------------------
class StakeholderEdge(Base):
    __tablename__ = "stakeholder_edges"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_slug     = Column(String(80), nullable=False)
    target_slug     = Column(String(80), nullable=False)
    # 'tension' or 'alignment'
    edge_type       = Column(String(40), default="tension")
    label           = Column(String(200), default="")
    strength        = Column(Float, default=0.5)


# ---------------------------------------------------------------------------
# Sessions (a wargame run)
# ---------------------------------------------------------------------------
class Session(Base):
    __tablename__ = "sessions"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, ForeignKey("projects.id"), nullable=False)

    title         = Column(String(300), default="")
    question      = Column(Text, nullable=False)   # the strategic proposal posed

    # Status: pending | running | complete | error
    status        = Column(String(40), default="pending")

    # Which stakeholders participated (JSON list of slugs)
    participants  = Column(Text, default="[]")

    # Final chairman synthesis
    synthesis     = Column(Text, default="")

    # Aggregate consensus score (0-1, computed after session)
    consensus_score = Column(Float, nullable=True)

    # Moderator persona (per-session customization)
    moderator_name           = Column(String(100), default="Moderator", nullable=True)
    moderator_title          = Column(String(200), default="", nullable=True)
    moderator_mandate        = Column(Text, default="", nullable=True)
    moderator_persona_prompt = Column(Text, default="", nullable=True)

    # Pause/crash recovery checkpoint (JSON blob)
    # Schema: {"round": int, "turn": int, "phase": str, "speakers_completed": [...]}
    checkpoint    = Column(Text, nullable=True)

    # Pre-warm status: null | "warming" | "ready" | "invalidated"
    pre_warm_status = Column(String(20), nullable=True)

    # Pre-warm cached data (JSON blob)
    # Schema: {"agenda": [...], "moderator_opening": "...", "warmed_at": "ISO8601"}
    pre_warm_data   = Column(Text, nullable=True)

    # Timestamp of last config change (used to detect invalidation)
    config_changed_at = Column(DateTime, nullable=True)

    # Compact summary — LLM-generated summary of compacted rounds (#118)
    # Injected as prior_session_context by resume_from_db when present
    compact_summary = Column(Text, nullable=True)

    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)

    project       = relationship("Project", back_populates="sessions")
    messages      = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.turn")


# ---------------------------------------------------------------------------
# Messages (individual agent turns)
# ---------------------------------------------------------------------------
class Message(Base):
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    session_id      = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)  # #88

    turn            = Column(Integer, default=0)
    round_num       = Column(Integer, default=0, nullable=True)  # CR-004: round attribution for resume
    # stage: 0=intro, 1=initial_response, 2=challenge, 3=synthesis, 4=inject
    stage           = Column(Integer, default=1)

    # 'stakeholder' slug or 'chairman' or 'moderator'
    speaker         = Column(String(80), nullable=False)
    speaker_name    = Column(String(200), default="")

    content         = Column(Text, nullable=False)

    # Sentiment snapshot at this turn (JSON: {anxiety, trust, aggression, compliance})
    sentiment       = Column(Text, nullable=True)

    # Cosine similarity vs previous turn (null for first turn)
    cosine_similarity = Column(Float, nullable=True)

    # Whether this message has been summarized by the /compact endpoint
    # Manual Supabase SQL: ALTER TABLE messages ADD COLUMN IF NOT EXISTS compacted BOOLEAN DEFAULT FALSE;
    compacted       = Column(Boolean, default=False, nullable=True)

    # Finish reason from LLM: 'stop' | 'error' | 'length' | None
    finish_reason   = Column(String(20), nullable=True)

    created_at      = Column(DateTime, default=_now)

    session         = relationship("Session", back_populates="messages")


# ---------------------------------------------------------------------------
# Analytics Snapshots (per-round metrics)
# ---------------------------------------------------------------------------
class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id                  = Column(Integer, primary_key=True, index=True)
    session_id          = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)  # #88
    round               = Column(Integer, nullable=False)

    consensus_score     = Column(Float, nullable=True)
    consensus_velocity  = Column(Float, nullable=True)   # delta from prior round
    polarization_index  = Column(Float, nullable=True)   # 1 - inter-cluster sim

    coalition_data      = Column(Text, nullable=True)     # JSON: {clusters: [{members, similarity, stability}]}
    influence_data      = Column(Text, nullable=True)     # JSON: [{agent, eigenvector, betweenness, turns}]
    risk_scores         = Column(Text, nullable=True)     # JSON: [{agent, score, level, drivers}]
    position_embeddings = Column(Text, nullable=True)     # JSON: {slug: [384 floats]}

    created_at          = Column(DateTime, default=_now)

    session             = relationship("Session", backref="analytics_snapshots")


# ---------------------------------------------------------------------------
# Session Config (per-session overrides)
# ---------------------------------------------------------------------------
class SessionConfig(Base):
    __tablename__ = "session_config"

    id                    = Column(Integer, primary_key=True, index=True)
    session_id            = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)  # #88

    num_rounds            = Column(Integer, default=5)
    agents_per_turn       = Column(Integer, default=3)
    anti_groupthink       = Column(Boolean, default=True)
    devil_advocate_round  = Column(Integer, default=0)    # 0 = disabled
    moderator_style       = Column(String(40), default="neutral")  # neutral | challenging | facilitative
    temperature_override  = Column(Float, nullable=True)  # null = use settings default

    # CR-011: private thread configuration
    private_thread_limit      = Column(Integer, default=3)     # base quota per agent
    private_thread_depth      = Column(Integer, default=2)     # max exchanges per thread
    private_thread_quota_mode = Column(String(20), default="fixed")  # "fixed" | "power_proportional"

    session               = relationship("Session", backref="config")


# ---------------------------------------------------------------------------
# Turn Analytics (fine-grained per-turn observer data)
# ---------------------------------------------------------------------------
class TurnAnalytics(Base):
    __tablename__ = "turn_analytics"

    id                = Column(Integer, primary_key=True, index=True)
    session_id        = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)  # #88
    message_id        = Column(Integer, ForeignKey("messages.id"), nullable=True)

    turn              = Column(Integer, nullable=False)
    round             = Column(Integer, nullable=False)
    speaker           = Column(String(80), nullable=False)

    position_summary  = Column(Text, nullable=True)
    sentiment_data    = Column(Text, nullable=True)   # JSON: {overall, anxiety, trust, aggression, compliance}
    behavioral_signals = Column(Text, nullable=True)  # JSON: {concession, agreements, disagreements, ...}
    claims            = Column(Text, nullable=True)   # JSON: list of strings
    fears_triggered   = Column(Text, nullable=True)   # JSON: list of strings
    needs_referenced  = Column(Text, nullable=True)   # JSON: list of strings

    created_at        = Column(DateTime, default=_now)

    session           = relationship("Session", backref="turn_analytics")


# ---------------------------------------------------------------------------
# Session Agenda (per-session debate sub-questions)
# ---------------------------------------------------------------------------
class SessionAgenda(Base):
    __tablename__ = "session_agenda"

    id          = Column(Integer, primary_key=True, index=True)
    session_id  = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_key    = Column(String(50), nullable=False)   # "item_1", "item_2", ...
    label       = Column(Text, nullable=False)         # "Should AI be integrated within 6 months?"
    description = Column(Text, default="")
    created_at  = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))

    session     = relationship("Session", backref="agenda_items")


# ---------------------------------------------------------------------------
# Agenda Votes (per-turn stance per speaker per agenda item)
# ---------------------------------------------------------------------------
class AgendaVote(Base):
    __tablename__ = "agenda_votes"

    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_key     = Column(String(50), nullable=False)
    speaker_slug = Column(String(100), nullable=False)
    turn         = Column(Integer, nullable=False)
    round        = Column(Integer, nullable=False)
    stance       = Column(String(20), nullable=False)  # "agree" | "oppose" | "neutral" | "abstain"
    confidence   = Column(Float, default=0.5)
    created_at   = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))

    session      = relationship("Session", backref="agenda_votes")


# ---------------------------------------------------------------------------
# Agent Memories (CR-010 — semantic retrieval + observer feedback)
# ---------------------------------------------------------------------------
class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True)
    speaker_slug = Column(String(100), nullable=False, index=True)

    # Memory content
    memory_type = Column(String(30), nullable=False)
    # Types: "concession", "alliance", "escalation", "proposal",
    #        "agreement", "disagreement", "fear_triggered", "belief_update"
    content = Column(Text, nullable=False)
    structured_data = Column(Text, nullable=True)  # JSON: entities, related_agents, topic

    # Vector retrieval (384-dim = all-MiniLM-L6-v2 output)
    embedding = Column(Vector(384), nullable=True) if Vector is not None else Column(Text, nullable=True)

    # Salience scoring
    salience = Column(Float, default=0.5)       # importance 0-1 (set by Observer)
    access_count = Column(Integer, default=0)    # how often retrieved (for LRU)
    decay_factor = Column(Float, default=1.0)    # recency decay, decremented over rounds

    # Scoping
    round_num = Column(Integer, nullable=True)
    turn = Column(Integer, nullable=True)
    scope = Column(String(20), default="session")  # "session" or "project" (cross-session)

    created_at = Column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# CR-011 — Private Agent-to-Agent Threads (Whisper Channels)
# ---------------------------------------------------------------------------

class PrivateThread(Base):
    """One bilateral private thread per agent-pair per session."""
    __tablename__ = "private_threads"

    id              = Column(Integer, primary_key=True, index=True)
    session_id      = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    initiator_slug  = Column(String(100), nullable=False)
    target_slug     = Column(String(100), nullable=False)
    round_opened    = Column(Integer, nullable=False)
    status          = Column(String(20), default="open")  # "open" | "closed" | "declined"
    created_at      = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))

    messages        = relationship("PrivateMessage", backref="thread", cascade="all, delete-orphan")
    session         = relationship("Session", backref="private_threads")


class PrivateMessage(Base):
    """Individual turns within a private bilateral thread."""
    __tablename__ = "private_messages"

    id              = Column(Integer, primary_key=True, index=True)
    thread_id       = Column(Integer, ForeignKey("private_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id      = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker_slug    = Column(String(100), nullable=False)
    content         = Column(Text, nullable=False)
    internal_reason = Column(Text, nullable=True)   # agent's private reasoning (never sent over SSE)
    round_num       = Column(Integer, nullable=True)
    turn            = Column(Integer, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# CR-019 — Provider Keys (per-user encrypted API keys)
# ---------------------------------------------------------------------------
class ProviderKey(Base):
    """One API key per provider per user, encrypted at rest via Fernet."""
    __tablename__ = "provider_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", name="uq_provider_keys_user_provider"),
    )

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Uuid, nullable=False, index=True)
    provider_id   = Column(String(50), nullable=False)    # 'openai', 'anthropic', 'groq', etc.
    api_key_enc   = Column(LargeBinary, nullable=False)   # Fernet-encrypted API key
    base_url      = Column(String(500), nullable=True)    # custom override, null = use preset default
    is_enabled    = Column(Boolean, default=True)
    is_verified   = Column(Boolean, default=False)
    last_verified = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)

    def set_api_key(self, plaintext: str) -> None:
        """Encrypt and store an API key."""
        from .encryption import encrypt_api_key
        self.api_key_enc = encrypt_api_key(plaintext)

    def get_api_key(self) -> str:
        """Decrypt and return the stored API key."""
        from .encryption import decrypt_api_key
        return decrypt_api_key(self.api_key_enc)


# ---------------------------------------------------------------------------
# CR-019 — Model Registry (static + dynamic model catalog)
# ---------------------------------------------------------------------------
class ModelRegistryEntry(Base):
    """Known model catalog — seeded from JSON, enriched by /models discovery."""
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_model_registry_provider_model"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    provider_id       = Column(String(50), nullable=False)     # 'openai', 'anthropic', etc.
    model_id          = Column(String(200), nullable=False)    # 'gpt-4o', 'claude-opus-4-5', etc.
    display_name      = Column(String(200), nullable=False)    # 'GPT-4o'
    tier              = Column(String(20), default="balanced")  # 'fast', 'balanced', 'quality', 'reasoning'
    context_window    = Column(Integer, nullable=True)         # e.g. 128000
    supports_vision   = Column(Boolean, default=False)
    supports_thinking = Column(Boolean, default=False)         # extended thinking / chain-of-thought
    supports_streaming = Column(Boolean, default=True)
    supports_json_mode = Column(Boolean, default=True)
    is_deprecated     = Column(Boolean, default=False)
    metadata_json     = Column(Text, default="{}")             # pricing, notes, etc. (stored as JSON text)
    created_at        = Column(DateTime, default=_now)


# ---------------------------------------------------------------------------
# CR-019 — User Model Preferences (per-user activation & defaults)
# ---------------------------------------------------------------------------
class UserModelPreference(Base):
    """Per-user model activation and default selection."""
    __tablename__ = "user_model_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", "model_id", "role",
                         name="uq_user_model_pref_user_provider_model_role"),
    )

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Uuid, nullable=False, index=True)
    provider_id = Column(String(50), nullable=False)
    model_id    = Column(String(200), nullable=False)
    is_active   = Column(Boolean, default=True)
    is_default  = Column(Boolean, default=False)
    role        = Column(String(30), default="council")  # 'council', 'chairman', 'observer', 'moderator'
    created_at  = Column(DateTime, default=_now)
