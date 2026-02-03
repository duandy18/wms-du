# app/services/scan_handlers/__init__.py
"""
Unified public API for scan handlers.

The scan orchestrator imports handlers like:
    from app.services.scan_handlers import handle_receive, handle_count, handle_pick

This module consolidates the canonical handler entry points and avoids accidental
stale imports. Keep these bindings in sync with the concrete handler modules.
"""

from .count_handler import handle_count
from .pick_handler import handle_pick
from .receive_handler import handle_receive

__all__ = (
    "handle_receive",
    "handle_count",
    "handle_pick",
)
