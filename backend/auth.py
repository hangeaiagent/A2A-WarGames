"""
Supabase JWT validation for FastAPI.

Validates JWTs from Supabase Auth, extracts user_id,
and provides a DB dependency that sets the RLS session variable.
"""

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text
from typing import Optional

from .config import settings
from .database import get_db

security = HTTPBearer(auto_error=False)


def decode_supabase_jwt(token: str) -> dict:
    """Decode and validate a Supabase Auth JWT."""
    if not settings.supabase_jwt_secret:
        # No JWT secret configured — skip validation (dev mode)
        return jwt.decode(token, options={"verify_signature": False})
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Extract user from JWT. Returns None if no auth header."""
    if not credentials:
        return None
    return decode_supabase_jwt(credentials.credentials)


async def require_user(
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Require authentication. Raises 401 if no valid JWT."""
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def get_db_with_rls(
    user: Optional[dict] = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> DBSession:
    """Get a DB session with RLS user context set.

    Sets `app.user_id` as a PostgreSQL session variable
    so RLS policies can use current_setting('app.user_id').
    """
    if user and user.get("sub") and not settings.database_url.startswith("sqlite"):
        db.execute(text("SET LOCAL app.user_id = :user_id"), {"user_id": user["sub"]})
    return db
