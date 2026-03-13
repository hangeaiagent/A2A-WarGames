from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import ipaddress
import json
import logging
import re
import uuid as _uuid
from urllib.parse import urlparse


def _parse_uid(sub: Optional[str]) -> Optional[_uuid.UUID]:
    if not sub:
        return None
    try:
        return _uuid.UUID(sub)
    except (ValueError, AttributeError):
        return None

import httpx

from ..auth import get_db_with_rls, get_current_user, require_user
from ..models import LLMSettings, ModelRegistryEntry, UserModelPreference, ProviderKey
from ..provider_presets import get_presets, get_preset_by_id

logger = logging.getLogger(__name__)

# RFC 1918 / loopback / link-local ranges that must not be reachable via SSRF
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("0.0.0.0/8"),       # #219: INADDR_ANY
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),        # #219: IPv6 link-local
    ipaddress.ip_network("::ffff:0:0/96"),    # #219: IPv4-mapped IPv6 (covers ::ffff:10.x, ::ffff:127.x, etc.)
]


def _validate_proxy_url(url: str) -> None:
    """Raise HTTPException 400 if url is not a safe http/https URL pointing to a public host. (#216, #219)"""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(400, "Invalid base_url")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "base_url must use http or https scheme")
    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(400, "base_url has no hostname")
    # #219: Block credential injection (e.g. http://user:pass@internal-host/)
    if parsed.username or parsed.password:
        raise HTTPException(400, "base_url must not contain credentials")
    # Block localhost by name
    if hostname.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
        raise HTTPException(400, "base_url must not target localhost")
    # Block by IP range
    try:
        addr = ipaddress.ip_address(hostname)
        # #219: For IPv4-mapped IPv6 addresses (::ffff:x.x.x.x), also check the mapped IPv4
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            mapped = addr.ipv4_mapped
            for net in _PRIVATE_NETWORKS:
                if net.version == 4 and mapped in net:
                    raise HTTPException(400, "base_url must not target private/internal IP ranges")
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                raise HTTPException(400, "base_url must not target private/internal IP ranges")
    except ValueError:
        pass  # hostname is a domain name, not an IP — allow

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LLMSettingsIn(BaseModel):
    profile_name: str = "default"
    base_url: str
    api_key: str
    default_model: str
    chairman_model: str
    council_models: List[str]
    temperature: float = 0.8
    max_tokens: int = 1024
    feature_flags: Optional[dict] = {}
    # TTS settings
    tts_enabled:   bool = False
    tts_model:     str = "tts-1"
    tts_voice:     str = "alloy"
    tts_speed:     float = 1.0
    tts_auto_play: bool = False
    tts_language:  str = "auto"
    # STT settings
    stt_enabled:   bool = False
    stt_model:     str = "whisper-1"
    stt_language:  str = "auto"
    stt_auto_send: bool = False


class LLMSettingsOut(LLMSettingsIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


def _to_out(s: LLMSettings) -> dict:
    return {
        "id": s.id,
        "profile_name": s.profile_name,
        "is_active": s.is_active,
        "base_url": s.base_url,
        "api_key": "***" if s.api_key else "",
        "default_model": s.default_model,
        "chairman_model": s.chairman_model,
        "council_models": s.council_models_list,
        "temperature": s.temperature,
        "max_tokens": s.max_tokens,
        "feature_flags": s.feature_flags_dict,
        # TTS
        "tts_enabled":   s.tts_enabled if s.tts_enabled is not None else False,
        "tts_model":     s.tts_model or "tts-1",
        "tts_voice":     s.tts_voice or "alloy",
        "tts_speed":     s.tts_speed if s.tts_speed is not None else 1.0,
        "tts_auto_play": s.tts_auto_play if s.tts_auto_play is not None else False,
        "tts_language":  s.tts_language or "auto",
        # STT
        "stt_enabled":   s.stt_enabled if s.stt_enabled is not None else False,
        "stt_model":     s.stt_model or "whisper-1",
        "stt_language":  s.stt_language or "auto",
        "stt_auto_send": s.stt_auto_send if s.stt_auto_send is not None else False,
    }


@router.get("/")
def list_profiles(db: Session = Depends(get_db_with_rls)):
    return [_to_out(s) for s in db.query(LLMSettings).all()]


@router.get("/active")
def get_active(db: Session = Depends(get_db_with_rls)):
    s = db.query(LLMSettings).filter_by(is_active=True).first()
    if not s:
        return None   # 200 + null body — frontend handles "not configured" state
    return _to_out(s)


@router.get("/providers")
def list_providers():
    """Return known LLM provider presets for the frontend provider selector."""
    return get_presets()


@router.post("/test-connection")
async def test_connection(
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """
    Bottom-up health check of the active LLM profile.

    Tests: DNS/TLS, auth, model list, batch completion per council model,
    streaming completion per council model.  Returns a structured report.
    """
    import time as _time

    settings = db.query(LLMSettings).filter_by(is_active=True).first()
    if not settings:
        raise HTTPException(400, "No active LLM settings")

    base_url = settings.base_url.rstrip("/")
    api_key = settings.api_key
    council = settings.council_models_list
    results = {"profile": settings.profile_name, "base_url": base_url, "checks": []}

    def _add(name, ok, detail="", latency=None):
        entry = {"name": name, "ok": ok, "detail": detail}
        if latency is not None:
            entry["latency_s"] = round(latency, 2)
        results["checks"].append(entry)

    # 1. Connectivity + auth
    try:
        t0 = _time.time()
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
        elapsed = _time.time() - t0
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", []) if "id" in m]
            _add("connectivity", True, f"{len(models)} models available", elapsed)
        elif r.status_code == 401:
            _add("connectivity", False, "401 Unauthorized - check API key", elapsed)
            results["summary"] = "Auth failed"
            return results
        else:
            _add("connectivity", False, f"HTTP {r.status_code}", elapsed)
    except Exception as e:
        _add("connectivity", False, str(e))
        results["summary"] = "Connection failed"
        return results

    # 2. Model availability
    for m in council:
        _add(f"model_available:{m}", m in models, "found" if m in models else "NOT in model list")

    # 3. Batch completion per model
    for m in council:
        try:
            t0 = _time.time()
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
                r = await c.post(
                    f"{base_url}/chat/completions",
                    json={"model": m, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 20, "temperature": 0},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
            elapsed = _time.time() - t0
            if r.status_code == 200:
                data = r.json()
                msg = data.get("choices", [{}])[0].get("message", {})
                content = msg.get("content", "")
                reasoning = msg.get("reasoning", "")
                finish = data.get("choices", [{}])[0].get("finish_reason", "")
                has_content = bool(content.strip())
                has_reasoning = bool(reasoning.strip())
                detail = f"content={len(content)}ch"
                if has_reasoning:
                    detail += f" reasoning={len(reasoning)}ch"
                detail += f" finish={finish}"
                if not has_content and has_reasoning:
                    detail += " WARNING:reasoning-only"
                _add(f"batch:{m}", has_content or has_reasoning, detail, elapsed)
            else:
                _add(f"batch:{m}", False, f"HTTP {r.status_code}", _time.time() - t0)
        except Exception as e:
            _add(f"batch:{m}", False, f"{type(e).__name__}: {e}")

    # 4. Streaming per model
    for m in council:
        try:
            t0 = _time.time()
            content_len = 0
            reasoning_len = 0
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as c:
                async with c.stream(
                    "POST", f"{base_url}/chat/completions",
                    json={"model": m, "messages": [{"role": "user", "content": "Reply: OK"}], "max_tokens": 20, "temperature": 0, "stream": True},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                ) as resp:
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        ds = line[6:]
                        if ds == "[DONE]":
                            break
                        try:
                            chunk = json.loads(ds)
                            choices = chunk.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            fr = choices[0].get("finish_reason")
                            cd = delta.get("content", "")
                            rd = delta.get("reasoning", "") or delta.get("reasoning_content", "")
                            if cd:
                                content_len += len(cd)
                            if rd:
                                reasoning_len += len(rd)
                            if fr in ("stop", "length", "end_turn"):
                                break
                        except json.JSONDecodeError:
                            pass
            elapsed = _time.time() - t0
            detail = f"content={content_len}ch"
            if reasoning_len:
                detail += f" reasoning={reasoning_len}ch"
            _add(f"stream:{m}", content_len > 0 or reasoning_len > 0, detail, elapsed)
        except Exception as e:
            _add(f"stream:{m}", False, f"{type(e).__name__}: {e}")

    # Summary
    failed = [c for c in results["checks"] if not c["ok"]]
    results["summary"] = f"{len(results['checks']) - len(failed)}/{len(results['checks'])} passed"
    if failed:
        results["summary"] += f" ({len(failed)} failed: {', '.join(c['name'] for c in failed)})"
    return results


@router.post("/", status_code=201)
def create_profile(
    payload: LLMSettingsIn,
    user: Optional[dict] = Depends(get_current_user),
    db: Session = Depends(get_db_with_rls),
):
    existing = db.query(LLMSettings).filter_by(profile_name=payload.profile_name).first()
    if existing:
        raise HTTPException(400, f"Profile '{payload.profile_name}' already exists")
    s = LLMSettings(
        profile_name=payload.profile_name,
        user_id=_parse_uid(user.get("sub") if user else None),
        base_url=payload.base_url,
        api_key=payload.api_key,
        default_model=payload.default_model,
        chairman_model=payload.chairman_model,
        council_models=json.dumps(payload.council_models),
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        feature_flags=json.dumps(payload.feature_flags or {}),
        tts_enabled=payload.tts_enabled,
        tts_model=payload.tts_model,
        tts_voice=payload.tts_voice,
        tts_speed=payload.tts_speed,
        tts_auto_play=payload.tts_auto_play,
        tts_language=payload.tts_language,
        stt_enabled=payload.stt_enabled,
        stt_model=payload.stt_model,
        stt_language=payload.stt_language,
        stt_auto_send=payload.stt_auto_send,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.put("/{profile_name}")
def update_profile(profile_name: str, payload: LLMSettingsIn, db: Session = Depends(get_db_with_rls), user: dict = Depends(require_user)):
    s = db.query(LLMSettings).filter_by(profile_name=profile_name).first()
    if not s:
        raise HTTPException(404, "Profile not found")
    if payload.profile_name and payload.profile_name != profile_name:
        # #124: check for name collision before renaming to avoid IntegrityError 500
        collision = db.query(LLMSettings).filter_by(profile_name=payload.profile_name).first()
        if collision:
            raise HTTPException(409, f"Profile '{payload.profile_name}' already exists")
        s.profile_name = payload.profile_name
    s.base_url = payload.base_url
    if payload.api_key and payload.api_key != "***":
        s.api_key = payload.api_key
    s.default_model = payload.default_model
    s.chairman_model = payload.chairman_model
    s.council_models = json.dumps(payload.council_models)
    s.temperature = payload.temperature
    s.max_tokens = payload.max_tokens
    s.feature_flags = json.dumps(payload.feature_flags or {})
    s.tts_enabled = payload.tts_enabled
    s.tts_model = payload.tts_model
    s.tts_voice = payload.tts_voice
    s.tts_speed = payload.tts_speed
    s.tts_auto_play = payload.tts_auto_play
    s.tts_language = payload.tts_language
    s.stt_enabled = payload.stt_enabled
    s.stt_model = payload.stt_model
    s.stt_language = payload.stt_language
    s.stt_auto_send = payload.stt_auto_send
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.post("/{profile_name}/activate")
def activate_profile(profile_name: str, db: Session = Depends(get_db_with_rls), user: dict = Depends(require_user)):
    # #161: verify target exists BEFORE deactivating all profiles to prevent
    # leaving the system with zero active LLM profiles on a typo/404
    s = db.query(LLMSettings).filter_by(profile_name=profile_name).first()
    if not s:
        raise HTTPException(404, "Profile not found")
    db.query(LLMSettings).update({"is_active": False})
    s.is_active = True
    db.commit()
    return {"activated": profile_name}


@router.delete("/{profile_name}", status_code=204)
def delete_profile(
    profile_name: str,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Delete an LLM settings profile. The active profile cannot be deleted. (#123)"""
    s = db.query(LLMSettings).filter_by(profile_name=profile_name).first()
    if not s:
        raise HTTPException(404, "Profile not found")
    if s.is_active:
        raise HTTPException(409, "Cannot delete the active profile — deactivate it first by activating another profile")
    db.delete(s)
    db.commit()


@router.get("/models")
async def get_available_models(db: Session = Depends(get_db_with_rls)):
    """Proxy GET {llm_base_url}/models and return model IDs."""
    settings = db.query(LLMSettings).filter_by(is_active=True).first()
    if not settings:
        raise HTTPException(400, "No active LLM settings")

    _validate_proxy_url(settings.base_url)  # #216: SSRF guard
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.base_url}/models",
                headers={"Authorization": f"Bearer {settings.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            # OpenAI / Ollama / LM Studio all return {"data": [{"id": "model-name", ...}]}
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            return {"models": models, "provider_url": settings.base_url}
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Failed to fetch models from %s: %s", settings.base_url, e)
            raise HTTPException(502, f"Could not fetch models from LLM provider: {e}")


@router.get("/voices")
async def get_available_voices(db: Session = Depends(get_db_with_rls)):
    """Proxy GET {base_url}/audio/voices — returns available TTS voice list."""
    settings = db.query(LLMSettings).filter(LLMSettings.is_active.is_(True)).first()
    if not settings:
        raise HTTPException(404, "No active LLM profile")
    _validate_proxy_url(settings.base_url)  # #216: SSRF guard
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.base_url.rstrip('/')}/audio/voices",
                headers={"Authorization": f"Bearer {settings.api_key}"},
            )
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except Exception:
        # Provider may not support /audio/voices — return common defaults
        return {"voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]}


@router.get("/presets")
async def get_provider_presets():
    """Return the list of known LLM provider presets for quick-setup on the settings page."""
    return {"presets": get_presets()}


# ---------------------------------------------------------------------------
# CR-019 — Model Registry & User Model Preferences
# ---------------------------------------------------------------------------

class DefaultModelIn(BaseModel):
    provider_id: str
    model_id: str


@router.get("/models/registry")
def get_model_registry(
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Return all model_registry entries, enriched with user's is_active/is_default."""
    uid = user.get("sub")
    entries = db.query(ModelRegistryEntry).all()

    # Fetch user prefs in one query
    prefs = db.query(UserModelPreference).filter_by(user_id=uid).all()
    pref_map = {}
    for p in prefs:
        pref_map[(p.provider_id, p.model_id, p.role)] = p

    result = []
    for e in entries:
        # Look up user preference for the default 'council' role
        pref = pref_map.get((e.provider_id, e.model_id, "council"))
        result.append({
            "id": e.id,
            "provider_id": e.provider_id,
            "model_id": e.model_id,
            "display_name": e.display_name,
            "tier": e.tier,
            "context_window": e.context_window,
            "supports_vision": e.supports_vision,
            "supports_thinking": e.supports_thinking,
            "supports_streaming": e.supports_streaming,
            "supports_json_mode": e.supports_json_mode,
            "is_deprecated": e.is_deprecated,
            "is_active": pref.is_active if pref else False,
            "is_default": pref.is_default if pref else False,
        })
    return result


@router.post("/models/refresh")
async def refresh_model_registry(
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """For each configured provider key, fetch /models and upsert into model_registry."""
    uid = user.get("sub")
    keys = db.query(ProviderKey).filter_by(user_id=uid, is_enabled=True).all()

    results = {}
    for pk in keys:
        # Resolve base_url
        base_url = pk.base_url
        if not base_url:
            preset = get_preset_by_id(pk.provider_id)
            if preset:
                base_url = preset.get("base_url", "")
        if not base_url:
            results[pk.provider_id] = {"ok": False, "detail": "No base_url"}
            continue

        base_url = base_url.rstrip("/")
        try:
            _validate_proxy_url(base_url)
        except HTTPException:
            results[pk.provider_id] = {"ok": False, "detail": "Invalid base_url (SSRF blocked)"}
            continue

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
        except Exception as e:
            results[pk.provider_id] = {"ok": False, "detail": str(e)}
            continue

        # Upsert discovered models
        upserted = 0
        for model_id in models:
            existing = (
                db.query(ModelRegistryEntry)
                .filter_by(provider_id=pk.provider_id, model_id=model_id)
                .first()
            )
            if not existing:
                entry = ModelRegistryEntry(
                    provider_id=pk.provider_id,
                    model_id=model_id,
                    display_name=model_id,
                    tier="balanced",
                )
                db.add(entry)
                upserted += 1
        try:
            db.commit()
        except Exception:
            db.rollback()

        results[pk.provider_id] = {
            "ok": True,
            "models_found": len(models),
            "new_models": upserted,
        }

    return {"refreshed": results}


@router.put("/models/{provider_id}/{model_id}/toggle")
def toggle_model(
    provider_id: str,
    model_id: str,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Toggle is_active in user_model_preferences for current user."""
    uid = user.get("sub")

    # Verify model exists in registry
    entry = db.query(ModelRegistryEntry).filter_by(
        provider_id=provider_id, model_id=model_id
    ).first()
    if not entry:
        raise HTTPException(404, "Model not found in registry")

    pref = db.query(UserModelPreference).filter_by(
        user_id=uid, provider_id=provider_id, model_id=model_id, role="council"
    ).first()

    if pref:
        pref.is_active = not pref.is_active
    else:
        pref = UserModelPreference(
            user_id=uid,
            provider_id=provider_id,
            model_id=model_id,
            role="council",
            is_active=True,
        )
        db.add(pref)

    db.commit()
    db.refresh(pref)
    return {
        "provider_id": provider_id,
        "model_id": model_id,
        "is_active": pref.is_active,
    }


@router.put("/defaults")
def set_default_model(
    payload: DefaultModelIn,
    db: Session = Depends(get_db_with_rls),
    user: dict = Depends(require_user),
):
    """Set account-wide default provider + model. Clears other defaults first."""
    uid = user.get("sub")

    # Verify model exists in registry
    entry = db.query(ModelRegistryEntry).filter_by(
        provider_id=payload.provider_id, model_id=payload.model_id
    ).first()
    if not entry:
        raise HTTPException(404, "Model not found in registry")

    # Clear all existing defaults for this user
    db.query(UserModelPreference).filter_by(
        user_id=uid, is_default=True
    ).update({"is_default": False}, synchronize_session=False)

    # Upsert the new default
    pref = db.query(UserModelPreference).filter_by(
        user_id=uid,
        provider_id=payload.provider_id,
        model_id=payload.model_id,
        role="council",
    ).first()

    if pref:
        pref.is_default = True
        pref.is_active = True
    else:
        pref = UserModelPreference(
            user_id=uid,
            provider_id=payload.provider_id,
            model_id=payload.model_id,
            role="council",
            is_active=True,
            is_default=True,
        )
        db.add(pref)

    db.commit()
    return {
        "provider_id": payload.provider_id,
        "model_id": payload.model_id,
        "is_default": True,
    }
