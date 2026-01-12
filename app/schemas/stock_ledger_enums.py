# app/schemas/stock_ledger_enums.py
from __future__ import annotations

from enum import Enum


class ReasonCanon(str, Enum):
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    ADJUSTMENT = "ADJUSTMENT"


class SubReason(str, Enum):
    PO_RECEIPT = "PO_RECEIPT"
    RETURN_RECEIPT = "RETURN_RECEIPT"
    ORDER_SHIP = "ORDER_SHIP"
    INTERNAL_SHIP = "INTERNAL_SHIP"
    RETURN_TO_VENDOR = "RETURN_TO_VENDOR"
    COUNT_ADJUST = "COUNT_ADJUST"
