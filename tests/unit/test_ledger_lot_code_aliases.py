from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.wms.ledger.contracts.stock_ledger import LedgerQuery
from app.wms.ledger.helpers.stock_ledger import (
    normalize_ledger_lot_code_aliases,
    resolve_ledger_lot_code_filter,
)


def test_resolve_ledger_lot_code_filter_uses_lot_code_as_canonical_input() -> None:
    query = LedgerQuery(lot_code="  LOT-A  ")

    should_filter, value = resolve_ledger_lot_code_filter(query)
    normalized = normalize_ledger_lot_code_aliases(query)

    assert should_filter is True
    assert value == "LOT-A"
    assert normalized.lot_code == "LOT-A"
    assert normalized.batch_code == "LOT-A"


def test_resolve_ledger_lot_code_filter_keeps_batch_code_compatibility() -> None:
    query = LedgerQuery(batch_code="  LOT-B  ")

    should_filter, value = resolve_ledger_lot_code_filter(query)
    normalized = normalize_ledger_lot_code_aliases(query)

    assert should_filter is True
    assert value == "LOT-B"
    assert normalized.lot_code == "LOT-B"
    assert normalized.batch_code == "LOT-B"


def test_resolve_ledger_lot_code_filter_accepts_matching_aliases() -> None:
    query = LedgerQuery(lot_code="LOT-C", batch_code="  LOT-C  ")

    should_filter, value = resolve_ledger_lot_code_filter(query)
    normalized = normalize_ledger_lot_code_aliases(query)

    assert should_filter is True
    assert value == "LOT-C"
    assert normalized.lot_code == "LOT-C"
    assert normalized.batch_code == "LOT-C"


def test_resolve_ledger_lot_code_filter_rejects_conflicting_aliases() -> None:
    query = LedgerQuery(lot_code="LOT-D", batch_code="LOT-E")

    with pytest.raises(HTTPException) as exc:
        resolve_ledger_lot_code_filter(query)

    assert exc.value.status_code == 422
    assert exc.value.detail["error_code"] == "lot_code_alias_conflict"


def test_resolve_ledger_lot_code_filter_preserves_explicit_null_semantics() -> None:
    query = LedgerQuery(lot_code="")

    should_filter, value = resolve_ledger_lot_code_filter(query)
    normalized = normalize_ledger_lot_code_aliases(query)

    assert should_filter is True
    assert value is None
    assert normalized.lot_code is None
    assert normalized.batch_code is None


def test_resolve_ledger_lot_code_filter_ignores_absent_aliases() -> None:
    query = LedgerQuery(item_id=1)

    should_filter, value = resolve_ledger_lot_code_filter(query)
    normalized = normalize_ledger_lot_code_aliases(query)

    assert should_filter is False
    assert value is None
    assert normalized is query
