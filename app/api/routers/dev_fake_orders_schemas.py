# app/api/routers/dev_fake_orders_schemas.py
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class FakeGenerateParams(BaseModel):
    # generate-only：不落库，允许稍大用于分布/回归
    count: int = Field(10, ge=1, le=200)
    lines_min: int = Field(1, ge=1, le=10)
    lines_max: int = Field(3, ge=1, le=10)
    qty_min: int = Field(1, ge=1, le=100)
    qty_max: int = Field(3, ge=1, le=100)
    rng_seed: int = Field(42, ge=0, le=10_000_000)


class DevFakeOrdersGenerateIn(BaseModel):
    seed: Dict[str, Any]
    generate: FakeGenerateParams = Field(default_factory=FakeGenerateParams)


class DevFakeOrdersGenerateOut(BaseModel):
    batch_id: str
    orders: List[Dict[str, Any]]
    gen_stats: Dict[str, Any]


class DevFakeOrdersRunIn(BaseModel):
    seed: Dict[str, Any]
    generate: FakeGenerateParams = Field(default_factory=FakeGenerateParams)
    watch_filled_codes: List[str] = Field(default_factory=list)
    with_replay: bool = True


class DevFakeOrdersRunOut(BaseModel):
    report: Dict[str, Any]
    gen_stats: Dict[str, Any]
