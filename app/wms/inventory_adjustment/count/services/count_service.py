from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inventory_adjustment.count.contracts.count import CountRequest, CountResponse
from app.wms.inventory_adjustment.count.repos.count_repo import CountRepo
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)
from app.wms.shared.services.lot_code_contract import validate_lot_code_contract
from app.wms.stock.services.stock_service import StockService


class CountService:
    def __init__(
        self,
        *,
        repo: CountRepo | None = None,
        stock: StockService | None = None,
    ) -> None:
        self.repo = repo or CountRepo()
        self.stock = stock or StockService()

    async def submit(
        self,
        session: AsyncSession,
        *,
        req: CountRequest,
    ) -> CountResponse:
        await ensure_warehouse_not_frozen(
            session,
            warehouse_id=int(req.warehouse_id),
        )

        expiry_policy_text = await self.repo.get_item_expiry_policy_text(
            session,
            item_id=int(req.item_id),
        )
        requires_batch = expiry_policy_text.upper() == "REQUIRED"

        lot_code_raw = req.lot_code or req.batch_code
        lot_code = validate_lot_code_contract(
            requires_batch=requires_batch,
            lot_code=lot_code_raw,
        )

        if requires_batch and req.production_date is None and req.expiry_date is None:
            raise ValueError(
                "expiry-policy REQUIRED item requires production_date or expiry_date (at least one)."
            )

        current = await self.repo.get_current_qty_by_lot_code(
            session,
            item_id=int(req.item_id),
            warehouse_id=int(req.warehouse_id),
            lot_code=lot_code,
        )
        delta = int(req.qty) - int(current)

        meta: dict[str, object] = {
            "sub_reason": "COUNT_ADJUST" if delta != 0 else "COUNT_CONFIRM",
        }
        if delta == 0:
            meta["allow_zero_delta_ledger"] = True

        res = await self.stock.adjust(
            session=session,
            item_id=req.item_id,
            warehouse_id=req.warehouse_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref=req.ref,
            ref_line=1,
            occurred_at=req.occurred_at,
            batch_code=lot_code,
            production_date=req.production_date,
            expiry_date=req.expiry_date,
            meta=meta,
        )

        after_qty = int(res.get("after", req.qty))

        return CountResponse(
            ok=True,
            after=after_qty,
            ref=req.ref,
            item_id=req.item_id,
            warehouse_id=req.warehouse_id,
            lot_code=lot_code,
            batch_code=lot_code,
            occurred_at=req.occurred_at,
        )
