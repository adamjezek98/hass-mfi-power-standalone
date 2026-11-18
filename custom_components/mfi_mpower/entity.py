"""Shared entity base for mFi mPower."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .api import MPowerClient
from .const import DOMAIN


class MPowerEntity(Entity):
    """An entity bound to one outlet of an mPower strip."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, client: MPowerClient, entry_id: str, port: int, key: str, name: str
    ) -> None:
        self._client = client
        self._port = port
        self._attr_unique_id = f"{entry_id}_{port}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"mPower {client.host}",
            manufacturer="Ubiquiti",
            model=f"mFi mPower ({len(client.ports)} outlets)",
            configuration_url=f"http://{client.host}/",
        )

    @property
    def _data(self) -> dict[str, Any]:
        return self._client.ports.get(self._port, {})

    @property
    def available(self) -> bool:
        return self._client.connected and bool(self._data)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self.async_write_ha_state))
