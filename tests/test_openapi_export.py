# tests/test_openapi_export.py
from pathlib import Path

from app.export_openapi import export_openapi


def test_export_openapi_function(tmp_path: Path):
    """确保 export_openapi 函数能导出文件并包含关键字段."""
    out = export_openapi(tmp_path / "openapi.json")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    # 基本断言: 文件存在, 且包含关键字段
    assert '"openapi"' in text
    assert '"paths"' in text


def test_export_openapi_smoke(client):
    """通过 client fixture 直接请求 /openapi.json."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert "openapi" in data
    assert isinstance(data, dict)
