# app/services/ship_service.py
from __future__ import annotations

from math import ceil
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter


class ShipService:
    """
    发运相关服务：

    1) commit()     : 记录一次发运事件（不做库存扣减）
    2) calc_quotes(): 基于 shipping_providers 的定价模型计算费用矩阵
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # 1. 发运审计事件（以前已有）
    # ------------------------------------------------------------------ #
    async def commit(
        self,
        *,
        ref: str,
        platform: str,
        shop_id: str,
        trace_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        记录一次发运事件（发货成功）。

        参数：
          - ref:      业务引用（订单 / 出库单等）
          - platform: 平台标识（如 PDD）
          - shop_id:  店铺 ID（字符串）
          - trace_id: 链路 ID（可选）
          - meta:     额外元数据（可选）

        返回：
          {
            "ok": True,
            "ref": ref,
            "trace_id": trace_id,
          }
        """
        plat = (platform or "").upper()

        payload: Dict[str, Any] = {
            "platform": plat,
            "shop_id": shop_id,
        }
        if meta:
            payload.update(meta)

        await AuditEventWriter.write(
            self.session,
            flow="OUTBOUND",
            event="SHIP_COMMIT",
            ref=ref,
            trace_id=trace_id,
            meta=payload,
            auto_commit=False,  # 由上层控制事务
        )

        return {"ok": True, "ref": ref, "trace_id": trace_id}

    # ------------------------------------------------------------------ #
    # 2. 运费计算（by_weight 模型 + packaging_factor）
    # ------------------------------------------------------------------ #

    async def calc_quotes(
        self,
        *,
        weight_kg: float,
        province: Optional[str] = None,
        city: Optional[str] = None,
        district: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        基于 shipping_providers 表中 active 的记录，计算费用矩阵。

        定价模型（pricing_model）约定：

        {
          "type": "by_weight",
          "base_weight": 1.0,
          "base_cost": 3.5,
          "extra_unit": 1.0,
          "extra_cost": 1.2,
          "packaging_factor": 1.05   # 可选，默认 1.0
        }

        区域覆盖（region_rules）约定：

        {
          "广东省": { "base_cost": 3.2 },
          "新疆维吾尔自治区": { "base_cost": 15.0 }
        }
        """
        if weight_kg <= 0:
            raise ValueError("weight_kg must be > 0")

        sql = text(
            """
            SELECT id, name, code, active, priority, pricing_model, region_rules
            FROM shipping_providers
            WHERE active = TRUE
            ORDER BY priority ASC, id ASC
            """
        )
        result = await self.session.execute(sql)
        rows = result.mappings().all()

        quotes: List[Dict[str, Any]] = []
        for row in rows:
            code = (row.get("code") or "").strip()
            name = row.get("name") or code or f"SP-{row['id']}"
            pricing_model = row.get("pricing_model") or {}
            region_rules = row.get("region_rules") or {}

            cost, formula = self._calc_cost_by_weight(
                weight_kg=weight_kg,
                province=province,
                pricing_model=pricing_model,
                region_rules=region_rules,
            )
            if cost is None:
                # 没有有效模型，跳过
                continue

            quotes.append(
                {
                    "carrier": code or f"ID{row['id']}",
                    "name": name,
                    "est_cost": round(float(cost), 2),
                    "eta": None,  # 未来可按 provider 配置
                    "formula": formula,
                }
            )

        # 推荐策略：费用最低者；若有多家平价，则按 priority / id
        recommended: Optional[str] = None
        if quotes:
            best = min(quotes, key=lambda q: q["est_cost"])
            recommended = best["carrier"]

        dest_parts = [p for p in [province, city, district] if p]
        dest_str = " ".join(dest_parts) if dest_parts else None

        return {
            "ok": True,
            "weight_kg": weight_kg,
            "dest": dest_str,
            "quotes": quotes,
            "recommended": recommended,
        }

    @staticmethod
    def _calc_cost_by_weight(
        *,
        weight_kg: float,
        province: Optional[str],
        pricing_model: Dict[str, Any],
        region_rules: Dict[str, Any],
    ) -> tuple[Optional[float], str]:
        """
        简单 by_weight 模型 + packaging_factor：

        effective_weight = weight_kg * packaging_factor
        cost = base_cost + ceil(max(0, effective_weight - base_weight) / extra_unit) * extra_cost
        """
        if not pricing_model:
            return None, "no_pricing_model"

        model_type = (pricing_model.get("type") or "by_weight").lower()
        if model_type != "by_weight":
            # 目前只支持 by_weight，其他类型待扩展
            return None, f"unsupported_type:{model_type}"

        base_weight = float(pricing_model.get("base_weight") or 1.0)
        base_cost = float(pricing_model.get("base_cost") or 0.0)
        extra_unit = float(pricing_model.get("extra_unit") or 1.0)
        extra_cost = float(pricing_model.get("extra_cost") or 0.0)
        packaging_factor = float(pricing_model.get("packaging_factor") or 1.0)

        # 区域覆盖：按省份覆盖 base_cost
        if province and isinstance(region_rules, dict):
            region_cfg = region_rules.get(province)
            if isinstance(region_cfg, dict) and "base_cost" in region_cfg:
                base_cost = float(region_cfg["base_cost"])

        if extra_unit <= 0:
            extra_unit = 1.0
        if packaging_factor <= 0:
            packaging_factor = 1.0

        effective_weight = weight_kg * packaging_factor

        extra_weight = max(0.0, effective_weight - base_weight)
        extra_units = ceil(extra_weight / extra_unit)
        cost = base_cost + extra_units * extra_cost

        formula = (
            f"base_cost={base_cost} + ceil(max(0,{effective_weight:.3f}-{base_weight})/"
            f"{extra_unit})*{extra_cost} => {cost} "
            f"(raw_weight={weight_kg:.3f}, pack_factor={packaging_factor})"
        )
        return cost, formula
