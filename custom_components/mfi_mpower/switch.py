"""Outlet switches for mFi mPower."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MPowerConfigEntry
from .api import MPowerError
from .entity import MPowerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MPowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data
    async_add_entities(
        MPowerSwitch(client, entry.entry_id, port, "output", f"Outlet {port}")
        for port in sorted(client.ports)
    )


class MPowerSwitch(MPowerEntity, SwitchEntity):
    """Relay of one outlet."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    @property
    def is_on(self) -> bool | None:
        value = self._data.get("output")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        try:
            await self._client.set_output(self._port, on)
        except MPowerError as err:
            raise HomeAssistantError(f"Cannot switch outlet {self._port}: {err}") from err
