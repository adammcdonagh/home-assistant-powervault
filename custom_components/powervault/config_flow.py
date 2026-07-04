"""Config flow for Powervault integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector
from powervaultpy import PowerVault
from powervaultpy.powervault import RequestError, ServerError

from .const import (
    CONF_ENABLE_DETAILED_BATTERY_TELEMETRY,
    CONF_IP_ADDRESS,
    CONF_MODEL,
    CONF_PLATFORM,
    CONF_POLL_INTERVAL,
    DEFAULT_ENABLE_DETAILED_BATTERY_TELEMETRY,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LEGACY_PLATFORM_P3,
    LEGACY_PLATFORMS,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    MODEL_LEGACY_P3,
    MODEL_NEWER,
)

_LOGGER = logging.getLogger(__name__)

STEP_MODEL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODEL): selector(
            {
                "select": {
                    "options": [
                        {"value": MODEL_LEGACY_P3, "label": "Legacy P3"},
                        {"value": MODEL_NEWER, "label": "Newer Powervault"},
                    ]
                }
            }
        ),
    }
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("api_key"): str,
    }
)

STEP_LEGACY_UNIT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
    }
)

STEP_PICK_UNIT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("unit_id"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    powervault = PowerVault(data["api_key"])

    account_id = None
    units = None

    try:
        account_response = await hass.async_add_executor_job(powervault.get_account)
        account_id = account_response["id"]
        units = await hass.async_add_executor_job(powervault.get_units, account_id)

    except RequestError as exc:
        raise InvalidAuth from exc
    except ServerError as exc:
        raise CannotConnect from exc

    units_ = []
    for unit in units:
        units_.append(unit["id"])

    # Return info that you want to store in the config entry.
    return {"units": units_, "account_id": account_id}


def _normalize_legacy_platform(platform: str | None) -> str:
    """Validate and normalize the reported legacy platform string."""
    if platform is None:
        raise CannotConnect

    if (normalized := platform.strip().lower()) not in LEGACY_PLATFORMS:
        raise CannotConnect

    return normalized


async def validate_legacy_unit(hass: HomeAssistant, ip_address: str) -> str:
    """Validate a legacy local unit and return its stored platform type."""
    client = PowerVault(local_ip=ip_address)
    try:
        response = await hass.async_add_executor_job(client.get_health)
        platform = await hass.async_add_executor_job(client.get_platform)
    except (RequestError, ServerError) as exc:
        raise CannotConnect from exc

    if response != {"status": "ok"}:
        raise CannotConnect

    return _normalize_legacy_platform(platform)


class PowervaultOptionsFlow(OptionsFlow):  # pylint: disable=too-few-public-methods
    """Handle options for Powervault (legacy P3 only)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the poll-interval option."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )
        current_detailed = self._config_entry.options.get(
            CONF_ENABLE_DETAILED_BATTERY_TELEMETRY,
            DEFAULT_ENABLE_DETAILED_BATTERY_TELEMETRY,
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_POLL_INTERVAL, default=current): selector(
                    {
                        "number": {
                            "min": MIN_POLL_INTERVAL,
                            "max": MAX_POLL_INTERVAL,
                            "step": 1,
                            "unit_of_measurement": "s",
                            "mode": "slider",
                        }
                    }
                ),
                vol.Required(
                    CONF_ENABLE_DETAILED_BATTERY_TELEMETRY,
                    default=current_detailed,
                ): selector({"boolean": {}}),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class PowervaultConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Powervault."""

    VERSION = 3

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> PowervaultOptionsFlow | None:
        """Return options flow only for legacy P3 entries."""
        if config_entry.data.get(CONF_MODEL) == MODEL_LEGACY_P3:
            return PowervaultOptionsFlow(config_entry)
        return None

    unit_id: str
    unit_name: str
    account_info: dict[str, Any]
    api_key: str
    model: str

    async def async_step_reauth(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication triggered when the stored model is unknown."""
        return await self.async_step_reauth_model()

    async def async_step_reauth_model(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask the user to identify their Powervault model."""
        if user_input is not None:
            self.model = user_input[CONF_MODEL]
            if self.model == MODEL_LEGACY_P3:
                return await self.async_step_reauth_legacy()
            # Newer unit — existing api_key / unit_id remain valid.
            entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_MODEL: MODEL_NEWER},
            )
            return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_model",
            data_schema=STEP_MODEL_DATA_SCHEMA,
        )

    async def async_step_reauth_legacy(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the IP address of the legacy P3 unit."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                platform = await validate_legacy_unit(
                    self.hass, user_input[CONF_IP_ADDRESS]
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_MODEL: MODEL_LEGACY_P3,
                        CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS],
                        CONF_PLATFORM: platform,
                    },
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_legacy",
            data_schema=STEP_LEGACY_UNIT_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - model selection."""
        if user_input is not None:
            self.model = user_input[CONF_MODEL]
            if self.model == MODEL_LEGACY_P3:
                return await self.async_step_legacy_unit()
            return await self.async_step_api_key()

        return self.async_show_form(step_id="user", data_schema=STEP_MODEL_DATA_SCHEMA)

    async def async_step_legacy_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle legacy P3 unit configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                platform = await validate_legacy_unit(
                    self.hass, user_input[CONF_IP_ADDRESS]
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=(
                        "Powervault P3"
                        if platform == LEGACY_PLATFORM_P3
                        else "Powervault P3X"
                    ),
                    data={
                        CONF_MODEL: MODEL_LEGACY_P3,
                        CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS],
                        CONF_PLATFORM: platform,
                    },
                )

        return self.async_show_form(
            step_id="legacy_unit",
            data_schema=STEP_LEGACY_UNIT_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle API key entry for newer Powervault units."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.account_info = info
                self.api_key = user_input["api_key"]
                data_schema = {
                    vol.Required("unit_name"): str,
                }
                data_schema["unit_id"] = selector(
                    {
                        "select": {
                            "options": info["units"],
                        }
                    }
                )

                return self.async_show_form(
                    step_id="pick_unit", data_schema=vol.Schema(data_schema)
                )

        return self.async_show_form(
            step_id="api_key", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_pick_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # Save the picked unit id
            self.unit_id = user_input["unit_id"]
            self.unit_name = user_input["unit_name"]

            # Now we can create the entity

            return self.async_create_entry(
                title=f"Powervault - {self.unit_name}",
                data={
                    CONF_MODEL: MODEL_NEWER,
                    "api_key": self.api_key,
                    "unit_id": self.unit_id,
                },
            )


class CannotConnect(HomeAssistantError):  # pylint: disable=too-few-public-methods
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):  # pylint: disable=too-few-public-methods
    """Error to indicate there is invalid auth."""
