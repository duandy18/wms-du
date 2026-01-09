# app/services/pick_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class PickService:
    """
    v2 拣货（出库）Facade（location_id 已移除；FEFO 仅提示不刚性）：

    设计要点
    - 拣货即扣减：扫码确认后立刻扣减库存（原子 + 幂等由 StockService.adjust 保障）
    - 批次强制：扫码必须提供 batch_code；未提供即拒绝
    - 粒度统一：以 (item_id, warehouse_id, batch_code) 为唯一槽位
    - FEFO 柔性：不强制 FEFO，只要指定批次即可扣减；FEFO 风险通过快照/查询提示

    Phase N（订单驱动增强）：
    - 允许调用方传入 trace_id，用于将本次扣减挂到订单 trace 上；
    - trace_id 透传到 StockService.adjust → stock_ledger.trace_id；
    - 订单驱动的 HTTP 层可以从 orders.trace_id 获取该 trace_id 并传入。

    语义约束（非常重要）：
    - “扣减库存”只是动作；台账 reason 必须表达业务语义。
    - 默认：通用拣货使用 MovementType.PICK（当前映射为 ADJUSTMENT）。
    - 订单出库：调用方应显式传入 movement_type=MovementType.SHIP（落库为 SHIPMENT）。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def record_pick(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        qty: int,
        ref: str,
        occurred_at: datetime,
        batch_code: str,
        warehouse_id: int,
        trace_id: Optional[str] = None,  # ⭐ 新增：可选 trace_id（订单驱动时传入）
        start_ref_line: Optional[int] = None,
        task_line_id: Optional[int] = None,  # 预留：任务/拣货单整合
        movement_type: Union[str, MovementType] = MovementType.PICK,
    ) -> Dict[str, Any]:
        """
        人工拣货（扫码确认）→ 直接扣减 (item_id, warehouse_id, batch_code) 槽位上的库存。
        幂等键由台账唯一键保障：(warehouse_id, item_id, batch_code, reason, ref, ref_line)

        参数说明：
          - trace_id: 若为订单驱动拣货，可传入对应订单的 trace_id；
                      将透传给 StockService.adjust，最终写入 stock_ledger.trace_id，
                      便于 TraceService 统一聚合。
          - movement_type:
                      本次扣减应落入 stock_ledger.reason 的业务语义（MovementType 映射）。
                      默认 PICK；订单出库应传 SHIP（落库为 SHIPMENT）。
        """
        # —— 基础校验 ——
        if qty <= 0:
            raise ValueError("Qty must be > 0 for pick record.")
        if not batch_code or not str(batch_code).strip():
            raise ValueError("扫码拣货必须提供 batch_code。")
        if warehouse_id is None or int(warehouse_id) <= 0:
            raise ValueError("拣货必须明确 warehouse_id。")

        ref_line = int(start_ref_line or 1)

        # —— 核心原子操作：统一走 StockService.adjust（delta < 0 扣减） ——
        try:
            result = await self.stock_svc.adjust(
                session=session,
                item_id=item_id,
                delta=-int(qty),
                reason=movement_type,  # ✅ 由调用方决定落库 reason 语义
                ref=ref,
                ref_line=ref_line,
                occurred_at=occurred_at,
                batch_code=str(batch_code),
                warehouse_id=int(warehouse_id),
                trace_id=trace_id,  # ⭐ 将 trace_id 透传到 ledger
            )
        except ValueError as e:
            # 典型：库存不足 / 批次不存在等业务校验失败
            raise ValueError(f"拣货失败：{e}") from e
        except Exception as e:
            # 其他异常：继续抛出交由上层审计/处理
            raise e

        # —— 返回结果：与出库链路保持一致的最小契约 ——
        return {
            "picked": int(qty),
            "stock_after": result.get("after") if result else None,
            "batch_code": str(batch_code),
            "warehouse_id": int(warehouse_id),
            "ref": ref,
            "ref_line": ref_line,
            "status": "OK" if result and result.get("applied", True) else "IDEMPOTENT",
        }
