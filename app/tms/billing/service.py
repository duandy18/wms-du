# app/tms/billing/service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import (
    ReconcileCarrierBillCommand,
    ReconcileCarrierBillResult,
)
from .repository import (
    list_carrier_bill_items_for_reconcile,
    list_shipping_records_for_reconcile,
    update_shipping_record_reconcile_result,
)


def _to_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class CarrierBillReconcileService:
    WEIGHT_TOLERANCE_KG = Decimal("0.0005")
    COST_TOLERANCE = Decimal("0.01")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _resolve_reconcile_status(
        self,
        *,
        weight_diff_kg: Decimal | None,
        cost_diff: Decimal | None,
    ) -> str:
        weight_ok = (
            weight_diff_kg is None
            or abs(weight_diff_kg) <= self.WEIGHT_TOLERANCE_KG
        )
        cost_ok = cost_diff is None or abs(cost_diff) <= self.COST_TOLERANCE
        return "MATCHED" if weight_ok and cost_ok else "DIFF"

    async def reconcile(
        self,
        command: ReconcileCarrierBillCommand,
    ) -> ReconcileCarrierBillResult:
        carrier_code = command.carrier_code.strip()
        import_batch_no = command.import_batch_no.strip()

        bill_rows = await list_carrier_bill_items_for_reconcile(
            self.session,
            import_batch_no=import_batch_no,
            carrier_code=carrier_code,
        )
        bill_item_count = len(bill_rows)

        bill_map: dict[str, dict[str, Any]] = {}
        duplicate_tracking_nos: set[str] = set()

        for row in bill_rows:
            tracking_no = str(row.get("tracking_no") or "").strip()
            if not tracking_no:
                continue
            if tracking_no in bill_map:
                duplicate_tracking_nos.add(tracking_no)
                continue
            bill_map[tracking_no] = row

        for tracking_no in duplicate_tracking_nos:
            bill_map.pop(tracking_no, None)

        unique_tracking_nos = list(bill_map.keys())

        record_rows = await list_shipping_records_for_reconcile(
            self.session,
            carrier_code=carrier_code,
            tracking_nos=unique_tracking_nos,
        )
        record_map: dict[str, dict[str, Any]] = {
            str(r.get("tracking_no") or "").strip(): r
            for r in record_rows
            if str(r.get("tracking_no") or "").strip()
        }

        matched_count = 0
        diff_count = 0
        unmatched_count = 0
        updated_count = 0

        reconciled_at = datetime.now(timezone.utc)

        for tracking_no, bill_row in bill_map.items():
            record_row = record_map.get(tracking_no)
            if record_row is None:
                unmatched_count += 1
                continue

            billing_weight_kg = _to_decimal(bill_row.get("billing_weight_kg"))
            freight_amount = _to_decimal(bill_row.get("freight_amount"))
            surcharge_amount = _to_decimal(bill_row.get("surcharge_amount"))
            gross_weight_kg = _to_decimal(record_row.get("gross_weight_kg"))
            cost_estimated = _to_decimal(record_row.get("cost_estimated"))

            cost_real: Decimal | None = None
            if freight_amount is not None or surcharge_amount is not None:
                cost_real = (freight_amount or Decimal("0")) + (
                    surcharge_amount or Decimal("0")
                )

            weight_diff_kg: Decimal | None = None
            if billing_weight_kg is not None and gross_weight_kg is not None:
                weight_diff_kg = billing_weight_kg - gross_weight_kg

            cost_diff: Decimal | None = None
            if cost_real is not None and cost_estimated is not None:
                cost_diff = cost_real - cost_estimated

            reconcile_status = self._resolve_reconcile_status(
                weight_diff_kg=weight_diff_kg,
                cost_diff=cost_diff,
            )

            await update_shipping_record_reconcile_result(
                self.session,
                record_id=int(record_row["id"]),
                billing_weight_kg=billing_weight_kg,
                freight_amount=freight_amount,
                surcharge_amount=surcharge_amount,
                cost_real=cost_real,
                weight_diff_kg=weight_diff_kg,
                cost_diff=cost_diff,
                reconcile_status=reconcile_status,
                carrier_bill_item_id=int(bill_row["id"]),
                reconciled_at=reconciled_at,
            )
            updated_count += 1

            if reconcile_status == "MATCHED":
                matched_count += 1
            else:
                diff_count += 1

        await self.session.commit()

        return ReconcileCarrierBillResult(
            ok=True,
            carrier_code=carrier_code,
            import_batch_no=import_batch_no,
            bill_item_count=bill_item_count,
            matched_count=matched_count,
            diff_count=diff_count,
            unmatched_count=unmatched_count + len(duplicate_tracking_nos),
            updated_count=updated_count,
            duplicate_bill_tracking_count=len(duplicate_tracking_nos),
        )
