# app/pms/public/suppliers/contracts/supplier_basic.py
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class SupplierBasic(BaseModel):
    """
    PMS 对外最小供应商读模型。

    说明：
    - 这是跨域 public read surface
    - 只暴露其他模块稳定需要的最小读取字段
    - 不承载 owner contacts / 写入语义
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )

    id: int
    name: str
    code: Optional[str] = None
    active: bool
