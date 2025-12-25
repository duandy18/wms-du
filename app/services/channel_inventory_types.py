# app/services/channel_inventory_types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class BatchQty:
    batch_code: str
    qty: int


@dataclass
class ChannelInventory:
    platform: str
    shop_id: str
    warehouse_id: int
    item_id: int

    on_hand: int
    reserved_open: int
    available: int

    batches: List[BatchQty]
