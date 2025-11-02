# app/api/routers/user.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.user import UserCreate, UserLogin, UserOut
from app.schemas.token import Token
from app.services.user_service import UserService, AuthorizationError

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserOut)
def register_user(user_in: UserCreate, session: Session = Depends(get_session)):
    """
    注册新用户
    """
    svc = UserService(session)
    user = svc.create_user(user_in)
    return user


@router.post("/login", response_model=Token)
def login_user(user_in: UserLogin, session: Session = Depends(get_session)):
    """
    用户登录，返回 JWT token
    """
    svc = UserService(session)
    try:
        token = svc.authenticate_user(user_in.username, user_in.password)
        return {"access_token": token, "token_type": "bearer"}
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )


@router.get("/", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session)):
    """
    获取所有用户
    """
    svc = UserService(session)
    return svc.get_all_users()
