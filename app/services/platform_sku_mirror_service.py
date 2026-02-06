# app/services/platform_sku_mirror_service.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class PlatformSkuMirrorService:
    """
    ✅ 平台同步（未来）唯一写入口：platform_sku_mirror

    工程约束（刻意写在这里，防止后人越界）：
    - 只允许写 mirror（UPSERT by (platform, shop_id, platform_sku_id)）
    - 允许覆盖字段：
        sku_name / spec / raw_payload / source / observed_at
    - 严禁在此处改写：
        platform_sku_bindings / FSKU / Item
      （这些属于业务映射与主数据域）
    """

    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        *,
        platform: str,
        shop_id: int,
        platform_sku_id: str,
        sku_name: Optional[str],
        spec: Optional[str],
        raw_payload: Optional[dict[str, Any]],
        source: str,
        observed_at: datetime,
    ) -> None:
        """
        UPSERT mirror 事实快照。

        说明：
        - raw_payload 统一使用 json.dumps → (:raw_payload)::jsonb
        - 不做任何业务推导、不触碰 binding
        """
        self.db.execute(
            text(
                """
                insert into platform_sku_mirror(
                  platform, shop_id, platform_sku_id,
                  sku_name, spec, raw_payload, source, observed_at,
                  created_at, updated_at
                ) values (
                  :platform, :shop_id, :platform_sku_id,
                  :sku_name, :spec, (:raw_payload)::jsonb, :source, :observed_at,
                  now(), now()
                )
                on conflict (platform, shop_id, platform_sku_id)
                do update set
                  sku_name     = excluded.sku_name,
                  spec         = excluded.spec,
                  raw_payload  = excluded.raw_payload,
                  source       = excluded.source,
                  observed_at  = excluded.observed_at,
                  updated_at   = now();
                """
            ),
            {
                "platform": platform,
                "shop_id": shop_id,
                "platform_sku_id": platform_sku_id,
                "sku_name": sku_name,
                "spec": spec,
                "raw_payload": (
                    None
                    if raw_payload is None
                    else json.dumps(raw_payload, ensure_ascii=False)
                ),
                "source": source,
                "observed_at": observed_at,
            },
        )
