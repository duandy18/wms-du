# app/schemas/receive_task_supplement.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel


class ReceiveSupplementLineOut(BaseModel):
    """补录清单行"""

    task_id: int
    po_id: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    warehouse_id: int

    item_id: int
    item_name: Optional[str] = None

    scanned_qty: int
    batch_code: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    # 返回字段名用后端字段，但前端会映射成中文
    missing_fields: List[str] = []


class ReceiveTaskLineMetaIn(BaseModel):
    """补录写回：只更新批次/日期（不改数量）"""

    batch_code: str | None = None
    production_date: date | None = None
    expiry_date: date | None = None


class ReceiveSupplementSummaryOut(BaseModel):
    """
    补录清单汇总（用于作业台顶部告警 / 快速判断）
    """

    mode: str
    total_rows: int
    by_field: Dict[str, int]  # e.g. {"batch_code": 12, "production_date": 8, "expiry_date": 5}
