from __future__ import annotations

from app.wms.ledger.contracts.stock_ledger import SubReason


def test_stock_ledger_sub_reason_contract_includes_count_confirm() -> None:
    values = {x.value for x in SubReason}
    assert "COUNT_CONFIRM" in values
    assert "COUNT_ADJUST" in values
