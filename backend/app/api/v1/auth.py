"""Auth router — Login, registration, invite, and set-password endpoints."""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AdminCreateUser,
    AdminUserRow,
    InviteInfoResponse,
    SetPasswordRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

INVITE_EXPIRY_DAYS = 7


def _hash_token(token: str) -> str:
    """SHA-256 hash a raw invite token."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Register (self-registration) ────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: DbSession):
    """Register a new user."""
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        department=data.department,
        role=data.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(data={"sub": user.id, "department": user.department, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ── Login ────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: DbSession):
    """Login and get access token."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Please complete your registration via invite link.",
        )

    token = create_access_token(data={"sub": user.id, "department": user.department, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ── Invite Info (public) ────────────────────

@router.get("/invite-info")
async def invite_info(token: str, db: DbSession) -> InviteInfoResponse:
    """Validate invite token and return user info for the invite page."""
    token_hash = _hash_token(token)
    result = await db.execute(select(User).where(User.invite_token_hash == token_hash))
    user = result.scalar_one_or_none()

    if not user:
        return InviteInfoResponse(
            name="", email="", department="", role="",
            valid=False, message="Invalid invite link.",
        )

    if user.invite_expires_at and user.invite_expires_at < datetime.now(timezone.utc):
        return InviteInfoResponse(
            name=user.name, email=user.email, department=user.department, role=user.role,
            valid=False, message="Invite link has expired. Contact your admin for a new one.",
        )

    if user.is_active:
        return InviteInfoResponse(
            name=user.name, email=user.email, department=user.department, role=user.role,
            valid=False, message="Account is already active. Please login instead.",
        )

    return InviteInfoResponse(
        name=user.name, email=user.email, department=user.department, role=user.role,
        valid=True, message="Set your password to activate your account.",
    )


# ── Set Password (public) ──────────────────

@router.post("/set-password")
async def set_password(data: SetPasswordRequest, db: DbSession):
    """User sets password via invite token. Activates the account."""
    token_hash = _hash_token(data.token)
    result = await db.execute(select(User).where(User.invite_token_hash == token_hash))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid invite token.")

    if user.invite_expires_at and user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite token has expired.")

    if user.is_active:
        raise HTTPException(status_code=400, detail="Account is already active.")

    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    # Activate user
    user.hashed_password = hash_password(data.password)
    user.is_active = True
    user.invite_token_hash = None
    user.invite_expires_at = None

    await db.flush()

    token = create_access_token(data={"sub": user.id, "department": user.department, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )
