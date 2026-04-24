# app/tms/records/models/__init__.py
# Domain-owned ORM models for TMS records / logistics ledger.

from app.tms.records.models.shipping_record import ShippingRecord

__all__ = [
    "ShippingRecord",
]
