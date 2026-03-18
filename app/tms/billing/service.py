# app/tms/billing/service.py

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import (
    ReconcileCarrierBillCommand,
    ReconcileCarrierBillResult,
)

from .repository_items import list_carrier_bill_items_for_reconcile
from .repository_records import (
    list_shipping_records_for_reconcile,
    list_shipping_records_for_record_only,
)
from .repository_reconciliations import (
    upsert_shipping_record_reconciliation,
)


def _to_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _has_weight_diff(weight_diff_kg: Decimal | None) -> bool:
    return weight_diff_kg is not None and weight_diff_kg != Decimal("0")


def _has_cost_diff(cost_diff: Decimal | None) -> bool:
    return cost_diff is not None and cost_diff != Decimal("0")


def _derive_business_date_window(
    bill_rows: list[dict[str, Any]],
) -> tuple[date | None, date | None]:
    dates: list[date] = []
    for row in bill_rows:
        v = row.get("business_time")
        if isinstance(v, datetime):
            dates.append(v.date())
    if not dates:
        return None, None
    return min(dates), max(dates)


class CarrierBillReconcileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reconcile(
        self,
        command: ReconcileCarrierBillCommand,
    ) -> ReconcileCarrierBillResult:
        carrier_code = command.carrier_code.strip()

        bill_rows = await list_carrier_bill_items_for_reconcile(
            self.session,
            carrier_code=carrier_code,
        )
        bill_item_count = len(bill_rows)

        bill_map: dict[str, dict[str, Any]] = {}
        duplicate_tracking_nos: set[str] = set()
        all_bill_tracking_nos: set[str] = set()

        for row in bill_rows:
            tracking_no = str(row.get("tracking_no") or "").strip()
            if not tracking_no:
                continue
            all_bill_tracking_nos.add(tracking_no)
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

        record_map = {
            str(r.get("tracking_no") or "").strip(): r
            for r in record_rows
            if str(r.get("tracking_no") or "").strip()
        }

        diff_count = 0
        bill_only_count = 0
        record_only_count = 0
        updated_count = 0

        for tracking_no, bill_row in bill_map.items():
            record_row = record_map.get(tracking_no)

            if record_row is None:
                await upsert_shipping_record_reconciliation(
                    self.session,
                    status="bill_only",
                    carrier_code=carrier_code,
                    tracking_no=tracking_no,
                    shipping_record_id=None,
                    carrier_bill_item_id=int(bill_row["id"]),
                    weight_diff_kg=None,
                    cost_diff=None,
                    adjust_amount=None,
                )
                bill_only_count += 1
                updated_count += 1
                continue

            billing_weight_kg = _to_decimal(bill_row.get("billing_weight_kg"))
            freight_amount = _to_decimal(bill_row.get("freight_amount"))
            surcharge_amount = _to_decimal(bill_row.get("surcharge_amount"))
            gross_weight_kg = _to_decimal(record_row.get("gross_weight_kg"))
            cost_estimated = _to_decimal(record_row.get("cost_estimated"))

            bill_cost_real = (
                (freight_amount or Decimal("0")) + (surcharge_amount or Decimal("0"))
                if freight_amount is not None or surcharge_amount is not None
                else None
            )

            weight_diff_kg = (
                billing_weight_kg - gross_weight_kg
                if billing_weight_kg is not None and gross_weight_kg is not None
                else None
            )

            cost_diff = (
                bill_cost_real - cost_estimated
                if bill_cost_real is not None and cost_estimated is not None
                else None
            )

            has_diff = _has_weight_diff(weight_diff_kg) or _has_cost_diff(cost_diff)

            if has_diff:
                await upsert_shipping_record_reconciliation(
                    self.session,
                    status="diff",
                    carrier_code=carrier_code,
                    tracking_no=tracking_no,
                    shipping_record_id=int(record_row["id"]),
                    carrier_bill_item_id=int(bill_row["id"]),
                    weight_diff_kg=weight_diff_kg,
                    cost_diff=cost_diff,
                    adjust_amount=None,
                )
                diff_count += 1
                updated_count += 1

        from_date, to_date = _derive_business_date_window(bill_rows)

        record_only_rows = await list_shipping_records_for_record_only(
            self.session,
            carrier_code=carrier_code,
            bill_tracking_nos=sorted(all_bill_tracking_nos),
            from_date=from_date,
            to_date=to_date,
        )

        for record_row in record_only_rows:
            tracking_no = str(record_row.get("tracking_no") or "").strip()
            if not tracking_no:
                continue

                # no-op

            await upsert_shipping_record_reconciliation(
                self.session,
                status="record_only",
                carrier_code=carrier_code,
                tracking_no=tracking_no,
                shipping_record_id=int(record_row["id"]),
                carrier_bill_item_id=None,
                weight_diff_kg=None,
                cost_diff=None,
                adjust_amount=None,
            )
            record_only_count += 1
            updated_count += 1

        await self.session.commit()

        return ReconcileCarrierBillResult(
            ok=True,
            carrier_code=carrier_code,
            bill_item_count=bill_item_count,
            diff_count=diff_count,
            bill_only_count=bill_only_count,
            record_only_count=record_only_count,
            updated_count=updated_count,
            duplicate_bill_tracking_count=len(duplicate_tracking_nos),
        )
