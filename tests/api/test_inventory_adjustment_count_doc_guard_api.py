from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def _iso_at(minutes_offset: int) -> str:
    base = datetime(2026, 4, 23, 10, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes_offset)).isoformat().replace("+00:00", "Z")


def _body_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


async def _create_count_doc(
    client: AsyncClient,
    *,
    warehouse_id: int,
    snapshot_at: str,
    remark: str | None = None,
):
    body: dict[str, object] = {
        "warehouse_id": warehouse_id,
        "snapshot_at": snapshot_at,
    }
    if remark is not None:
        body["remark"] = remark
    return await client.post("/inventory-adjustment/count-docs", json=body)


async def _freeze_count_doc(client: AsyncClient, doc_id: int):
    return await client.post(f"/inventory-adjustment/count-docs/{doc_id}/freeze")


async def _void_count_doc(client: AsyncClient, doc_id: int):
    return await client.post(f"/inventory-adjustment/count-docs/{doc_id}/void")


@pytest.mark.anyio
async def test_create_count_doc_rejects_when_active_doc_exists_same_warehouse(
    client: AsyncClient,
) -> None:
    create_resp_1 = await _create_count_doc(
        client,
        warehouse_id=1,
        snapshot_at=_iso_at(0),
        remark="guard test first doc",
    )
    assert create_resp_1.status_code == 201, create_resp_1.text
    body_1: dict[str, object] = create_resp_1.json()
    first_doc_id = int(body_1["id"])  # type: ignore[index]

    freeze_resp = await _freeze_count_doc(client, first_doc_id)
    assert freeze_resp.status_code == 200, freeze_resp.text

    create_resp_2 = await _create_count_doc(
        client,
        warehouse_id=1,
        snapshot_at=_iso_at(10),
        remark="guard test second doc",
    )
    assert create_resp_2.status_code == 400, create_resp_2.text

    err_body = create_resp_2.json()
    err_text = _body_text(err_body)
    assert "count_doc_active_exists" in err_text
    assert f"doc_id={first_doc_id}" in err_text
    assert "status=FROZEN" in err_text


@pytest.mark.anyio
async def test_void_count_doc_releases_warehouse_when_no_other_active_doc(
    client: AsyncClient,
) -> None:
    create_resp_1 = await _create_count_doc(
        client,
        warehouse_id=1,
        snapshot_at=_iso_at(20),
        remark="void release test first doc",
    )
    assert create_resp_1.status_code == 201, create_resp_1.text
    body_1: dict[str, object] = create_resp_1.json()
    first_doc_id = int(body_1["id"])  # type: ignore[index]

    freeze_resp = await _freeze_count_doc(client, first_doc_id)
    assert freeze_resp.status_code == 200, freeze_resp.text

    void_resp = await _void_count_doc(client, first_doc_id)
    assert void_resp.status_code == 200, void_resp.text
    void_body: dict[str, object] = void_resp.json()
    assert int(void_body["doc_id"]) == first_doc_id  # type: ignore[index]
    assert str(void_body["status"]) == "VOIDED"  # type: ignore[index]

    create_resp_2 = await _create_count_doc(
        client,
        warehouse_id=1,
        snapshot_at=_iso_at(30),
        remark="void release test second doc",
    )
    assert create_resp_2.status_code == 201, create_resp_2.text
    body_2: dict[str, object] = create_resp_2.json()
    assert str(body_2["status"]) == "DRAFT"  # type: ignore[index]
    assert int(body_2["warehouse_id"]) == 1  # type: ignore[index]
