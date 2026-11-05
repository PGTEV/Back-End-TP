"""Autenticación del prototipo, compartida por los adaptadores HTTP."""
from secrets import compare_digest
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def reviewer_dependency(settings):
    bearer = HTTPBearer(auto_error=False)

    def reviewer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        token = settings.reviewer_token.get_secret_value()
        if len(token) < 32 or not settings.reviewer_id.strip():
            raise HTTPException(503, detail={"codigo": "REVISOR_NO_CONFIGURADO",
                                "mensaje": "El acceso de evaluador no está configurado en el servidor."})
        if credentials is None or not compare_digest(credentials.credentials.encode(), token.encode()):
            raise HTTPException(401, detail="Credencial de evaluador inválida.",
                                headers={"WWW-Authenticate": "Bearer"})
        return settings.reviewer_id

    return reviewer
