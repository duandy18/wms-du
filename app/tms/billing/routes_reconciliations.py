# app/tms/billing/routes_reconciliations.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts import (
    ApproveShippingBillReconciliationIn,
    ApproveShippingBillReconciliationOut,
    ShippingBillReconciliationHistoriesResponse,
    ShippingBillReconciliationHistoryRowOut,
    ShippingBillReconciliationsResponse,
    ShippingBillReconciliationRowOut,
)
from .repository_reconciliation_history import (
    insert_shipping_bill_reconciliation_history,
    list_shipping_bill_reconciliation_histories,
)
from .repository_reconciliations import (
    approve_shipping_record_reconciliation,
    delete_shipping_record_reconciliation_by_id,
    get_shipping_record_reconciliation_by_id,
    list_shipping_bill_reconciliations,
)


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float(v)  # type: ignore[arg-type]


def register(router: APIRouter) -> None:
    @router.get(
        "/reconciliations",
        response_model=ShippingBillReconciliationsResponse,
    )
    async def get_shipping_bill_reconciliations(
        carrier_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingBillReconciliationsResponse:
        normalized_status = None
        if isinstance(status, str) and status.strip():
            if status.strip() not in {"diff", "bill_only"}:
                raise HTTPException(status_code=422, detail="status 仅支持 diff 或 bill_only。")
            normalized_status = status.strip()

        total, rows = await list_shipping_bill_reconciliations(
            session,
            carrier_code=(
                carrier_code.strip()
                if isinstance(carrier_code, str) and carrier_code.strip()
                else None
            ),
            tracking_no=(
                tracking_no.strip()
                if isinstance(tracking_no, str) and tracking_no.strip()
                else None
            ),
            status=normalized_status,
            limit=limit,
            offset=offset,
        )

        return ShippingBillReconciliationsResponse(
            ok=True,
            rows=[
                ShippingBillReconciliationRowOut(
                    reconciliation_id=int(r["reconciliation_id"]),
                    status=str(r["status"]),
                    carrier_code=str(r["carrier_code"]),
                    tracking_no=str(r["tracking_no"]),
                    shipping_record_id=(
                        int(r["shipping_record_id"])
                        if r.get("shipping_record_id") is not None
                        else None
                    ),
                    carrier_bill_item_id=int(r["carrier_bill_item_id"]),
                    weight_diff_kg=_to_float(r.get("weight_diff_kg")),
                    cost_diff=_to_float(r.get("cost_diff")),
                    adjust_amount=_to_float(r.get("adjust_amount")),
                    approved_reason_code=r.get("approved_reason_code"),
                    approved_reason_text=r.get("approved_reason_text"),
                    approved_at=r.get("approved_at"),
                    created_at=r["created_at"],
                )
                for r in rows
            ],
            total=total,
        )

    @router.get(
        "/reconciliation-histories",
        response_model=ShippingBillReconciliationHistoriesResponse,
    )
    async def get_shipping_bill_reconciliation_histories(
        carrier_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        result_status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingBillReconciliationHistoriesResponse:
        normalized_result_status = None
        if isinstance(result_status, str) and result_status.strip():
            if result_status.strip() not in {"matched", "approved_bill_only", "resolved"}:
                raise HTTPException(
                    status_code=422,
                    detail="result_status 仅支持 matched、approved_bill_only 或 resolved。",
                )
            normalized_result_status = result_status.strip()

        total, rows = await list_shipping_bill_reconciliation_histories(
            session,
            carrier_code=(
                carrier_code.strip()
                if isinstance(carrier_code, str) and carrier_code.strip()
                else None
            ),
            tracking_no=(
                tracking_no.strip()
                if isinstance(tracking_no, str) and tracking_no.strip()
                else None
            ),
            result_status=normalized_result_status,
            limit=limit,
            offset=offset,
        )

        return ShippingBillReconciliationHistoriesResponse(
            ok=True,
            rows=[
                ShippingBillReconciliationHistoryRowOut(
                    id=int(r["id"]),
                    carrier_bill_item_id=int(r["carrier_bill_item_id"]),
                    shipping_record_id=(
                        int(r["shipping_record_id"])
                        if r.get("shipping_record_id") is not None
                        else None
                    ),
                    carrier_code=str(r["carrier_code"]),
                    tracking_no=str(r["tracking_no"]),
                    result_status=str(r["result_status"]),
                    approved_reason_code=str(r["approved_reason_code"]),
                    weight_diff_kg=_to_float(r.get("weight_diff_kg")),
                    cost_diff=_to_float(r.get("cost_diff")),
                    adjust_amount=_to_float(r.get("adjust_amount")),
                    approved_reason_text=r.get("approved_reason_text"),
                    archived_at=r["archived_at"],
                )
                for r in rows
            ],
            total=total,
        )

    @router.post(
        "/reconciliations/{reconciliation_id}/approve",
        response_model=ApproveShippingBillReconciliationOut,
    )
    async def approve_reconciliation(
        reconciliation_id: int,
        payload: ApproveShippingBillReconciliationIn,
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ApproveShippingBillReconciliationOut:
        approved_reason_text = (
            payload.approved_reason_text.strip()
            if isinstance(payload.approved_reason_text, str) and payload.approved_reason_text.strip()
            else None
        )
        adjust_amount = payload.adjust_amount if payload.adjust_amount is not None else 0

        reconciliation_row = await get_shipping_record_reconciliation_by_id(
            session,
            reconciliation_id=reconciliation_id,
        )
        if reconciliation_row is None:
            raise HTTPException(status_code=404, detail="对账差异记录不存在。")

        current_status = str(reconciliation_row["status"])
        expected_reason_code = (
            "approved_bill_only"
            if current_status == "bill_only"
            else "resolved"
        )

        if payload.approved_reason_code != expected_reason_code:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"当前状态 {current_status} 只能确认为 {expected_reason_code}，"
                    f"不能写为 {payload.approved_reason_code}。"
                ),
            )

        row = await approve_shipping_record_reconciliation(
            session,
            reconciliation_id=reconciliation_id,
            approved_reason_code=payload.approved_reason_code,
            adjust_amount=adjust_amount,
            approved_reason_text=approved_reason_text,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="对账差异记录不存在。")

        await insert_shipping_bill_reconciliation_history(
            session,
            carrier_bill_item_id=int(row["carrier_bill_item_id"]),
            shipping_record_id=(
                int(row["shipping_record_id"])
                if row.get("shipping_record_id") is not None
                else None
            ),
            carrier_code=str(row["carrier_code"]),
            tracking_no=str(row["tracking_no"]),
            result_status=str(row["approved_reason_code"]),
            weight_diff_kg=row.get("weight_diff_kg"),
            cost_diff=row.get("cost_diff"),
            adjust_amount=row.get("adjust_amount"),
            approved_reason_code=str(row["approved_reason_code"]),
            approved_reason_text=row.get("approved_reason_text"),
        )
        await delete_shipping_record_reconciliation_by_id(
            session,
            reconciliation_id=reconciliation_id,
        )
        await session.commit()

        return ApproveShippingBillReconciliationOut(
            ok=True,
            reconciliation_id=reconciliation_id,
            history_result_status=str(row["approved_reason_code"]),
        )
