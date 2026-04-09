# app/pms/public/items/contracts/item_query.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ItemReadQuery(BaseModel):
    """
    PMS public read 查询参数。

    说明：
    - 这是后端域间读取入参，不是 HTTP router 的直接替身
    - 保持和 /items 的主读语义一致，但不携带兼容包袱
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    supplier_id: Annotated[int | None, Field(default=None, ge=1)] = None
    enabled: bool | None = None
    q: str | None = None
    limit: Annotated[int | None, Field(default=None, ge=1, le=200)] = None

    @field_validator("q", mode="before")
    @classmethod
    def _trim_q(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v
