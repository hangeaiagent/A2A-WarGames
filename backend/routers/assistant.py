"""
AI Assistant endpoints — proposal enhancement and stakeholder profile extraction.

Endpoints:
  POST /api/assistant/enhance          — enhance a draft proposal
  POST /api/assistant/extract-profile  — extract stakeholder profile from text
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..auth import get_db_with_rls
from ..models import Project, LLMSettings
from ..a2a.llm_client import get_completion_json, get_completion_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _get_active_llm(db: Session) -> LLMSettings:
    """Return the active LLM profile or raise 503."""
    llm = db.query(LLMSettings).filter_by(is_active=True).first()
    if not llm:
        raise HTTPException(503, "No active LLM profile configured")
    return llm


# ---------------------------------------------------------------------------
# Enhance Proposal
# ---------------------------------------------------------------------------

class EnhanceRequest(BaseModel):
    proposal_text: str
    project_id: int
    tone: str = "professional"


class EnhanceResponse(BaseModel):
    enhanced_text: str
    key_changes: list[str]


@router.post("/enhance", response_model=EnhanceResponse)
async def enhance_proposal(req: EnhanceRequest, db: Session = Depends(get_db_with_rls)):
    project = db.query(Project).filter_by(id=req.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    llm = _get_active_llm(db)

    system_prompt = (
        "You are a strategic consultant helping to refine a proposal for stakeholder analysis.\n\n"
        f"Project: {project.name}\n"
        f"Context: {project.description or ''}\n\n"
        f"Your task: Rewrite the proposal to be more {req.tone}, specific, and persuasive.\n"
        "Add concrete metrics, timelines, and success criteria where missing.\n"
        "IMPORTANT: Respond with RAW JSON only. No markdown fences. No ```json blocks.\n"
        'Format: {"enhanced_text": "the enhanced proposal as a plain text string", "key_changes": ["change 1", "change 2", ...]}'
    )

    data = await get_completion_json(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.proposal_text},
        ],
        temperature=0.4,
        max_tokens=4096,
        agent_name="ai-assistant-enhance",
    )

    if data:
        return EnhanceResponse(
            enhanced_text=data.get("enhanced_text", ""),
            key_changes=data.get("key_changes", []),
        )
    # Fallback: get raw completion and return as plain text
    logger.warning("enhance_proposal: JSON parse failed, falling back to raw text")
    raw = await get_completion_content(
        base_url=llm.base_url, api_key=llm.api_key, model=llm.default_model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": req.proposal_text}],
        temperature=0.4, max_tokens=4096, agent_name="ai-assistant-enhance-fallback",
    )
    return EnhanceResponse(enhanced_text=raw, key_changes=[])


# ---------------------------------------------------------------------------
# Extract Stakeholder Profile
# ---------------------------------------------------------------------------

class ExtractProfileRequest(BaseModel):
    source_text: str
    project_id: int


class ExtractedProfile(BaseModel):
    name: str = ""
    role: str = ""
    department: str = ""
    goals: str = ""
    fears: str = ""
    influence: float = 0.5
    attitude_label: str = "neutral"
    key_motivations: list[str] = []
    success_criteria: list[str] = []

    @field_validator("goals", "fears", mode="before")
    @classmethod
    def coerce_list_to_str(cls, v):
        if isinstance(v, list):
            return "; ".join(str(i) for i in v)
        return v
    notes: str = ""


@router.post("/extract-profile", response_model=ExtractedProfile)
async def extract_stakeholder_profile(req: ExtractProfileRequest, db: Session = Depends(get_db_with_rls)):
    llm = _get_active_llm(db)

    system_prompt = (
        "Extract stakeholder profile fields from the provided text.\n"
        "IMPORTANT: Respond with RAW JSON only. No markdown fences. No ```json blocks.\n"
        "Output JSON with these exact keys: name, role, department, goals, fears,\n"
        "influence (0.0–1.0 float), attitude_label (one of: founder/enthusiast/conditional/critical/strategic/neutral),\n"
        "key_motivations (string array), success_criteria (string array), notes (string).\n"
        "If a field cannot be determined, use sensible defaults. Do NOT hallucinate — only extract what is present."
    )

    data = await get_completion_json(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.default_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.source_text},
        ],
        temperature=0.1,
        max_tokens=4096,
        agent_name="ai-assistant-extract",
    )

    if data:
        try:
            return ExtractedProfile(**data)
        except Exception as e:
            logger.warning("Failed to construct ExtractedProfile from parsed JSON: %s", e)
    logger.warning("extract_stakeholder_profile: LLM returned unparseable JSON")
    return ExtractedProfile()
