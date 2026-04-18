# app/wms/scan/routers/scan_entrypoint.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.scan.services.scan_helpers import to_date_str
from app.wms.scan.contracts.scan import ScanRequest, ScanResponse
from app.wms.scan.services.scan_orchestrator_ingest import ingest as ingest_scan


def register(router: APIRouter) -> None:
    # ==========================
    # /scan（统一入口 → orchestrator）
    # ==========================

    @router.post("/scan", response_model=ScanResponse, status_code=status.HTTP_200_OK)
    async def scan_entrypoint(
        req: ScanRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ScanResponse:
        """
        v2 统一 /scan 入口：

        - 前端提交 ScanRequest（mode + item_id + qty + warehouse_id + 批次/日期 + ctx）
        - 由 scan_orchestrator.ingest 解析并路由到对应 handler（receive/pick/count）
        - 不再直接调用 InboundService.receive，也不再依赖 legacy 库位维度/ref/occurred_at

        Phase M-4 governance：
        - lot_code 为正名；batch_code 为兼容别名
        """
        result = await ingest_scan(req.model_dump(), session)

        # ★ item_id：优先 orchestrator，其次请求体
        item_id = result.get("item_id") or req.item_id

        item_uom_id = result.get("item_uom_id")
        ratio_to_base = result.get("ratio_to_base")

        # qty 继续作为输入单位数量回显
        qty = req.qty
        qty_base = result.get("qty_base")

        # 合同双轨：对外返回两者对齐；内部仍沿用 batch_code 作为 key
        lot_code = req.lot_code or req.batch_code
        batch_code = lot_code

        # enriched 字段（count / receive）
        warehouse_id = result.get("warehouse_id") or req.warehouse_id
        actual = result.get("actual")
        before = result.get("before")
        after = result.get("after")
        delta = result.get("delta")

        before_qty = result.get("before_qty") or before
        after_qty = result.get("after_qty") or after

        # 日期：优先 orchestrator，再回落到请求体，统一转为字符串
        raw_prod = result.get("production_date")
        if raw_prod is None:
            raw_prod = req.production_date
        prod = to_date_str(raw_prod)

        raw_exp = result.get("expiry_date")
        if raw_exp is None:
            raw_exp = req.expiry_date
        exp = to_date_str(raw_exp)

        return ScanResponse(
            ok=bool(result.get("ok", False)),
            committed=bool(result.get("committed", False)),
            scan_ref=result.get("scan_ref") or "",
            event_id=result.get("event_id"),
            source=result.get("source") or "scan_orchestrator",
            item_id=item_id,
            item_uom_id=item_uom_id,
            ratio_to_base=ratio_to_base,
            qty=qty,
            qty_base=qty_base,
            lot_code=lot_code,
            batch_code=batch_code,
            warehouse_id=warehouse_id,
            actual=actual,
            before=before,
            before_qty=before_qty,
            after=after,
            after_qty=after_qty,
            delta=delta,
            production_date=prod,
            expiry_date=exp,
            evidence=result.get("evidence") or [],
            errors=result.get("errors") or [],
        )
