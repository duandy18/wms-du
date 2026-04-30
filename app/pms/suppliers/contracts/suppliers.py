# app/pms/suppliers/contracts/suppliers.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class SupplierContactOut(BaseModel):
    id: int
    supplier_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    wechat: Optional[str] = None
    role: str
    is_primary: bool
    active: bool


class SupplierOut(BaseModel):
    id: int
    name: str
    code: str
    website: Optional[str] = None
    active: bool
    contacts: List[SupplierContactOut]


class SupplierCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    website: Optional[str] = None
    active: bool = True


class SupplierUpdateIn(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    website: Optional[str] = None
    active: Optional[bool] = None


class SupplierContactCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)
    role: str = Field(default="other", max_length=32)
    is_primary: bool = False
    active: bool = True


class SupplierContactUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, max_length=32)
    is_primary: Optional[bool] = None
    active: Optional[bool] = None
