# tests/services/test_outbound_ledger_consistency.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.outbound import OutboundLine, OutboundMode
from app.services.outbound_service import OutboundService

UTC = timezone.utc

# [同你已通过的版本，此处略，保留使用 OutboundLine + commit/ begin 的结构]
# ……（此文件你已运行通过，无需再改）
