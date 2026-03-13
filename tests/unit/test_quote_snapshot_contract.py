# tests/unit/test_quote_snapshot_contract.py
from __future__ import annotations

import pytest

from app.tms.quote_snapshot import (
    build_quote_snapshot,
    extract_cost_estimated,
    extract_quote_snapshot,
    validate_quote_snapshot,
)


def test_build_quote_snapshot_has_v1_contract() -> None:
    snapshot = build_quote_snapshot(
        source="shipping_quote.calc",
        input_payload={"warehouse_id": 1, "scheme_id": 2},
        selected_quote={
            "quote_status": "OK",
            "scheme_id": 2,
            "currency": "CNY",
            "total_amount": 12.5,
            "weight": {"billable_weight_kg": 1.2},
            "breakdown": {"base": 10.0},
            "reasons": ["group_match:x", "total=12.50 CNY"],
        },
    )

    assert snapshot["version"] == "v1"
    assert snapshot["source"] == "shipping_quote.calc"

    selected = snapshot["selected_quote"]
    assert isinstance(selected, dict)
    assert selected["total_amount"] == 12.5
    assert selected["reasons"] == ["group_match:x", "total=12.50 CNY"]


def test_extract_quote_snapshot_from_meta() -> None:
    meta = {
        "foo": "bar",
        "quote_snapshot": {
            "version": "v1",
            "selected_quote": {
                "total_amount": 9.9,
                "reasons": ["ok"],
            },
        },
    }

    snapshot = extract_quote_snapshot(meta)
    assert snapshot["version"] == "v1"


def test_validate_quote_snapshot_and_extract_cost() -> None:
    snapshot = {
        "version": "v1",
        "selected_quote": {
            "total_amount": 19.8,
            "reasons": ["matrix_match:x"],
        },
    }

    validate_quote_snapshot(snapshot)
    assert extract_cost_estimated(snapshot) == 19.8


def test_validate_quote_snapshot_rejects_missing_reasons() -> None:
    snapshot = {
        "version": "v1",
        "selected_quote": {
            "total_amount": 19.8,
            "reasons": [],
        },
    }

    with pytest.raises(Exception):
        validate_quote_snapshot(snapshot)
