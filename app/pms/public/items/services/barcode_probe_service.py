# app/pms/public/items/services/barcode_probe_service.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.pms.items.models.item_barcode import ItemBarcode
from app.pms.items.models.item_uom import ItemUOM
from app.pms.public.items.contracts.barcode_probe import (
    BarcodeProbeError,
    BarcodeProbeOut,
    BarcodeProbeStatus,
)
from app.pms.public.items.services.item_read_service import ItemReadService


class BarcodeProbeService:
    """
    PMS public barcode probe service。

    职责：
    - 解析 barcode 是否绑定
    - 返回 item_id / item_uom_id / ratio_to_base
    - 补充最小 item_basic 读模型

    边界：
    - 这是 PMS 主数据探针，不承载 WMS /scan 的作业语义
    - 不返回 committed / scan_ref / event_id / qty / batch_code 等仓内字段
    """

    def __init__(self, db: Session | AsyncSession) -> None:
        self.db = db

    def _require_sync_db(self) -> Session:
        if isinstance(self.db, AsyncSession):
            raise TypeError("BarcodeProbeService sync API requires Session, got AsyncSession")
        if not isinstance(self.db, Session):
            raise TypeError(f"BarcodeProbeService expected Session, got {type(self.db)!r}")
        return self.db

    def _require_async_db(self) -> AsyncSession:
        if not isinstance(self.db, AsyncSession):
            raise TypeError("BarcodeProbeService async API requires AsyncSession")
        return self.db

    def probe(self, *, barcode: str) -> BarcodeProbeOut:
        db = self._require_sync_db()
        code = (barcode or "").strip()
        if not code:
            return BarcodeProbeOut(
                ok=False,
                status=BarcodeProbeStatus.ERROR,
                barcode="",
                errors=[BarcodeProbeError(stage="probe", error="barcode is required")],
            )

        stmt = (
            select(ItemBarcode, ItemUOM)
            .join(
                ItemUOM,
                (ItemUOM.id == ItemBarcode.item_uom_id)
                & (ItemUOM.item_id == ItemBarcode.item_id),
            )
            .where(ItemBarcode.barcode == code)
            .order_by(ItemBarcode.active.desc(), ItemBarcode.id.asc())
        )
        row = db.execute(stmt).first()
        if row is None:
            return BarcodeProbeOut(
                ok=True,
                status=BarcodeProbeStatus.UNBOUND,
                barcode=code,
            )

        bc, uom = row
        item_basic = ItemReadService(db).get_basic_by_id(item_id=int(bc.item_id))
        return BarcodeProbeOut(
            ok=True,
            status=BarcodeProbeStatus.BOUND,
            barcode=code,
            item_id=int(bc.item_id),
            item_uom_id=int(bc.item_uom_id),
            ratio_to_base=int(uom.ratio_to_base),
            symbology=str(bc.symbology),
            active=bool(bc.active),
            item_basic=item_basic,
        )

    async def aprobe(self, *, barcode: str) -> BarcodeProbeOut:
        db = self._require_async_db()
        code = (barcode or "").strip()
        if not code:
            return BarcodeProbeOut(
                ok=False,
                status=BarcodeProbeStatus.ERROR,
                barcode="",
                errors=[BarcodeProbeError(stage="probe", error="barcode is required")],
            )

        stmt = (
            select(ItemBarcode, ItemUOM)
            .join(
                ItemUOM,
                (ItemUOM.id == ItemBarcode.item_uom_id)
                & (ItemUOM.item_id == ItemBarcode.item_id),
            )
            .where(ItemBarcode.barcode == code)
            .order_by(ItemBarcode.active.desc(), ItemBarcode.id.asc())
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return BarcodeProbeOut(
                ok=True,
                status=BarcodeProbeStatus.UNBOUND,
                barcode=code,
            )

        bc, uom = row
        item_basic = await ItemReadService(db).aget_basic_by_id(item_id=int(bc.item_id))
        return BarcodeProbeOut(
            ok=True,
            status=BarcodeProbeStatus.BOUND,
            barcode=code,
            item_id=int(bc.item_id),
            item_uom_id=int(bc.item_uom_id),
            ratio_to_base=int(uom.ratio_to_base),
            symbology=str(bc.symbology),
            active=bool(bc.active),
            item_basic=item_basic,
        )
