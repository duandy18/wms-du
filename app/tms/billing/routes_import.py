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

# ✅ 拆分后的 repository 引用
from .repository_batches import (
    create_carrier_bill_import_batch,
    get_carrier_bill_import_batch_by_business_key,
    update_carrier_bill_import_batch,
)
from .repository_items import (
    delete_carrier_bill_items_by_batch,
    insert_carrier_bill_items,
)


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-bills/import",
        response_model=CarrierBillImportResult,
    )
    async def import_shipping_bill(
        carrier_code: str = Form(...),
        import_batch_no: str = Form(...),
        bill_month: str | None = Form(None),
        file: UploadFile = File(...),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> CarrierBillImportResult:
        filename = (file.filename or "").strip()
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="当前仅支持 .xlsx 对账单导入")

        carrier_code_clean = carrier_code.strip()
        import_batch_no_clean = import_batch_no.strip()
        bill_month_clean = (
            bill_month.strip()
            if isinstance(bill_month, str) and bill_month.strip()
            else None
        )

        if not carrier_code_clean:
            raise HTTPException(status_code=422, detail="carrier_code is required")
        if not import_batch_no_clean:
            raise HTTPException(status_code=422, detail="import_batch_no is required")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=422, detail="上传文件为空")

        _ = ImportCarrierBillCommand(
            carrier_code=carrier_code_clean,
            import_batch_no=import_batch_no_clean,
            bill_month=bill_month_clean,
            filename=filename,
            file_bytes=file_bytes,
        )

        valid_rows, errors_data, skipped_count = parse_and_normalize_carrier_bill_xlsx(
            file_bytes
        )

        row_count = len(valid_rows) + skipped_count + len(errors_data)
        success_count = len(valid_rows)
        error_count = len(errors_data)

        batch_row = await get_carrier_bill_import_batch_by_business_key(
            session,
            carrier_code=carrier_code_clean,
            import_batch_no=import_batch_no_clean,
        )

        if batch_row is None:
            import_batch_id = await create_carrier_bill_import_batch(
                session,
                carrier_code=carrier_code_clean,
                import_batch_no=import_batch_no_clean,
                bill_month=bill_month_clean,
                source_filename=filename or None,
                row_count=row_count,
                success_count=success_count,
                error_count=error_count,
                status="imported" if success_count > 0 else "failed",
            )
        else:
            import_batch_id = int(batch_row["id"])
            await delete_carrier_bill_items_by_batch(
                session,
                import_batch_id=import_batch_id,
            )
            await update_carrier_bill_import_batch(
                session,
                import_batch_id=import_batch_id,
                bill_month=bill_month_clean,
                source_filename=filename or None,
                row_count=row_count,
                success_count=success_count,
                error_count=error_count,
                status="imported" if success_count > 0 else "failed",
            )

        imported_count = 0
        if valid_rows:
            imported_count = await insert_carrier_bill_items(
                session,
                import_batch_id=import_batch_id,
                rows=valid_rows,
                carrier_code=carrier_code_clean,
                import_batch_no=import_batch_no_clean,
                bill_month=bill_month_clean,
            )

        await session.commit()

        errors = [
            CarrierBillImportRowError(row_no=e.row_no, message=e.message)
            for e in errors_data
        ]

        return CarrierBillImportResult(
            ok=True,
            import_batch_id=import_batch_id,
            carrier_code=carrier_code_clean,
            import_batch_no=import_batch_no_clean,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=len(errors),
            errors=errors,
        )
