"""Constants for the Powervault integration."""

from typing import Final

DOMAIN = "powervault"
MANUFACTURER = "Powervault"

POWERVAULT_BASE_INFO: Final = "base_info"
POWERVAULT_COORDINATOR: Final = "coordinator"
POWERVAULT_API: Final = "api_instance"
POWERVAULT_MANAGER: Final = "manager"
POWERVAULT_API_CHANGED: Final = "api_changed"
POWERVAULT_HTTP_SESSION: Final = "http_session"

UPDATE_INTERVAL = 30

CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PLATFORM: Final = "platform"
CONF_ENABLE_DETAILED_BATTERY_TELEMETRY: Final = "enable_detailed_battery_telemetry"
DEFAULT_POLL_INTERVAL: Final = 30
MIN_POLL_INTERVAL: Final = 10
MAX_POLL_INTERVAL: Final = 60
DEFAULT_ENABLE_DETAILED_BATTERY_TELEMETRY: Final = False

CONF_MODEL: Final = "model"
CONF_IP_ADDRESS: Final = "ip_address"
CONF_USE_API_HISTORY: Final = "use_api_history"

MODEL_LEGACY_P3: Final = "legacy_p3"
MODEL_NEWER: Final = "newer"
MODEL_UNKNOWN: Final = "unknown"

LEGACY_PLATFORM_P3: Final = "p3"
LEGACY_PLATFORM_P3X: Final = "p3x"
LEGACY_PLATFORMS: Final = (LEGACY_PLATFORM_P3, LEGACY_PLATFORM_P3X)
