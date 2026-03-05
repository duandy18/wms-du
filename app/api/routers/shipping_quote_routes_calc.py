# app/api/routers/shipping_quote_routes_calc.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.error_detail import raise_422, raise_500
from app.api.routers.shipping_quote_error_codes import QuoteCalcErrorCode, map_calc_value_error_to_code
from app.api.routers.shipping_quote_helpers import check_perm, dims_from_payload
from app.api.routers.shipping_quote_schemas import QuoteCalcIn, QuoteCalcOut
from app.db.deps import get_db
from app.services.audit_writer_sync import SyncAuditEventWriter
from app.services.shipping_quote_service import Dest, calc_quote


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-quote/calc",
        response_model=QuoteCalcOut,
        status_code=status.HTTP_200_OK,
    )
    def calc_shipping_quote(
        payload: QuoteCalcIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        dims = dims_from_payload(payload.length_cm, payload.width_cm, payload.height_cm)

        audit_ref = f"WH:{int(payload.warehouse_id)}|SCHEME:{int(payload.scheme_id)}"

        try:
            result = calc_quote(
                db=db,
                scheme_id=payload.scheme_id,
                warehouse_id=payload.warehouse_id,
                dest=Dest(
                    province=payload.dest.province,
                    city=payload.dest.city,
                    district=payload.dest.district,
                    province_code=payload.dest.province_code,
                    city_code=payload.dest.city_code,
                ),
                real_weight_kg=float(payload.real_weight_kg),
                dims_cm=dims,
                flags=payload.flags,
            )
        except ValueError as e:
            msg = str(e)
            code = map_calc_value_error_to_code(msg)

            # ✅ Phase 4：失败也要落库（否则异常返回会触发 rollback，审计会丢）
            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_CALC_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-quote/calc",
                    "error_code": code,
                    "message": msg,
                    "scheme_id": int(payload.scheme_id),
                    "warehouse_id": int(payload.warehouse_id),
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                },
                auto_commit=True,
            )

            raise_422(code, msg)

        except Exception as e:
            msg = f"calc failed: {e}"

            SyncAuditEventWriter.write(
                db,
                flow="SHIPPING_QUOTE",
                event="QUOTE_CALC_REJECT",
                ref=audit_ref,
                trace_id=None,
                meta={
                    "endpoint": "/shipping-quote/calc",
                    "error_code": QuoteCalcErrorCode.FAILED,
                    "message": msg,
                    "scheme_id": int(payload.scheme_id),
                    "warehouse_id": int(payload.warehouse_id),
                    "dest": payload.dest.model_dump(),
                    "real_weight_kg": float(payload.real_weight_kg),
                },
                auto_commit=True,
            )

            raise_500(QuoteCalcErrorCode.FAILED, msg)

        return QuoteCalcOut(
            ok=bool(result.get("ok", True)),
            quote_status=str(result.get("quote_status") or "OK"),
            currency=result.get("currency"),
            total_amount=result.get("total_amount"),
            weight=result.get("weight") or {},
            zone=result.get("zone"),
            bracket=result.get("bracket"),
            breakdown=result.get("breakdown") or {},
            reasons=result.get("reasons") or [],
        )
