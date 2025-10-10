# app/schemas/stock_ledger.py
from datetime import datetime

from pydantic import BaseModel


class LedgerQuery(BaseModel):
    stock_id: int | None = None
    batch_code: str | None = None
    reason: str | None = None
    ref: str | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    limit: int = 100
    offset: int = 0


class LedgerRow(BaseModel):
    id: int
    stock_id: int
    batch_id: int | None
    delta: int
    reason: str
    ref: str | None
    created_at: datetime
    after_qty: int


class LedgerList(BaseModel):
    total: int
    items: list[LedgerRow]
