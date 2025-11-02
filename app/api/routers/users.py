# app/api/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.deps import get_db
from app.schemas.token import Token
from app.schemas.users import UserCreate, UserLogin, UserOut
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(prefix="/users", tags=["users"])

def get_user_service(db_session: Session = Depends(get_db)): return UserService(db_session)

@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, user_service: UserService = Depends(get_user_service)):
    try:
        return user_service.create_user(username=user_in.email, password=user_in.password, role_id=user_in.role_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.post("/login", response_model=Token)
def login(user_in: UserLogin, user_service: UserService = Depends(get_user_service)):
    user = user_service.authenticate_user(user_in.email, user_in.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    access_token = user_service.create_token_for_user(user)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("", response_model=list[UserOut])
def get_all_users(user_service: UserService = Depends(get_user_service),
                  current_user: dict = Depends(get_current_user)):
    try:
        user_service.check_permission(current_user, ["read_users"])
        return user_service.get_all_users()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
