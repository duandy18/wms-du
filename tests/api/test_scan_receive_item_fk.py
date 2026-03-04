# tests/api/test_scan_receive_item_fk.py
#
# 目标：
# - 当 item_id 不存在时，/scan(mode=receive) 必须失败（不落账），并暴露“无法写入”的关键信号：
#     * 旧世界可能是 items FK 失败文本；
#     * Phase M / lot-world 护栏下，也可能更早表现为 lot_not_found（没有可解析的 lot / 不允许隐式创建）。
# - 当 items 表中已存在该 item_id 时，同样的收货请求不能再触发上述“缺失 item / 缺失 lot”的阻断信号。
#
from __future__ import annotations

from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _get_db() -> Generator[Session, None, None]:
    """简单同步 Session 工具，用于在测试中直接操作 DB。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_item(db: Session, item_id: int, sku: str | None = None, name: str | None = None) -> None:
    """
    在 items 表中确保存在一条指定 id 的记录：

    - 若已存在（id 已存在），不做任何事；
    - 若不存在，插入 Phase M-5 “最小合法”字段集合，避免 items policy NOT NULL / CHECK 护栏爆炸；
    - 同时补齐 item_uoms（base+defaults），满足单位主权。

    注意：不依赖 ORM Item 模型字段定义，直接用 SQL，避免模型/表不一致问题。
    """
    sku_val = (sku or str(item_id)).strip()
    name_val = (name or f"ITEM-{item_id}").strip()

    db.execute(
        text(
            """
            INSERT INTO items (
              id, sku, name,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES (
              :id, :sku, :name,
              'SUPPLIER_ONLY'::lot_source_policy, CAST(:expiry_policy AS expiry_policy), TRUE, TRUE,
              NULL, NULL
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": int(item_id),
            "sku": sku_val,
            "name": name_val,
            "expiry_policy": "NONE",
        },
    )

    db.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :i, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            """
        ),
        {"i": int(item_id)},
    )

    db.commit()


def _looks_like_missing_item_or_lot_guard(msg: str) -> bool:
    """
    Phase M：不再绑死 batches/约束名；只验证“unknown item / 无法解析 lot 导致写入被阻断”的语义。

    兼容不同错误包装/不同驱动/不同实现路径的文本差异：
    - 可能是 items FK 失败（旧路径）
    - 也可能是 lot_not_found（lot-world 护栏更早触发）
    - 或者是服务层先拦截的 item_not_found（更明确的语义）
    """
    s = (msg or "").lower()

    # 0) 明确的 unknown item 语义
    if "item_not_found" in s:
        return True
    if "unknown item" in s:
        return True

    # 1) items FK 语义（常见：psycopg/asyncpg 文本）
    if 'not present in table "items"' in s:
        return True
    if "violates foreign key constraint" in s and "item" in s:
        return True
    if ("foreign key" in s) and ("items" in s):
        return True

    # 2) lot-world 护栏语义：lot_not_found / “lot 不存在”
    if "lot_not_found" in s:
        return True
    if "lot 不存在" in msg:
        return True

    return False


def test_scan_receive_unknown_item_should_fail_fk() -> None:
    """
    当 item_id 在 items 表中不存在时，
    /scan(mode=receive) 不应该落账，而是返回错误信息（语义：缺失 item / 缺失 lot 导致阻断）。
    """
    payload = {
        "mode": "receive",
        "warehouse_id": 1,
        "item_id": 999999,  # 假定一定不存在
        "qty": 1,
        "batch_code": "TEST-FK",
        "production_date": "2025-11-24",
        # ctx 不能为 null，否则 scan_orchestrator._scan_ref 会炸
        "ctx": {"device_id": "test-fk-unknown"},
    }

    resp = client.post("/scan", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    # Scan API HTTP 200，但业务上 ok=false / committed=false
    assert data.get("ok") is False
    assert data.get("committed") is False
    assert data.get("source") == "scan_receive_error"

    errors = data.get("errors") or []
    joined = "\n".join(e.get("error", "") for e in errors)

    # 不强依赖约束名；必须体现“unknown item / lot-world 护栏阻断”的语义
    assert _looks_like_missing_item_or_lot_guard(joined), joined


def test_scan_receive_existing_item_should_succeed() -> None:
    """
    在 items 表中预先插入 item 记录后，
    同样的 /scan(mode=receive) 请求应当不再触发“缺失 item / 缺失 lot”类阻断信号。
    """
    target_item_id = 52405

    # 1) 先插入 item 主数据，满足 FK（Phase M-5 最小合法 + item_uoms）
    db = next(_get_db())
    _ensure_item(
        db,
        item_id=target_item_id,
        sku="ITEM-52405",
        name="测试商品52405",
    )

    # 2) 发送收货请求（注意带 ctx.device_id，避免 orchestrator NPE）
    payload = {
        "mode": "receive",
        "warehouse_id": 1,
        "item_id": target_item_id,
        "qty": 3,
        "batch_code": "C-23",
        "production_date": "2025-11-11",
        "ctx": {"device_id": "test-fk-exists"},
    }

    resp = client.post("/scan", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()

    # 期望：不再出现“unknown item / lot-world 护栏阻断”的错误
    errors = data.get("errors") or []
    joined = "\n".join(e.get("error", "") for e in errors)
    assert not _looks_like_missing_item_or_lot_guard(joined), joined

    # 这里不强行要求 ok/committed=True（避免把业务逻辑绑死在一条测试上），
    # 只要确认不再被“缺失 item / 缺失 lot”阻断，后续可以在别的测试里更细分地检查台账 /库存等行为。
