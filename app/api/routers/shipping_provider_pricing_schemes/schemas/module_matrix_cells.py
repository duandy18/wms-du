# app/api/routers/shipping_provider_pricing_schemes/schemas/module_matrix_cells.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_ALLOWED_PRICING_MODES = {"flat", "linear_total", "step_over", "manual_quote"}


# ---------------------------------------------------------
# Out Models
# ---------------------------------------------------------

class ModuleMatrixCellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    group_id: int
    module_range_id: int
    range_module_id: int

    pricing_mode: str

    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None

    active: bool


class ModuleMatrixCellsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    module_code: str
    cells: List[ModuleMatrixCellOut] = Field(default_factory=list)


# ---------------------------------------------------------
# PUT Input
# ---------------------------------------------------------

class ModuleMatrixCellPutItemIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_id: int = Field(..., ge=1)
    module_range_id: int = Field(..., ge=1)

    pricing_mode: str

    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: bool = True

    @model_validator(mode="after")
    def _validate_shape(self):

        mode = str(self.pricing_mode)

        if mode not in _ALLOWED_PRICING_MODES:
            raise ValueError(
                "pricing_mode must be one of: flat / linear_total / step_over / manual_quote"
            )

        if mode == "flat":
            if self.flat_amount is None:
                raise ValueError("flat pricing_mode requires flat_amount")

            if any(v is not None for v in (self.base_amount, self.rate_per_kg, self.base_kg)):
                raise ValueError("flat pricing_mode only allows flat_amount")

        if mode == "linear_total":
            if self.base_amount is None:
                raise ValueError("linear_total pricing_mode requires base_amount")

            if self.rate_per_kg is None:
                raise ValueError("linear_total pricing_mode requires rate_per_kg")

            if self.flat_amount is not None or self.base_kg is not None:
                raise ValueError(
                    "linear_total pricing_mode does not allow flat_amount or base_kg"
                )

        if mode == "step_over":
            if self.base_kg is None:
                raise ValueError("step_over pricing_mode requires base_kg")

            if self.base_amount is None:
                raise ValueError("step_over pricing_mode requires base_amount")

            if self.rate_per_kg is None:
                raise ValueError("step_over pricing_mode requires rate_per_kg")

            if self.flat_amount is not None:
                raise ValueError("step_over pricing_mode does not allow flat_amount")

        if mode == "manual_quote":
            if any(
                v is not None
                for v in (self.flat_amount, self.base_amount, self.rate_per_kg, self.base_kg)
            ):
                raise ValueError("manual_quote pricing_mode does not allow pricing fields")

        return self


class ModuleMatrixCellsPutIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cells: List[ModuleMatrixCellPutItemIn] = Field(default_factory=list)
