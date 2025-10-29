# app/schemas/snapshot_api.py
from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 模型直接序列化
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名/字段名互填（便于未来加 alias）
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 首页库存快照（聚合） =========
class TopLocation(_Base):
    location_id: Annotated[int, Field(ge=1, description="库位ID")]
    qty: Annotated[int, Field(ge=0, description="该库位上的数量")]

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"location_id": 101, "qty": 36}}
    }


class InventoryItem(_Base):
    item_id: Annotated[int, Field(ge=1, description="商品ID")]
    name: Annotated[str, Field(min_length=1, max_length=128, description="商品名称")]
    spec: Annotated[str | None, Field(default=None, max_length=128, description="规格（可选）")] = None
    total_qty: Annotated[int, Field(ge=0, description="总库存数量")]
    top2_locations: list[TopLocation]
    # NOTE: 升级为 date | None，Pydantic 会自动从 ISO 字符串解析，兼容现有输出
    earliest_expiry: date | None = Field(
        default=None,
        description="最早到期日；None 表示无到期或无批次信息",
    )
    near_expiry: bool

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_id": 777,
                "name": "顽皮双拼猫粮 1.5kg",
                "spec": "鸡肉+牛肉",
                "total_qty": 150,
                "top2_locations": [{"location_id": 101, "qty": 36}, {"location_id": 102, "qty": 24}],
                "earliest_expiry": "2026-04-01",
                "near_expiry": False,
            }
        }
    }


class InventorySnapshotResponse(_Base):
    items: list[InventoryItem]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "item_id": 777,
                        "name": "顽皮双拼猫粮 1.5kg",
                        "spec": "鸡肉+牛肉",
                        "total_qty": 150,
                        "top2_locations": [{"location_id": 101, "qty": 36}, {"location_id": 102, "qty": 24}],
                        "earliest_expiry": "2026-04-01",
                        "near_expiry": False,
                    }
                ]
            }
        }
    }


__all__ = ["TopLocation", "InventoryItem", "InventorySnapshotResponse"]
