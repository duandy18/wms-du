# app/api/routers/pricing_integrity/router.py
from __future__ import annotations

from fastapi import APIRouter

from . import active_schemes, cleanup, fix_archive_release, fix_detach_brackets, fix_one_click, fix_unbind_archived_templates, report

router = APIRouter(tags=["ops - pricing-integrity"])

# 按“选 → 读 → 修 → 一键 → 清理”注册，便于运维使用
active_schemes.register(router)

report.register(router)

fix_archive_release.register(router)
fix_detach_brackets.register(router)
fix_unbind_archived_templates.register(router)

fix_one_click.register(router)

cleanup.register(router)
