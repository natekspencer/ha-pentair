"""Pentair coordinator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from pypentair import Pentair

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.redact import async_redact_data
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, TO_REDACT
from .helpers import diff_data, is_auth_error

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = 30


async def _async_fetch(
    hass: HomeAssistant, func: Callable[..., Any], *args: Any
) -> Any:
    """Call the API, triggering reauth when the credentials are no longer valid."""
    try:
        return await hass.async_add_executor_job(func, *args)
    except Exception as err:  # pylint: disable=broad-except
        if is_auth_error(err):
            raise ConfigEntryAuthFailed(err) from err
        _LOGGER.exception("Unknown exception while updating Pentair data")
        raise UpdateFailed(err) from err


def _log_changes(message: str, *args: Any, old: Any, new: Any) -> None:
    """Debug log the changes between two payloads, without account identifiers."""
    if _LOGGER.isEnabledFor(logging.DEBUG):
        changes = diff_data(
            async_redact_data(old, TO_REDACT), async_redact_data(new, TO_REDACT)
        )
        _LOGGER.debug(message, *args, changes or "no changes")


class PentairDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: Pentair
    ) -> None:
        """Initialize."""
        self.api = client
        self.devices: dict[str, list[dict[str, Any]]] = {}
        self.device_coordinators: list[PentairDeviceDataUpdateCoordinator] = []

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def get_device(self, device_id: str) -> dict | None:
        """Get device by id."""
        return next(
            (
                device
                for device in self.devices.get("data", [])
                if device["deviceId"] == device_id
            ),
            None,
        )

    def get_devices(self, device_type: str | None = None) -> list[dict]:
        """Get device by id."""
        return [
            device
            for device in self.devices.get("data", [])
            if device_type is None or device["deviceType"] == device_type
        ]

    async def _async_update_data(self):
        """Update data via library, refresh token if necessary."""
        if devices := await _async_fetch(self.hass, self.api.get_devices):
            _log_changes("Devices updated: %s", old=self.devices, new=devices)
            self.devices = devices
        return self.devices


class PentairDeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the device endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Pentair,
        device_id: str,
    ) -> None:
        """Initialize."""
        self.api = client
        self.device_id = device_id

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def get_device_data(self) -> dict | None:
        """Get the device data."""
        if self.data and (data := self.data.get("data")):
            return data
        return None

    async def _async_update_data(self):
        """Update data via library, refresh token if necessary."""
        if device := await _async_fetch(self.hass, self.api.get_device, self.device_id):
            _log_changes(
                "Device %s updated: %s",
                "***" + self.device_id[-4:],
                old=self.data,
                new=device,
            )
            return device
        return None
