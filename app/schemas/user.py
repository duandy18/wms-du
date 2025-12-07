# app/schemas/user.py
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, constr


# -------- 输入模型 --------
class UserCreate(BaseModel):
    """创建用户入参"""

    username: constr(strip_whitespace=True, min_length=3, max_length=64)
    password: constr(min_length=6, max_length=128)
    role_id: int = Field(..., ge=1)

    # 可选字段：基础资料
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class UserLogin(BaseModel):
    """登录入参"""

    username: constr(strip_whitespace=True, min_length=3, max_length=64)
    password: constr(min_length=1)


# -------- 输出模型 --------
class UserOut(BaseModel):
    """对外返回的用户模型"""

    id: int
    username: str
    role_id: Optional[int] = None

    is_active: bool = True
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    # Pydantic v2 的 from_attributes = True（等价 orm_mode = True）
    model_config = ConfigDict(from_attributes=True)
