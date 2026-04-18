# app/wms/scan/routers/scan_entrypoint.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.scan.services.scan_helpers import to_date_str
from app.wms.scan.contracts.scan import ScanRequest, ScanResponse
from app.wms.scan.services.scan_orchestrator_ingest import ingest as ingest_scan


def register(router: APIRouter) -> None:
    @router.post("/scan", response_model=ScanResponse, status_code=status.HTTP_200_OK)
    async def scan_entrypoint(
        req: ScanRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ScanResponse:
        """
        /scan 已收口为 pick probe 工具层：

        - 仅接收 pick + probe=true
        - 仅负责条码→商品/包装识别
        - 不再承接 receive / count 主链
        """
        result = await ingest_scan(req.model_dump(), session)

        item_id = result.get("item_id") or req.item_id
        item_uom_id = result.get("item_uom_id")
        ratio_to_base = result.get("ratio_to_base")

        qty = req.qty
        qty_base = result.get("qty_base")

        lot_code = req.lot_code or req.batch_code
        batch_code = lot_code

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
            source=result.get("source") or "scan_pick_probe",
            item_id=item_id,
            item_uom_id=item_uom_id,
            ratio_to_base=ratio_to_base,
            qty=qty,
            qty_base=qty_base,
            lot_code=lot_code,
            batch_code=batch_code,
            production_date=prod,
            expiry_date=exp,
            evidence=result.get("evidence") or [],
            errors=result.get("errors") or [],
        )
