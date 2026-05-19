# tests/api/test_wms_system_iam_snapshot_retired_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_wms_system_iam_snapshot_read_v1_is_retired() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/iam-snapshot")

    assert response.status_code == 404


def test_wms_system_iam_snapshot_read_v1_is_removed_from_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    assert "/system/read/v1/iam-snapshot" not in paths
