from __future__ import annotations


_ALLOWED_DEFAULT_PRICING_MODE = {
    "flat",
    "linear_total",
    "step_over",
    "manual_quote",
}


def validate_default_pricing_mode(value: str) -> str:
    v = str(value or "").strip()
    if v not in _ALLOWED_DEFAULT_PRICING_MODE:
        raise ValueError(
            "default_pricing_mode must be one of: flat / linear_total / step_over / manual_quote"
        )
    return v
