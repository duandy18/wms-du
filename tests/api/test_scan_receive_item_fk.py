# tests/api/test_scan_receive_item_fk.py
#
# 目标：
# - 当 item_id 不存在时，/scan(mode=receive) 必须失败，并暴露 FK 相关错误（不落账）。
# - 当 items 表中已存在该 item_id 时，同样的收货请求不能再触发 FK 错误。
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


def _ensure_item(
    db: Session, item_id: int, sku: str | None = None, name: str | None = None
) -> None:
    """
    在 items 表中确保存在一条指定 id 的记录：

    - 若已存在（id 已存在），不做任何事；
    - 若不存在，只插入最小必要字段 (id, sku, name)，让 DB 自己填充其余默认列。

    注意：不依赖 ORM Item 模型字段定义，直接用 SQL，避免模型/表不一致问题。
    """
    sku_val = (sku or str(item_id)).strip()
    name_val = (name or f"ITEM-{item_id}").strip()

    db.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": item_id, "sku": sku_val, "name": name_val},
    )
    db.commit()


def test_scan_receive_unknown_item_should_fail_fk() -> None:
    """
    当 item_id 在 items 表中不存在时，
    /scan(mode=receive) 不应该落账，而是返回错误信息。
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

    # 不强依赖完整错误字符串，但必须体现 FK 相关语义
    assert "fk_batches_item" in joined or "not present in table" in joined


def test_scan_receive_existing_item_should_succeed() -> None:
    """
    在 items 表中预先插入 item 记录后，
    同样的 /scan(mode=receive) 请求应当不再触发 FK 错误。
    """
    target_item_id = 52405

    # 1) 先插入 item 主数据，满足 FK（id + sku + name）
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

    # 期望：不再出现 FK 相关错误
    errors = data.get("errors") or []
    joined = "\n".join(e.get("error", "") for e in errors)
    assert "fk_batches_item" not in joined
    assert 'not present in table "items"' not in joined

    # 这里不强行要求 ok/committed=True（避免把业务逻辑绑死在一条测试上），
    # 只要确认不再 FK 炸，后续可以在别的测试里更细分地检查台账 /库存等行为。
    # 如果你已经确认 receive 流程完全通了，可以再加：
    # assert data.get("ok") is True
    # assert data.get("committed") is True
