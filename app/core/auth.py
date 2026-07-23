from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException

from app.core.security import decode_access_token


async def get_current_user_id(authorization: str | None = Header(default=None)) -> UUID:
    if not authorization:
        raise HTTPException(status_code=401, detail="No autenticado. Falta el header Authorization.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Header Authorization inválido. Se espera el formato 'Bearer <token>'.",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    subject = payload.get("sub")
    try:
        return UUID(subject)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido.")
