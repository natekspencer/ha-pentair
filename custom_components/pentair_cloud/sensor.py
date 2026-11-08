"""Support for Pentair sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PentairConfigEntry
from .const import DOMAIN, SECRET_FIELDS
from .entity import PentairEntity
from .helpers import convert_timestamp, get_field_value

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
                    _async_remove_secret_entity(hass, data["deviceId"], field)
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


def _async_remove_secret_entity(
    hass: HomeAssistant, device_id: str, field: str
) -> None:
    """Remove a sensor created for a secret field by an earlier version."""
    entity_registry = er.async_get(hass)
    if entity_id := entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{device_id}-{field}"
    ):
        entity_registry.async_remove(entity_id)


class PentairSensorEntity(PentairEntity, SensorEntity):
    """Pentair sensor entity."""

    entity_description: PentairSensorEntityDescription

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the value reported by the sensor."""
        if isinstance(device_data := self.get_device(), dict):
            return self.entity_description.value_fn(device_data)
        return None
