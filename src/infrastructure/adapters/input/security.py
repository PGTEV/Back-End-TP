"""Autenticación del prototipo, compartida por los adaptadores HTTP."""
from secrets import compare_digest
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def reviewer_dependency(settings):
    bearer = HTTPBearer(auto_error=False)

    def reviewer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        token = settings.reviewer_token.get_secret_value()
        candidates = [(token, settings.reviewer_token_expires_at)] + [
            (item.token.get_secret_value(), item.expires_at) for item in settings.reviewer_tokens]
        if not any(len(value) >= 32 for value, _ in candidates) or not settings.reviewer_id.strip():
            raise HTTPException(503, detail={"codigo": "REVISOR_NO_CONFIGURADO",
                                "mensaje": "El acceso de evaluador no está configurado en el servidor."})
        now = datetime.now(timezone.utc)
        matched = False
        for value, expiry in candidates:
            same = credentials is not None and compare_digest(credentials.credentials.encode(), value.encode())
            matched |= bool(same and len(value) >= 32 and (expiry is None or expiry > now))
        if not matched:
            raise HTTPException(401, detail="Credencial de evaluador inválida.",
                                headers={"WWW-Authenticate": "Bearer"})
        return settings.reviewer_id

    return reviewer
