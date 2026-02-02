# tests/_problem.py
from __future__ import annotations

from typing import Any, Dict


def as_problem(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    统一把 API 错误响应转换为 Problem 形状，兼容旧 detail 与新顶层格式。
    """
    # 新格式：顶层就是 Problem
    if "error_code" in payload and "message" in payload:
        return payload

    # 旧格式：detail={"code","message",...}
    d = payload.get("detail")
    if isinstance(d, dict) and "code" in d and "message" in d:
        out = {
            "error_code": d.get("code"),
            "message": d.get("message"),
            "http_status": payload.get("http_status"),
            "details": d.get("details"),
            "next_actions": d.get("next_actions"),
            "context": d.get("context"),
            "trace_id": d.get("trace_id"),
        }
        # 清理 None
        return {k: v for k, v in out.items() if v is not None}

    # 旧格式：detail=str / detail=list
    if isinstance(d, str):
        return {"error_code": "http_error", "message": d}
    if isinstance(d, list):
        return {"error_code": "request_validation_error", "message": "请求参数不合法", "details": d}

    # 兜底：找 message
    if "message" in payload:
        return {"error_code": payload.get("error_code", "http_error"), "message": payload["message"]}

    return {"error_code": "http_error", "message": str(payload)}
