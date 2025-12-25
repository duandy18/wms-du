# app/services/user_errors.py
from __future__ import annotations


class AuthorizationError(Exception):
    """权限不足"""


class DuplicateUserError(Exception):
    """用户名已存在"""


class NotFoundError(Exception):
    """实体不存在"""
