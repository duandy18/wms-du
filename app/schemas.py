# app/schemas.py

from pydantic import BaseModel, ConfigDict, EmailStr


# Common base: optional email field
class UserBase(BaseModel):
    username: str
    email: EmailStr | None = None

    # Pydantic v2: allow reading from ORM objects (replacement for v1 `orm_mode=True`)
    model_config = ConfigDict(from_attributes=True, extra="ignore")


# Create payload: username required, email optional
class UserCreate(UserBase):
    pass


# Update payload: both fields optional (partial update)
class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# Output model: includes id and optional email
class UserOut(UserBase):
    id: int
