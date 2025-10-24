# app/models/role_grants.py
"""
兼容层：
- 统一从 app.models.associations 引入 user_role / role_permission
- 避免老代码引用 role_grants.py 时出错
"""
from app.models.associations import user_role, role_permission  # noqa: F401
