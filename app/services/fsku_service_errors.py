# app/services/fsku_service_errors.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class FskuNotFound(Exception):
    pass


class FskuConflict(Exception):
    pass


@dataclass
class FskuBadInput(Exception):
    details: list[dict[str, Any]]
