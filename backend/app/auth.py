from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.settings import settings


Role = Literal["producer", "consumer", "admin"]


@dataclass(frozen=True)
class Principal:
    sub: str
    role: Role


security = HTTPBearer(auto_error=False)


def issue_token(*, sub: str, role: Role) -> str:
    now = int(time.time())
    payload = {
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "exp": now + settings.auth_jwt_ttl_seconds,
        "sub": sub,
        "role": role,
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


def get_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(security)],
) -> Principal:
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    claims = _decode_token(creds.credentials)
    role = claims.get("role")
    sub = claims.get("sub")
    if role not in ("producer", "consumer", "admin") or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Invalid token claims")
    return Principal(sub=sub, role=role)  # type: ignore[arg-type]


def require_roles(*roles: Role):
    def _dep(p: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if p.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return p

    return _dep

