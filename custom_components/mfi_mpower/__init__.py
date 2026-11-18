"""Ubiquiti mFi mPower integration (local websocket push)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MPowerClient
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL

PLATFORMS = [Platform.SWITCH, Platform.SENSOR]

type MPowerConfigEntry = ConfigEntry[MPowerClient]


async def async_setup_entry(hass: HomeAssistant, entry: MPowerConfigEntry) -> bool:
    """Connect to the mPower and set up its entities."""
    client = MPowerClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )
    client.start()
    if not await client.wait_for_data(30):
        await client.stop()
        raise ConfigEntryNotReady(f"no data from mPower at {entry.data[CONF_HOST]}")

    entry.runtime_data = client
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MPowerConfigEntry) -> bool:
    """Disconnect and remove entities."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: MPowerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
