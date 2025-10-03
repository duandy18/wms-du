from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter()


@router.post("/login", status_code=status.HTTP_200_OK)
def login(db: Session = Depends(get_db)):
    # 简化版的登录路由，暂时不包含具体逻辑
    return {"message": "Login route is working!"}
