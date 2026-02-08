# app/api/routers/platform_orders_ingest_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class PlatformOrderLineIn(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [
                {
                    "platform_sku_id": "PSKU-OK-1001",
                    "qty": 1,
                    "title": "示例商品A",
                    "spec": "默认",
                    "extras": {"note": "可选扩展字段"},
                }
            ]
        },
    )

    platform_sku_id: Optional[str] = Field(
        None, description="平台 SKU 标识（PSKU，可空；建议填系统生成/约定的编码）"
    )
    qty: int = Field(default=1, gt=0, description="数量（>0）")
    title: Optional[str] = Field(None, description="商品标题/名称（可选，用于治理线索展示）")
    spec: Optional[str] = Field(None, description="规格文本（可选，用于治理线索展示）")
    extras: Optional[Dict[str, Any]] = Field(None, description="行级扩展字段（可选）")


class PlatformOrderIngestIn(BaseModel):
    """
    平台订单接入（解码版）：
    - 外部输入（兼容）：platform + shop_id(str) + ext_order_no + lines(PSKU+qty)
    - 内部输入（推荐）：platform + store_id(int) + ext_order_no + lines(...)
    - 先写平台事实（platform_order_lines），再尝试解码落 orders

    ✅ 本次增强（Phase 3.x → 3.y 最小闭环）：
    - 支持输入收件地址（至少 province），解除 Route-C 履约阻塞
    - 字段名对齐 order_address：receiver_name/receiver_phone/province/city/district/detail/zipcode

    ⚠️ 注意：地址字段为「顶层字段」，不是 address:{...} 嵌套对象。
    """

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [
                # ✅ 最小可用：带 province（顶层字段）+ PSKU
                {
                    "platform": "DEMO",
                    "shop_id": "1",
                    "ext_order_no": "E2E-OK-0002",
                    "province": "广东省",
                    "lines": [
                        {
                            "platform_sku_id": "PSKU-OK-1001",
                            "qty": 1,
                            "title": "示例商品A",
                            "spec": "默认",
                        }
                    ],
                },
                # ✅ 兼容：内部治理用 store_id；可附带收件信息
                {
                    "platform": "DEMO",
                    "store_id": 915,
                    "ext_order_no": "E2E-OK-0003",
                    "receiver_name": "张三",
                    "receiver_phone": "13800000000",
                    "province": "广东省",
                    "city": "深圳市",
                    "district": "南山区",
                    "detail": "科技园某路 1 号",
                    "zipcode": "518000",
                    "lines": [
                        {
                            "platform_sku_id": "PSKU-OK-1001",
                            "qty": 2,
                            "title": "示例商品A",
                            "spec": "默认",
                        }
                    ],
                },
            ]
        },
    )

    platform: constr(min_length=1, max_length=32) = Field(
        ..., description="平台标识（如 DEMO/PDD/TIKTOK 等）"
    )

    # ✅ 新合同：内部治理用 store_id（stores.id）
    store_id: Optional[int] = Field(
        None, ge=1, description="内部店铺 ID（stores.id，推荐用于内部治理/重放）"
    )

    # ⚠️ 兼容：外部平台店铺标识（字符串）；若给了 store_id，可省略 shop_id
    shop_id: Optional[constr(min_length=1)] = Field(
        None, description="外部平台店铺标识（字符串；兼容输入）"
    )

    ext_order_no: constr(min_length=1) = Field(..., description="外部订单号（平台侧）")
    occurred_at: Optional[datetime] = Field(None, description="外部订单发生时间（可选）")

    buyer_name: Optional[str] = Field(None, description="买家姓名（可选）")
    buyer_phone: Optional[str] = Field(None, description="买家电话（可选）")

    # ✅ 收件信息（用于履约路由；最小可用只要求 province）
    receiver_name: Optional[str] = Field(
        None,
        description="收件人姓名（顶层字段；不要包在 address:{...} 里；可选）",
    )
    receiver_phone: Optional[str] = Field(
        None,
        description="收件人电话（顶层字段；不要包在 address:{...} 里；可选）",
    )
    province: Optional[str] = Field(
        None,
        description="收件省份（顶层字段；不要包在 address:{...} 里；最小闭环推荐必填）",
    )
    city: Optional[str] = Field(
        None, description="收件城市（顶层字段；不要包在 address:{...} 里；可选）"
    )
    district: Optional[str] = Field(
        None, description="收件区县（顶层字段；不要包在 address:{...} 里；可选）"
    )
    detail: Optional[str] = Field(
        None, description="收件详细地址（顶层字段；不要包在 address:{...} 里；可选）"
    )
    zipcode: Optional[str] = Field(
        None, description="邮编（顶层字段；不要包在 address:{...} 里；可选）"
    )

    lines: List[PlatformOrderLineIn] = Field(
        default_factory=list, description="订单行列表（至少一行）"
    )
    store_name: Optional[str] = Field(None, description="店铺名称（可选，展示用）")
    raw_payload: Optional[Dict[str, Any]] = Field(
        None, description="原始平台 payload（可选；调试/追溯用）"
    )


class PlatformOrderIngestOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str

    store_id: Optional[int] = None

    resolved: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved: List[Dict[str, Any]] = Field(default_factory=list)
    facts_written: int = 0

    # ✅ 解释增强：直接透出履约状态与阻塞原因，便于 PSKU 页面/治理页解释
    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None
