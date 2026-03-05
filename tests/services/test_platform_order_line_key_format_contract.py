# tests/services/test_platform_order_line_key_format_contract.py
from __future__ import annotations

from app.api.routers.platform_orders_fact_repo import line_key_from_inputs
from app.services.platform_order_fact_service import _line_key


def test_line_key_format_contract_keeps_legacy_prefixes_and_matches_repo_helper() -> None:
    """
    Contract: line_key 是“幂等锚点”，物理格式沿用历史前缀字符串，不承载 PSKU 业务语义。

    - filled_code 非空 -> 必须产出 "PSKU:{filled_code}"
    - filled_code 为空 -> 必须产出 "NO_PSKU:{line_no}"

    同时保证 app/api 与 app/services 两处生成逻辑严格一致（防漂移）。
    """
    # case 1: has filled_code
    filled_code = "SKU-INGEST-001"
    ln = 3
    lk1 = _line_key(filled_code=filled_code, line_no=ln)
    lk2 = line_key_from_inputs(filled_code=filled_code, line_no=ln)

    assert lk1 == f"PSKU:{filled_code}"
    assert lk2 == f"PSKU:{filled_code}"
    assert lk1 == lk2

    # case 2: filled_code is blank/None -> NO_PSKU:{line_no}
    lk3 = _line_key(filled_code=None, line_no=1)
    lk4 = line_key_from_inputs(filled_code=None, line_no=1)

    assert lk3 == "NO_PSKU:1"
    assert lk4 == "NO_PSKU:1"
    assert lk3 == lk4

    # case 3: repo helper needs line_no when no filled_code
    assert line_key_from_inputs(filled_code=None, line_no=None) is None

    # anti-regression: do NOT introduce new prefixes without a dedicated migration/compat phase
    assert not lk1.startswith("FILLED:")
    assert not lk3.startswith("NO_FILLED:")
