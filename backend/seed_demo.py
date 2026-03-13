"""
Seed the database with demo projects from JSON fixtures.
Each JSON file in seed_data/ defines one demo project with stakeholders and edges.
"""
import json
from pathlib import Path

from .models import Project, Stakeholder, StakeholderEdge

SEED_DATA_DIR = Path(__file__).parent / "seed_data"


def _load_fixture(filename: str) -> dict:
    filepath = SEED_DATA_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _seed_one(db, fixture: dict):
    """Seed a single demo project from a fixture dict. Idempotent."""
    proj_data = fixture["project"]
    existing = db.query(Project).filter_by(name=proj_data["name"]).first()
    if existing:
        if not getattr(existing, "is_demo", False):
            existing.is_demo = True
        return existing

    project = Project(
        name=proj_data["name"],
        description=proj_data.get("description", ""),
        organization=proj_data.get("organization", ""),
        context=proj_data.get("context", ""),
        is_public=True,
        is_demo=True,
        user_id=None,
    )
    db.add(project)
    db.flush()

    for s in fixture.get("stakeholders", []):
        db.add(Stakeholder(
            project_id=project.id,
            slug=s["slug"],
            name=s["name"],
            role=s.get("role", ""),
            department=s.get("department", ""),
            attitude=s.get("attitude", "neutral"),
            attitude_label=s.get("attitude_label", ""),
            influence=s.get("influence", 0.5),
            interest=s.get("interest", 0.5),
            needs=json.dumps(s.get("needs", [])),
            fears=json.dumps(s.get("fears", [])),
            preconditions=json.dumps(s.get("preconditions", [])),
            quote=s.get("quote", ""),
            signal_cle=s.get("signal_cle", ""),
            adkar=json.dumps(s.get("adkar", {})),
            color=s.get("color", "#888888"),
            avatar_url=s.get("avatar_url"),
            salience_power=s.get("salience_power", 5),
            salience_legitimacy=s.get("salience_legitimacy", 5),
            salience_urgency=s.get("salience_urgency", 5),
            salience_type=s.get("salience_type", ""),
            mendelow_quadrant=s.get("mendelow_quadrant", ""),
            communication_style=s.get("communication_style", ""),
            attitude_baseline=s.get("attitude_baseline", ""),
            interest_alignment=s.get("interest_alignment", 0),
            cognitive_biases=json.dumps(s.get("cognitive_biases", [])),
            batna=s.get("batna", ""),
            hard_constraints=json.dumps(s.get("hard_constraints", [])),
            success_criteria=json.dumps(s.get("success_criteria", [])),
            key_concerns=json.dumps(s.get("key_concerns", [])),
            grounding_quotes=json.dumps(s.get("grounding_quotes", [])),
            anti_sycophancy=s.get("anti_sycophancy", ""),
        ))

    for e in fixture.get("edges", []):
        db.add(StakeholderEdge(
            project_id=project.id,
            source_slug=e["source"],
            target_slug=e["target"],
            edge_type=e.get("edge_type", "tension"),
            label=e.get("label", ""),
            strength=e.get("strength", 0.5),
        ))

    return project


def seed_fixtures(db):
    """Seed all demo projects from JSON fixtures in seed_data/. Idempotent."""
    for filepath in sorted(SEED_DATA_DIR.glob("*.json")):
        fixture = _load_fixture(filepath.name)
        _seed_one(db, fixture)
