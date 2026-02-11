# app/services/devtools/fake_orders/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class FakeVariant:
    variant_name: str
    filled_code: str


@dataclass(frozen=True)
class FakeLink:
    spu_key: str
    title: str
    variants: List[FakeVariant]


@dataclass(frozen=True)
class FakeShopSeed:
    shop_id: str
    title_prefix: str
    links: List[FakeLink]


@dataclass(frozen=True)
class FakeOrderAddr:
    # 对齐 OrderAddrIn：全部可空
    receiver_name: Optional[str]
    receiver_phone: Optional[str]
    province: Optional[str]
    city: Optional[str]
    district: Optional[str]
    detail: Optional[str]
    zipcode: Optional[str]


@dataclass(frozen=True)
class FakeSeed:
    platform: str
    shops: List[FakeShopSeed]
    # 可选：用于让 DevTools 生成订单时使用“指定地址”，否则使用随机地址
    order_addr: Optional[FakeOrderAddr] = None
