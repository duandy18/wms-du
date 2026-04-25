# app/shipping_assist/records/models/__init__.py
# Domain-owned ORM models for TMS records / logistics ledger.

from app.shipping_assist.records.models.shipping_record import ShippingRecord

__all__ = [
    "ShippingRecord",
]
