from __future__ import annotations

# Thin facade exports

from app.services.oauth_unified_service import UnifiedOAuthService
from app.services.oauth_unified_types import (
    PLATFORM_CONFIGS,
    Platform,
    PlatformOAuthConfig,
    PlatformOAuthError,
    load_credentials,
)

__all__ = [
    "Platform",
    "PlatformOAuthError",
    "PlatformOAuthConfig",
    "PLATFORM_CONFIGS",
    "load_credentials",
    "UnifiedOAuthService",
]
