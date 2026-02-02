# app/api/error_detail.py
from __future__ import annotations

from typing import Dict

from app.api.problem import raise_409 as _raise_409
from app.api.problem import raise_422 as _raise_422
from app.api.problem import raise_500 as _raise_500


def raise_422(code: str, message: str) -> None:
    _raise_422(error_code=code, message=message)


def raise_409(code: str, message: str) -> None:
    _raise_409(error_code=code, message=message)


def raise_500(code: str, message: str) -> None:
    _raise_500(error_code=code, message=message)


def as_error_detail(code: str, message: str) -> Dict[str, str]:
    # 兼容旧调用点：仍返回 {code,message}，但强烈建议迁移到 Problem 结构
    return {"code": code, "message": message}
