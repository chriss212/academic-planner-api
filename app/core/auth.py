from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException

from app.core.security import decode_access_token

TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_current_user_id(authorization: str | None = Header(default=None)) -> UUID:
    if not authorization:
        return TEMP_USER_ID

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return TEMP_USER_ID

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    subject = payload.get("sub")
    try:
        return UUID(subject)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido.")
