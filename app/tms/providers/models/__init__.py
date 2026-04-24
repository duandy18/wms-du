# app/tms/providers/models/__init__.py
# Domain-owned ORM models for TMS providers, waybill configs, and warehouse-provider bindings.

from app.tms.providers.models.electronic_waybill_config import ElectronicWaybillConfig
from app.tms.providers.models.shipping_provider import ShippingProvider
from app.tms.providers.models.shipping_provider_contact import ShippingProviderContact
from app.tms.providers.models.warehouse_shipping_provider import WarehouseShippingProvider

__all__ = [
    "ElectronicWaybillConfig",
    "ShippingProvider",
    "ShippingProviderContact",
    "WarehouseShippingProvider",
]
