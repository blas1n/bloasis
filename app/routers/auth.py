"""Auth router — /v1/auth/tokens"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..dependencies import get_current_user, get_user_service
from ..rate_limit import limiter
from ..services.user import UserService

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


@router.post("/tokens")
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    user_svc: UserService = Depends(get_user_service),
):
    """Login — create tokens."""
    result = await user_svc.login(body.email, body.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.get("/me")
async def me(
    user_id: uuid.UUID = Depends(get_current_user),
    user_svc: UserService = Depends(get_user_service),
):
    """Get current user info from validated JWT."""
    info = await user_svc.get_user_info(user_id)
    if not info:
        raise HTTPException(status_code=404, detail="User not found")
    return info


@router.post("/tokens/refresh")
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    user_svc: UserService = Depends(get_user_service),
):
    """Refresh access token."""
    result = await user_svc.refresh_token(body.refreshToken)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return result


@router.delete("/tokens")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    body: RefreshRequest,
    user_svc: UserService = Depends(get_user_service),
):
    """Logout — invalidate tokens."""
    await user_svc.logout(body.refreshToken)
    return {"success": True}
