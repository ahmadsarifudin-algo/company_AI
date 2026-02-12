"""Auth schemas — Login, register, invite, and set-password request/response."""

from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    department: str
    role: str = "contributor"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    department: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Admin-driven invite flow ────────────────


class AdminCreateUser(BaseModel):
    """Admin creates a user (no password). Invite link generated."""
    email: EmailStr
    name: str
    department: str
    role: str = "contributor"


class AdminUserRow(BaseModel):
    """User row for the admin Users page."""
    id: str
    email: str
    name: str
    department: str
    role: str
    is_active: bool
    status_label: str
    created_at: str | None = None

    model_config = {"from_attributes": True}


class InviteInfoResponse(BaseModel):
    """Public info shown on the invite page."""
    name: str
    email: str
    department: str
    role: str
    valid: bool
    message: str = ""


class SetPasswordRequest(BaseModel):
    """User sets password via invite token."""
    token: str
    password: str
