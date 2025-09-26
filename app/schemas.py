# app/schemas.py

from pydantic import BaseModel, ConfigDict, EmailStr


# 公用基类: 提供可选的 email 字段
class UserBase(BaseModel):
    username: str
    email: EmailStr | None = None

    # Pydantic v2: 允许从 ORM 对象读取属性 (替代 v1 的 orm_mode = True)
    model_config = ConfigDict(from_attributes=True, extra="ignore")


# 创建入参: username 必填, email 可选
class UserCreate(UserBase):
    pass


# 更新入参: 两个字段都可选 (部分更新)
class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# 出参: 带 id, 以及可选 email
class UserOut(UserBase):
    id: int
