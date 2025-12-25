# app/services/outbound_metrics_v2_common.py
from __future__ import annotations

from datetime import timezone

UTC = timezone.utc

PICK_REASONS = ("PICK", "OUTBOUND_SHIP", "OUTBOUND_V2_SHIP", "SHIP")
