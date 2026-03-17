# app/models/carrier_bill_import_batch.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CarrierBillImportBatchStatus = Literal["imported", "reconciled", "failed", "archived"]


class CarrierBillImportBatch(Base):
    """
    快递账单导入批次头表 carrier_bill_import_batches

    语义定位：
    - 表示“一次账单导入事件”的头记录；
    - import_batch_no 是业务可见批次号；
    - id 是系统内部主键，供账单明细 / 对账异常通过 import_batch_id 正式关联；
    - 当前阶段先承接统一账单导入头，不强制绑定具体上传文件实体。
    """

    __tablename__ = "carrier_bill_import_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    carrier_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    import_batch_no: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    bill_month: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    source_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[CarrierBillImportBatchStatus] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'imported'"),
    )

    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('imported', 'reconciled', 'failed', 'archived')",
            name="ck_carrier_bill_import_batches_status",
        ),
        Index(
            "uq_carrier_bill_import_batches_carrier_batch",
            "carrier_code",
            "import_batch_no",
            unique=True,
        ),
        Index(
            "ix_carrier_bill_import_batches_bill_month",
            "bill_month",
        ),
        Index(
            "ix_carrier_bill_import_batches_imported_at",
            "imported_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CarrierBillImportBatch id={self.id} "
            f"carrier_code={self.carrier_code} "
            f"import_batch_no={self.import_batch_no} "
            f"bill_month={self.bill_month} "
            f"status={self.status}>"
        )
