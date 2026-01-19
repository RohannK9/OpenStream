from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from app.auth import issue_token
from app.models import TokenRequest, TokenResponse


router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def mint_token(req: TokenRequest) -> TokenResponse:
    """
    Dev-friendly token minting endpoint.

    In production you would integrate with your IdP (OIDC) or a proper API-key store.
    Here we guard minting with a shared admin secret for local testing.
    """
    admin_secret = os.environ.get("AUTH_ADMIN_SECRET", "dev-admin-secret")
    if req.admin_secret != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    token = issue_token(sub=req.sub, role=req.role)
    return TokenResponse(token=token)

