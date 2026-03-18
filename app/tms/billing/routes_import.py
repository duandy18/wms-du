# app/tms/billing/routes_import.py

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts import (
    CarrierBillImportResult,
    CarrierBillImportRowError,
    ImportCarrierBillCommand,
)
from .importer import parse_and_normalize_carrier_bill_xlsx
from .repository_items import insert_carrier_bill_items


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-bills/import",
        response_model=CarrierBillImportResult,
    )
    async def import_shipping_bill(
        carrier_code: str = Form(...),
        bill_month: str | None = Form(None),
        file: UploadFile = File(...),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> CarrierBillImportResult:
        filename = (file.filename or "").strip()
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="当前仅支持 .xlsx 对账单导入")

        carrier_code_clean = carrier_code.strip()
        bill_month_clean = (
            bill_month.strip()
            if isinstance(bill_month, str) and bill_month.strip()
            else None
        )

        if not carrier_code_clean:
            raise HTTPException(status_code=422, detail="carrier_code is required")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=422, detail="上传文件为空")

        _ = ImportCarrierBillCommand(
            carrier_code=carrier_code_clean,
            bill_month=bill_month_clean,
            filename=filename,
            file_bytes=file_bytes,
        )

        valid_rows, errors_data, skipped_count = parse_and_normalize_carrier_bill_xlsx(
            file_bytes
        )

        imported_count = 0

        if valid_rows:
            imported_count = await insert_carrier_bill_items(
                session,
                rows=valid_rows,
                carrier_code=carrier_code_clean,
                bill_month=bill_month_clean,
            )

        await session.commit()

        errors = [
            CarrierBillImportRowError(row_no=e.row_no, message=e.message)
            for e in errors_data
        ]

        return CarrierBillImportResult(
            ok=True,
            carrier_code=carrier_code_clean,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=len(errors),
            errors=errors,
        )
