# app/api/routers/diag.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db_session

router = APIRouter(prefix="/diag", tags=["diag"])


@router.get("/health")
def health(db: Session = Depends(get_db_session)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}
    except Exception:
        return {"ok": False, "db": "down"}
