from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.wms.ledger.contracts.stock_ledger import LedgerQuery
from app.wms.ledger.helpers.stock_ledger import resolve_ledger_lot_code_filter


def test_resolve_ledger_lot_code_filter_uses_lot_code_as_canonical_input() -> None:
    query = LedgerQuery(lot_code="  LOT-A  ")

    should_filter, value = resolve_ledger_lot_code_filter(query)

    assert should_filter is True
    assert value == "LOT-A"
    assert query.lot_code == "LOT-A"


def test_ledger_query_rejects_retired_batch_code_alias() -> None:
    with pytest.raises(ValidationError) as exc:
        LedgerQuery(batch_code="  LOT-B  ")

    assert "batch_code" in str(exc.value)


def test_resolve_ledger_lot_code_filter_preserves_explicit_null_semantics() -> None:
    query = LedgerQuery(lot_code="")

    should_filter, value = resolve_ledger_lot_code_filter(query)

    assert should_filter is True
    assert value is None
    assert query.lot_code == ""


def test_resolve_ledger_lot_code_filter_ignores_absent_lot_code() -> None:
    query = LedgerQuery(item_id=1)

    should_filter, value = resolve_ledger_lot_code_filter(query)

    assert should_filter is False
    assert value is None
