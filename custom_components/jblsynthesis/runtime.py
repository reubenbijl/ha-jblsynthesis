"""Connection runtime for the JBL Synthesis integration.

Unlike a polled device there is no DataUpdateCoordinator here: the receiver holds a
persistent TCP connection, the arcam-fmj library runs its own update loop over it, and
every received frame updates the library's State. This runtime owns that connection,
keeps it alive, and fans out a dispatcher signal so entities re-read the State whenever
anything arrives.
"""

from __future__ import annotations

import asyncio
import logging

from arcam.fmj.client import Client
from arcam.fmj.errors import ArcamException, ConnectionFailed, NotConnectedException
from arcam.fmj.packets import AmxDuetResponse, ResponsePacket
from arcam.fmj.state import State
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONNECT_TIMEOUT, DOMAIN, RECONNECT_INTERVAL

_LOGGER = logging.getLogger(__name__)

type JBLSynthesisConfigEntry = ConfigEntry[JBLSynthesisRuntime]


class JBLSynthesisRuntime:
    """Own the TCP connection and library state for one receiver."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: JBLSynthesisConfigEntry,
        client: Client,
        state: State,
    ) -> None:
        """Initialise the runtime."""
        self.hass = hass
        self.entry = entry
        self.client = client
        self.state = state

    @property
    def signal(self) -> str:
        """Dispatcher signal fired whenever entity state may have changed."""
        return f"{DOMAIN}_{self.entry.entry_id}"

    @property
    def connected(self) -> bool:
        """Return whether the receiver connection is currently up."""
        return self.client.connected

    async def async_connect(self) -> None:
        """Make the first connection and attach the library state.

        Raises the library's connection errors on failure; the caller maps them to
        ConfigEntryNotReady so Home Assistant retries setup with backoff — which is
        exactly right for a receiver that leaves the network in deep standby.
        """
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await self.client.start()
        await self.state.start()

    @callback
    def async_start(self) -> None:
        """Start the background task that services and maintains the connection."""
        self.entry.async_create_background_task(
            self.hass, self._run(), name=f"{DOMAIN} connection {self.entry.title}"
        )

    async def _run(self) -> None:
        """Service the connection, reconnecting with a fixed delay when it drops.

        The task lives for the config entry's lifetime; Home Assistant cancels it on
        unload because it was created with async_create_background_task.
        """
        with self.client.listen(self._on_packet):
            while True:
                try:
                    await self.client.process()
                except (ConnectionFailed, NotConnectedException, OSError) as err:
                    _LOGGER.debug("Connection error: %s", err)
                await self.client.stop()
                # Silver log-when-unavailable: once on the way down...
                _LOGGER.warning(
                    "Connection to %s lost, retrying every %d seconds",
                    self.client.host,
                    int(RECONNECT_INTERVAL),
                )
                async_dispatcher_send(self.hass, self.signal)
                while True:
                    await asyncio.sleep(RECONNECT_INTERVAL)
                    try:
                        async with asyncio.timeout(CONNECT_TIMEOUT):
                            await self.client.start()
                    except (ConnectionFailed, OSError, TimeoutError, ArcamException):
                        continue
                    break
                # ...and once on recovery.
                _LOGGER.warning("Connection to %s re-established", self.client.host)
                async_dispatcher_send(self.hass, self.signal)

    @callback
    def _on_packet(self, packet: ResponsePacket | AmxDuetResponse) -> None:
        """Fan a received frame out to entities.

        The library's State has already recorded the packet by the time listeners run,
        so entities can simply re-read their properties.
        """
        async_dispatcher_send(self.hass, self.signal)

    async def async_shutdown(self) -> None:
        """Detach from the library and close the connection."""
        await self.state.stop()
        await self.client.stop()
