"""The Pentair integration."""

from __future__ import annotations

import asyncio
import logging

from pypentair import Pentair

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_ID_TOKEN, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import (
    PentairDataUpdateCoordinator,
    PentairDeviceDataUpdateCoordinator,
)
from .helpers import is_auth_error

type PentairConfigEntry = ConfigEntry[PentairDataUpdateCoordinator]

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PentairConfigEntry) -> bool:
    """Set up Pentair from a config entry."""
    client = Pentair(
        username=entry.data.get(CONF_USERNAME),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        id_token=entry.data.get(CONF_ID_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )

    try:
        await hass.async_add_executor_job(client.get_auth)
    except Exception as ex:
        if is_auth_error(ex):
            raise ConfigEntryAuthFailed(ex) from ex
        raise ConfigEntryNotReady(ex) from ex

    coordinator = PentairDataUpdateCoordinator(
        hass=hass, config_entry=entry, client=client
    )
    await coordinator.async_config_entry_first_refresh()

    for device in coordinator.get_devices():
        device_coordinator = PentairDeviceDataUpdateCoordinator(
            hass=hass, config_entry=entry, client=client, device_id=device["deviceId"]
        )
        coordinator.device_coordinators.append(device_coordinator)

    await asyncio.gather(
        *(
            dc.async_config_entry_first_refresh()
            for dc in coordinator.device_coordinators
        )
    )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PentairConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: PentairConfigEntry) -> None:
    """Handle removal of an entry."""
    client = Pentair(
        username=entry.data.get(CONF_USERNAME),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        id_token=entry.data.get(CONF_ID_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )
    try:
        await hass.async_add_executor_job(client.logout)
    except Exception:
        _LOGGER.debug("Failed to logout during entry removal", exc_info=True)


async def async_migrate_entry(hass: HomeAssistant, entry: PentairConfigEntry) -> bool:
    """Migrate an old config entry."""
    if entry.version > 1:
        # Downgraded from a future version
        return False

    if entry.minor_version < 2:
        # 1.2: unique ID is the lowercased username instead of the domain
        unique_id = entry.data[CONF_USERNAME].lower()
        if any(
            other.unique_id == unique_id
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        ):
            _LOGGER.error(
                "Cannot migrate %s: another entry already uses this account",
                entry.title,
            )
            return False
        hass.config_entries.async_update_entry(
            entry, unique_id=unique_id, minor_version=2
        )

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: PentairConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    return not any(
        identifier
        for identifier in device_entry.identifiers
        if identifier[0] == DOMAIN
        for device in config_entry.runtime_data.get_devices()
        if identifier[1] == device["deviceId"]
    )
