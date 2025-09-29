# app/routers/diag.py
from fastapi import APIRouter, Depends
from app.authz import require_perms

router = APIRouter(prefix="/diag", tags=["diag"])

@router.get("/secure")
def secured(user = Depends(require_perms("purchase:view"))):
    return {"ok": True, "user": getattr(user, "username", None)}
