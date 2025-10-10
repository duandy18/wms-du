# app/api/endpoints/users.py


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db
from app.schemas.token import Token

# 导入 Pydantic 模型
from app.schemas.users import UserCreate, UserLogin, UserOut
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数，用于获取服务实例
def get_user_service(db_session: Session = Depends(get_db)):
    return UserService(db_session)


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, user_service: UserService = Depends(get_user_service)):
    """
    创建一个新的用户。
    """
    # 逻辑已移至服务层
    try:
        return user_service.create_user(
            username=user_in.email,
            password=user_in.password,
            role_id=user_in.role_id,  # 假设 UserCreate 包含了 role_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, user_service: UserService = Depends(get_user_service)):
    """
    用户登录并获取访问令牌。
    """
    user = user_service.authenticate_user(user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = user_service.create_token_for_user(user)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/", response_model=list[UserOut])
def get_all_users(
    user_service: UserService = Depends(get_user_service),
    # 假设需要管理员权限才能查看所有用户
    current_user: dict = Depends(get_current_user),
):
    """
    获取所有用户的列表。
    """
    try:
        user_service.check_permission(current_user, ["read_users"])
        return user_service.get_all_users()  # 假设服务层有此方法
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
