from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json
import uuid as _uuid

from ..auth import get_db_with_rls, get_current_user, require_user
from ..models import Project, Stakeholder, StakeholderEdge


def _parse_uid(sub: Optional[str]) -> Optional[_uuid.UUID]:
    """Convert a JWT 'sub' string to uuid.UUID. Returns None on failure."""
    if not sub:
        return None
    try:
        return _uuid.UUID(sub)
    except (ValueError, AttributeError):
        return None


def _guard_demo(project: Project):
    """Raise 403 if the project is a seeded demo (read-only)."""
    if project and getattr(project, "is_demo", False):
        raise HTTPException(403, "Demo projects are read-only")

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    organization: str = ""
    context: str = ""


class StakeholderIn(BaseModel):
    slug: str
    name: str
    role: str = ""
    department: str = ""
    attitude: str = "neutral"
    attitude_label: str = ""
    influence: float = 0.5
    interest: float = 0.5
    needs: list = []
    fears: list = []
    preconditions: list = []
    quote: str = ""
    signal_cle: str = ""
    adkar: dict = {}
    color: str = "#888888"
    avatar_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model_display: Optional[str] = None
    system_prompt: Optional[str] = None
    salience_power: int = 5
    salience_legitimacy: int = 5
    salience_urgency: int = 5
    salience_type: str = ""
    mendelow_quadrant: str = ""
    communication_style: str = ""
    attitude_baseline: str = ""
    interest_alignment: int = 0
    cognitive_biases: list = []
    batna: str = ""
    hard_constraints: list = []
    success_criteria: list = []
    key_concerns: list = []
    grounding_quotes: list = []
    anti_sycophancy: str = ""


def _project_out(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "organization": p.organization,
        "context": p.context,
        "is_active": p.is_active,
        "is_public": p.is_public,
        "is_demo": getattr(p, "is_demo", False),
        "stakeholder_count": len(p.stakeholders),
        "session_count": len(p.sessions),
        "created_at": p.created_at.isoformat(),
    }


def _stakeholder_out(s: Stakeholder) -> dict:
    return {
        "id": s.id,
        "slug": s.slug,
        "name": s.name,
        "role": s.role,
        "department": s.department,
        "attitude": s.attitude,
        "attitude_label": s.attitude_label,
        "influence": s.influence,
        "interest": s.interest,
        "needs": s.needs_list,
        "fears": s.fears_list,
        "preconditions": json.loads(s.preconditions or "[]"),
        "quote": s.quote,
        "signal_cle": s.signal_cle,
        "adkar": s.adkar_dict,
        "color": s.color,
        "avatar_url": s.avatar_url,
        "llm_model": s.llm_model,
        "llm_provider": s.llm_provider,
        "llm_model_display": s.llm_model_display,
        "is_active": s.is_active,
        "salience_power": s.salience_power,
        "salience_legitimacy": s.salience_legitimacy,
        "salience_urgency": s.salience_urgency,
        "salience_type": s.salience_type,
        "mendelow_quadrant": s.mendelow_quadrant,
        "communication_style": s.communication_style,
        "attitude_baseline": s.attitude_baseline,
        "interest_alignment": s.interest_alignment,
        "cognitive_biases": s.cognitive_biases_list,
        "batna": s.batna,
        "hard_constraints": s.hard_constraints_list,
        "success_criteria": s.success_criteria_list,
        "key_concerns": s.key_concerns_list,
        "grounding_quotes": s.grounding_quotes_list,
        "anti_sycophancy": s.anti_sycophancy,
    }


# --- Seed demo project (must be before /{project_id} routes) ---

@router.post("/seed-demo")
def seed_demo_project(db: Session = Depends(get_db_with_rls)):
    """Seed all demo projects from JSON fixtures in seed_data/. Idempotent."""
    from ..seed_demo import seed_fixtures
    seed_fixtures(db)
    db.commit()
    demos = db.query(Project).filter(Project.is_demo == True).all()  # noqa: E712
    return [_project_out(p) for p in demos]


# --- Projects CRUD ---

@router.get("/")
def list_projects(
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    uid = _parse_uid(user.get("sub") if user else None)
    q = db.query(Project)
    if uid:
        q = q.filter((Project.user_id == uid) | (Project.is_public == True))  # noqa: E712
    else:
        q = q.filter(Project.is_public == True)  # noqa: E712
    return [_project_out(p) for p in q.all()]


@router.get("/{project_id}")
def get_project(
    project_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    p = db.query(Project).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    uid = _parse_uid(user.get("sub") if user else None)
    if not p.is_public and p.user_id != uid:
        raise HTTPException(404, "Project not found")
    return _project_out(p)


@router.post("/", status_code=201)
def create_project(
    payload: ProjectIn,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    p = Project(**payload.model_dump(), user_id=_parse_uid(user.get("sub") if user else None))
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_out(p)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectIn,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    p = db.query(Project).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    _guard_demo(p)
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _project_out(p)


# --- Stakeholders ---

@router.get("/{project_id}/stakeholders")
def list_stakeholders(project_id: int, db: Session = Depends(get_db_with_rls)):
    stks = db.query(Stakeholder).filter_by(project_id=project_id, is_active=True).all()
    return [_stakeholder_out(s) for s in stks]


@router.post("/{project_id}/stakeholders", status_code=201)
def create_stakeholder(project_id: int, payload: StakeholderIn, db: Session = Depends(get_db_with_rls), user: dict = Depends(require_user)):
    _guard_demo(db.query(Project).filter_by(id=project_id).first())
    s = Stakeholder(
        project_id=project_id,
        slug=payload.slug,
        name=payload.name,
        role=payload.role,
        department=payload.department,
        attitude=payload.attitude,
        attitude_label=payload.attitude_label,
        influence=payload.influence,
        interest=payload.interest,
        needs=json.dumps(payload.needs),
        fears=json.dumps(payload.fears),
        preconditions=json.dumps(payload.preconditions),
        quote=payload.quote,
        signal_cle=payload.signal_cle,
        adkar=json.dumps(payload.adkar),
        color=payload.color,
        avatar_url=payload.avatar_url,
        llm_model=payload.llm_model,
        llm_provider=payload.llm_provider,
        llm_model_display=payload.llm_model_display,
        system_prompt=payload.system_prompt,
        salience_power=payload.salience_power,
        salience_legitimacy=payload.salience_legitimacy,
        salience_urgency=payload.salience_urgency,
        salience_type=payload.salience_type,
        mendelow_quadrant=payload.mendelow_quadrant,
        communication_style=payload.communication_style,
        attitude_baseline=payload.attitude_baseline,
        interest_alignment=payload.interest_alignment,
        cognitive_biases=json.dumps(payload.cognitive_biases),
        batna=payload.batna,
        hard_constraints=json.dumps(payload.hard_constraints),
        success_criteria=json.dumps(payload.success_criteria),
        key_concerns=json.dumps(payload.key_concerns),
        grounding_quotes=json.dumps(payload.grounding_quotes),
        anti_sycophancy=payload.anti_sycophancy,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _stakeholder_out(s)


@router.put("/{project_id}/stakeholders/{stakeholder_id}")
def update_stakeholder(
    project_id: int,
    stakeholder_id: int,
    payload: StakeholderIn,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    _guard_demo(db.query(Project).filter_by(id=project_id).first())
    s = db.query(Stakeholder).filter_by(id=stakeholder_id, project_id=project_id).first()
    if not s:
        raise HTTPException(404, "Stakeholder not found")
    s.name = payload.name
    s.role = payload.role
    s.department = payload.department
    s.attitude = payload.attitude
    s.attitude_label = payload.attitude_label
    s.influence = payload.influence
    s.interest = payload.interest
    s.needs = json.dumps(payload.needs)
    s.fears = json.dumps(payload.fears)
    s.preconditions = json.dumps(payload.preconditions)
    s.quote = payload.quote
    s.signal_cle = payload.signal_cle
    s.adkar = json.dumps(payload.adkar)
    s.color = payload.color
    s.avatar_url = payload.avatar_url
    s.llm_model = payload.llm_model
    s.llm_provider = payload.llm_provider
    s.llm_model_display = payload.llm_model_display
    s.system_prompt = payload.system_prompt
    s.salience_power = payload.salience_power
    s.salience_legitimacy = payload.salience_legitimacy
    s.salience_urgency = payload.salience_urgency
    s.salience_type = payload.salience_type
    s.mendelow_quadrant = payload.mendelow_quadrant
    s.communication_style = payload.communication_style
    s.attitude_baseline = payload.attitude_baseline
    s.interest_alignment = payload.interest_alignment
    s.cognitive_biases = json.dumps(payload.cognitive_biases)
    s.batna = payload.batna
    s.hard_constraints = json.dumps(payload.hard_constraints)
    s.success_criteria = json.dumps(payload.success_criteria)
    s.key_concerns = json.dumps(payload.key_concerns)
    s.grounding_quotes = json.dumps(payload.grounding_quotes)
    s.anti_sycophancy = payload.anti_sycophancy
    db.commit()
    db.refresh(s)
    return _stakeholder_out(s)


@router.delete("/{project_id}/stakeholders/{stakeholder_id}")
def deactivate_stakeholder(
    project_id: int,
    stakeholder_id: int,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    _guard_demo(db.query(Project).filter_by(id=project_id).first())
    s = db.query(Stakeholder).filter_by(id=stakeholder_id, project_id=project_id).first()
    if not s:
        raise HTTPException(404, "Stakeholder not found")
    s.is_active = False
    db.commit()
    return {"deactivated": stakeholder_id}


# --- Edges ---

@router.get("/{project_id}/edges")
def list_edges(project_id: int, db: Session = Depends(get_db_with_rls)):
    edges = db.query(StakeholderEdge).filter_by(project_id=project_id).all()
    return [
        {"id": e.id, "source": e.source_slug, "target": e.target_slug,
         "type": e.edge_type, "label": e.label, "strength": e.strength}
        for e in edges
    ]


# --- Visibility / Share ---

@router.patch("/{project_id}/visibility")
def toggle_visibility(
    project_id: int,
    body: dict,
    user: dict = Depends(require_user),
    db: Session = Depends(get_db_with_rls),
):
    """Toggle is_public on an owned project. Demo projects cannot be changed."""
    p = db.query(Project).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    _guard_demo(p)
    uid = _parse_uid(user.get("sub"))
    if p.user_id is not None and p.user_id != uid:
        raise HTTPException(403, "Not the project owner")
    p.is_public = body.get("is_public", p.is_public)
    db.commit()
    db.refresh(p)
    return _project_out(p)


@router.get("/public/browse")
def browse_public(
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db_with_rls),
):
    """Paginated list of all public projects (demos pinned first)."""
    from sqlalchemy import desc, case
    q = db.query(Project).filter(
        Project.is_public == True,  # noqa: E712
        Project.is_active == True,  # noqa: E712
    ).order_by(
        desc(case((Project.is_demo == True, 1), else_=0)),  # demos first
        desc(Project.created_at),
    )
    total = q.count()
    projects = q.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_project_out(p) for p in projects],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
