# app/schemas/users.py


from pydantic import BaseModel, ConfigDict, EmailStr

# 前向引用，以处理循环依赖
from .role import RoleOut


class UserBase(BaseModel):
    full_name: str | None = None
    email: EmailStr
    is_active: bool | None = True
    is_superuser: bool | None = False


class UserCreate(UserBase):
    email: EmailStr
    password: str


class UserUpdate(UserBase):
    password: str | None = None


class UserOut(UserBase):
    id: str
    roles: list[RoleOut] = []

    model_config = ConfigDict(from_attributes=True)
