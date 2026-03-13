"""
CR-019 — Provider management router.

Endpoints for managing per-user LLM provider API keys, testing
connectivity, and fetching available models from provider APIs.

All endpoints require authentication via ``require_user`` / ``get_db_with_rls``.
"""

import datetime
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_db_with_rls, require_user
from ..models import ProviderKey, ModelRegistryEntry
from ..provider_presets import get_presets, get_preset_by_id
from .settings import _validate_proxy_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProviderKeyIn(BaseModel):
    provider_id: str
    api_key: str
    base_url: Optional[str] = None


class ProviderKeyOut(BaseModel):
    provider_id: str
    api_key_masked: str
    base_url: Optional[str] = None
    is_enabled: bool = True
    is_verified: bool = False
    last_verified: Optional[str] = None


class TestResult(BaseModel):
    provider_id: str
    ok: bool
    detail: str = ""
    models_found: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_key(plaintext: str) -> str:
    """Mask an API key for display: show first 5 + last 3 chars."""
    if len(plaintext) <= 8:
        return "***"
    return plaintext[:5] + "***" + plaintext[-3:]


def _key_to_out(pk: ProviderKey) -> dict:
    """Serialize a ProviderKey row for API response (key masked)."""
    try:
        raw_key = pk.get_api_key()
        masked = _mask_key(raw_key)
    except Exception:
        masked = "***"
    return {
        "provider_id": pk.provider_id,
        "api_key_masked": masked,
        "base_url": pk.base_url,
        "is_enabled": pk.is_enabled,
        "is_verified": pk.is_verified,
        "last_verified": pk.last_verified.isoformat() if pk.last_verified else None,
    }


def _resolve_base_url(pk: ProviderKey) -> str:
    """Return the effective base_url — custom override or preset default."""
    if pk.base_url:
        return pk.base_url.rstrip("/")
    preset = get_preset_by_id(pk.provider_id)
    if preset and preset.get("base_url"):
        return preset["base_url"].rstrip("/")
    raise HTTPException(400, f"No base_url configured for provider '{pk.provider_id}'")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_provider_presets():
    """Return all provider presets (static catalog)."""
    return get_presets()


@router.get("/keys")
def list_provider_keys(
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """List user's configured provider keys with masked API keys."""
    uid = user.get("sub")
    keys = db.query(ProviderKey).filter_by(user_id=uid).all()
    return [_key_to_out(k) for k in keys]


@router.post("/keys", status_code=201)
def upsert_provider_key(
    payload: ProviderKeyIn,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Add or update an API key for a provider. Encrypts key at rest."""
    uid = user.get("sub")

    # SSRF validation on custom base_url
    if payload.base_url:
        _validate_proxy_url(payload.base_url)

    existing = (
        db.query(ProviderKey)
        .filter_by(user_id=uid, provider_id=payload.provider_id)
        .first()
    )

    if existing:
        existing.set_api_key(payload.api_key)
        if payload.base_url is not None:
            existing.base_url = payload.base_url or None
        existing.is_verified = False  # re-verify after key change
        existing.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        db.refresh(existing)
        return _key_to_out(existing)
    else:
        pk = ProviderKey(
            user_id=uid,
            provider_id=payload.provider_id,
            base_url=payload.base_url or None,
        )
        pk.set_api_key(payload.api_key)
        db.add(pk)
        db.commit()
        db.refresh(pk)
        return _key_to_out(pk)


@router.delete("/keys/{provider_id}", status_code=204)
def delete_provider_key(
    provider_id: str,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Remove a provider key for the current user."""
    uid = user.get("sub")
    pk = db.query(ProviderKey).filter_by(user_id=uid, provider_id=provider_id).first()
    if not pk:
        raise HTTPException(404, f"No key configured for provider '{provider_id}'")
    db.delete(pk)
    db.commit()


@router.post("/keys/{provider_id}/test")
async def test_provider_key(
    provider_id: str,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Test connectivity for a specific provider key. Updates verified status."""
    uid = user.get("sub")
    pk = db.query(ProviderKey).filter_by(user_id=uid, provider_id=provider_id).first()
    if not pk:
        raise HTTPException(404, f"No key configured for provider '{provider_id}'")

    base_url = _resolve_base_url(pk)
    _validate_proxy_url(base_url)
    api_key = pk.get_api_key()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            pk.is_verified = True
            pk.last_verified = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return {
                "provider_id": provider_id,
                "ok": True,
                "detail": f"{len(models)} models available",
                "models_found": len(models),
            }
        elif resp.status_code == 401:
            pk.is_verified = False
            db.commit()
            return {
                "provider_id": provider_id,
                "ok": False,
                "detail": "401 Unauthorized — check API key",
                "models_found": 0,
            }
        else:
            pk.is_verified = False
            db.commit()
            return {
                "provider_id": provider_id,
                "ok": False,
                "detail": f"HTTP {resp.status_code}",
                "models_found": 0,
            }
    except Exception as e:
        pk.is_verified = False
        db.commit()
        return {
            "provider_id": provider_id,
            "ok": False,
            "detail": f"{type(e).__name__}: {e}",
            "models_found": 0,
        }


@router.get("/{provider_id}/models")
async def fetch_provider_models(
    provider_id: str,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Fetch available models from a provider's /models endpoint.

    Uses the user's stored key for the provider. Optionally upserts
    discovered models into the model_registry table.
    """
    uid = user.get("sub")
    pk = db.query(ProviderKey).filter_by(user_id=uid, provider_id=provider_id).first()
    if not pk:
        raise HTTPException(404, f"No key configured for provider '{provider_id}'")

    base_url = _resolve_base_url(pk)
    _validate_proxy_url(base_url)
    api_key = pk.get_api_key()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if "id" in m]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to fetch models from %s for provider %s: %s", base_url, provider_id, e)
        raise HTTPException(502, f"Could not fetch models from provider: {e}")

    # Upsert discovered models into model_registry
    for model_id in models:
        existing = (
            db.query(ModelRegistryEntry)
            .filter_by(provider_id=provider_id, model_id=model_id)
            .first()
        )
        if not existing:
            entry = ModelRegistryEntry(
                provider_id=provider_id,
                model_id=model_id,
                display_name=model_id,  # best we can do from /models
                tier="balanced",
            )
            db.add(entry)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to upsert discovered models for %s", provider_id)

    return {"provider_id": provider_id, "models": models}
