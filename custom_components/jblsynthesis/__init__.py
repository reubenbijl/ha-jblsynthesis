"""The JBL Synthesis integration."""

from __future__ import annotations

from arcam.fmj.client import Client
from arcam.fmj.errors import ArcamException, ConnectionFailed, NotConnectedException
from arcam.fmj.state import State
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DEFAULT_PORT, ZONE
from .runtime import JBLSynthesisConfigEntry, JBLSynthesisRuntime

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: JBLSynthesisConfigEntry
) -> bool:
    """Set up a JBL Synthesis receiver from a config entry."""
    client = Client(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    state = State(client, ZONE)
    runtime = JBLSynthesisRuntime(hass, entry, client, state)

    try:
        await runtime.async_connect()
    except (
        ConnectionFailed,
        NotConnectedException,
        ArcamException,
        OSError,
        TimeoutError,
    ) as err:
        # In deep standby the receiver leaves the network entirely, so an unreachable
        # unit is expected; Home Assistant's setup retry picks it up when it wakes.
        raise ConfigEntryNotReady(
            f"Could not connect to the receiver at {entry.data[CONF_HOST]}: {err}"
        ) from err

    runtime.async_start()
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: JBLSynthesisConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
