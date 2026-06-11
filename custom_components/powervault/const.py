"""Constants for the Powervault integration."""

from typing import Final

DOMAIN = "powervault"
MANUFACTURER = "Powervault"

POWERVAULT_BASE_INFO: Final = "base_info"
POWERVAULT_COORDINATOR: Final = "coordinator"
POWERVAULT_API: Final = "api_instance"
POWERVAULT_API_CHANGED: Final = "api_changed"
POWERVAULT_HTTP_SESSION: Final = "http_session"

UPDATE_INTERVAL = 30

CONF_MODEL: Final = "model"
CONF_IP_ADDRESS: Final = "ip_address"

MODEL_LEGACY_P3: Final = "legacy_p3"
MODEL_NEWER: Final = "newer"
MODEL_UNKNOWN: Final = "unknown"
