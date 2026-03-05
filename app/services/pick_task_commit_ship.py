# app/services/pick_task_commit_ship.py
from __future__ import annotations

# ✅ 兼容入口：外部仍然 from app.services.pick_task_commit_ship import commit_ship
from app.services.pick_task_commit_ship.commit import commit_ship

__all__ = ["commit_ship"]
