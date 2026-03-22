"""Auth router — /v1/auth/tokens (Supabase Auth proxy)"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..core.responses import RefreshTokenResponse, SuccessResponse, TokenResponse, UserInfoResponse
from ..dependencies import get_user_service
from ..rate_limit import limiter
from ..services.user import UserService

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class SignupRequest(BaseModel):
    email: str
    password: str


@router.post("/tokens", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Login — create tokens via Supabase Auth."""
    result = await user_svc.login(body.email, body.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post("/tokens/signup", response_model=TokenResponse)
@limiter.limit("10/minute")
async def signup(
    request: Request,
    body: SignupRequest,
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Register a new user via Supabase Auth."""
    result = await user_svc.signup(body.email, body.password)
    if not result:
        raise HTTPException(status_code=400, detail="Signup failed")
    return result


@router.get("/me", response_model=UserInfoResponse)
async def me(
    request: Request,
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Get current user info from Supabase Auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = auth_header.removeprefix("Bearer ")
    info = await user_svc.get_user_info(token)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return info


@router.post("/tokens/refresh", response_model=RefreshTokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Refresh access token via Supabase Auth."""
    result = await user_svc.refresh_token(body.refreshToken)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return result


@router.delete("/tokens", response_model=SuccessResponse)
@limiter.limit("10/minute")
async def logout(
    request: Request,
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Logout — invalidate session via Supabase Auth using access token."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        await user_svc.logout(token)
    return {"success": True}
