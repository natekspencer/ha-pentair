"""Support for Pentair sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import ATTR_ENTITY_ID, EntityCategory, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PentairConfigEntry
from .const import DOMAIN, SECRET_FIELDS
from .entity import PentairEntity
from .helpers import convert_timestamp, get_field_value

_LOGGER = logging.getLogger(__name__)

# Not imported from the recorder, which may not be loaded
RECORDER_DOMAIN = "recorder"

UNIT_MAP = {"kg": UnitOfMass.KILOGRAMS}


@dataclass(frozen=True, kw_only=True)
class PentairSensorEntityDescription(SensorEntityDescription):
    """Pentair sensor entity description."""

    value_fn: Callable[[dict], Any]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PentairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Pentair sensors using config entry."""
    coordinator = config_entry.runtime_data
    await _async_remove_secret_entities(hass, config_entry)

    entities: list[PentairSensorEntity] = []
    for device_coordinator in coordinator.device_coordinators:
        if data := device_coordinator.get_device_data():
            entities.append(
                PentairSensorEntity(
                    coordinator=device_coordinator,
                    config_entry=config_entry,
                    description=PentairSensorEntityDescription(
                        key="last_report",
                        device_class=SensorDeviceClass.TIMESTAMP,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        translation_key="last_report",
                        value_fn=lambda data: (
                            convert_timestamp(ts)
                            if (ts := data.get("delivered"))
                            else None
                        ),
                    ),
                    device_id=data["deviceId"],
                )
            )
            for field, field_data in data.get("fields", {}).items():
                if field in SECRET_FIELDS:
                    continue
                if not isinstance(field_data, dict):
                    continue
                unit = UNIT_MAP.get(field_data.get("unit"))
                entity_description = PentairSensorEntityDescription(
                    key=field,
                    name=(field_data.get("name") or field).strip().capitalize(),
                    entity_category=(
                        None
                        if field_data.get("category") == "data"
                        else EntityCategory.DIAGNOSTIC
                    ),
                    native_unit_of_measurement=unit,
                    state_class=SensorStateClass.MEASUREMENT if unit else None,
                    translation_key=field,
                    value_fn=lambda data, field=field: get_field_value(field, data),
                )
                entities.append(
                    PentairSensorEntity(
                        coordinator=device_coordinator,
                        config_entry=config_entry,
                        description=entity_description,
                        device_id=data["deviceId"],
                    )
                )

    if not entities:
        return

    async_add_entities(entities)


async def _async_remove_secret_entities(
    hass: HomeAssistant, config_entry: PentairConfigEntry
) -> None:
    """Remove sensors created for secret fields by earlier versions.

    Checked against the registry rather than the device payload, so they are
    removed even if a device no longer reports the field. Their recorded
    history is purged too, as removing an entity doesn't remove its states.
    """
    entity_registry = er.async_get(hass)
    removed = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
        if entry.domain == SENSOR_DOMAIN
        and entry.platform == DOMAIN
        and entry.unique_id.rpartition("-")[2] in SECRET_FIELDS
    ]
    for entity_id in removed:
        entity_registry.async_remove(entity_id)

    if removed and hass.services.has_service(RECORDER_DOMAIN, "purge_entities"):
        _LOGGER.info("Purging recorded history of removed sensors: %s", removed)
        await hass.services.async_call(
            RECORDER_DOMAIN, "purge_entities", {ATTR_ENTITY_ID: removed}
        )


class PentairSensorEntity(PentairEntity, SensorEntity):
    """Pentair sensor entity."""

    entity_description: PentairSensorEntityDescription

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the value reported by the sensor."""
        if isinstance(device_data := self.get_device(), dict):
            return self.entity_description.value_fn(device_data)
        return None
