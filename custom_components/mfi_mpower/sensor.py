"""Power / energy sensors for mFi mPower."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MPowerConfigEntry
from .entity import MPowerEntity


@dataclass(frozen=True, kw_only=True)
class MPowerSensorDescription(SensorEntityDescription):
    field: str
    label: str


SENSORS: tuple[MPowerSensorDescription, ...] = (
    MPowerSensorDescription(
        key="power",
        field="power",
        label="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
    ),
    MPowerSensorDescription(
        key="current",
        field="current",
        label="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=3,
    ),
    MPowerSensorDescription(
        key="voltage",
        field="voltage",
        label="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    MPowerSensorDescription(
        key="power_factor",
        field="powerfactor",
        label="power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    MPowerSensorDescription(
        key="energy",
        field="energy",
        label="energy",
        device_class=SensorDeviceClass.ENERGY,
        # Counter lives in RAM on the device and restarts at 0 after a reboot.
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MPowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data
    async_add_entities(
        MPowerSensor(client, entry.entry_id, port, desc)
        for port in sorted(client.ports)
        for desc in SENSORS
    )


class MPowerSensor(MPowerEntity, SensorEntity):
    """One reading of one outlet."""

    entity_description: MPowerSensorDescription

    def __init__(self, client, entry_id, port, desc: MPowerSensorDescription) -> None:
        super().__init__(client, entry_id, port, desc.key, f"Outlet {port} {desc.label}")
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        value = self._data.get(self.entity_description.field)
        return None if value is None else round(float(value), 4)
