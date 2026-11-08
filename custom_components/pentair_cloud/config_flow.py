"""Pentair config flow."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from pypentair import Pentair, PentairAuthenticationError
import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class PentairConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pentair."""

    VERSION = 1
    MINOR_VERSION = 2

    async def _async_create_entry(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry, or update it when reauthenticating."""
        config_data = {k: v for k, v in user_input.items() if k != CONF_PASSWORD}

        await self.async_set_unique_id(config_data[CONF_USERNAME].lower())

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=config_data
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=config_data[CONF_USERNAME], data=config_data
        )

    async def async_pentair_login(
        self, step_id: str, user_input: dict[str, Any], schema: vol.Schema
    ) -> ConfigFlowResult:
        """Attempt a login with Pentair."""
        errors = {}

        pentair = Pentair(username=user_input[CONF_USERNAME])
        try:
            await self.hass.async_add_executor_job(
                pentair.authenticate, user_input[CONF_PASSWORD]
            )
        except PentairAuthenticationError:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        if not errors:
            return await self._async_create_entry(user_input | pentair.get_tokens())

        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            return await self.async_pentair_login(
                step_id="user", user_input=user_input, schema=STEP_USER_DATA_SCHEMA
            )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            user_input = {}

        reauth_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=user_input.get(
                        CONF_USERNAME, self._get_reauth_entry().data.get(CONF_USERNAME)
                    ),
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        if user_input.get(CONF_PASSWORD) is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=reauth_schema
            )

        return await self.async_pentair_login(
            step_id="reauth_confirm", user_input=user_input, schema=reauth_schema
        )
