# app/schemas/user.py
from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, constr


# -------- 输入模型 --------
class UserCreate(BaseModel):
    """创建用户入参"""
    username: constr(strip_whitespace=True, min_length=3, max_length=64)
    password: constr(min_length=6, max_length=128)
    role_id: int = Field(..., ge=1)


class UserLogin(BaseModel):
    """登录入参"""
    username: constr(strip_whitespace=True, min_length=3, max_length=64)
    password: constr(min_length=1)


# -------- 输出模型 --------
class UserOut(BaseModel):
    """对外返回的用户模型"""
    id: int
    username: str
    role_id: int

    # Pydantic v2 用 ConfigDict；等价于 v1 的 orm_mode = True
    model_config = ConfigDict(from_attributes=True)
