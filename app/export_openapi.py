# app/export_openapi.py
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def export_openapi(dst: str | Path = "openapi.json") -> Path:
    """
    导出当前 FastAPI 应用的 OpenAPI 文档到磁盘.
    返回写入的路径,便于测试断言.
    """
    client = TestClient(app)
    resp = client.get("/openapi.json")
    resp.raise_for_status()
    data = resp.json()

    path = Path(dst)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    export_openapi(target)
