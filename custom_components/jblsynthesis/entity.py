"""Base entity for the JBL Synthesis integration."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from arcam.fmj.errors import ArcamException
from homeassistant.const import CONF_HOST, CONF_MODEL
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_MANUFACTURER, DEFAULT_MANUFACTURER, DOMAIN
from .runtime import JBLSynthesisRuntime


class JBLSynthesisEntity(Entity):
    """Common device wiring and error handling for every entity.

    This is a push integration: entities never poll. Every received frame fires the
    runtime's dispatcher signal, and entities simply re-read the library State.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: JBLSynthesisRuntime) -> None:
        """Initialise the entity."""
        self.runtime = runtime
        entry = runtime.entry
        # Device identity was captured from the AMX reply during the config flow, so it
        # is available even while the receiver itself is unreachable.
        self.device_identifier = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=entry.data.get(CONF_MANUFACTURER, DEFAULT_MANUFACTURER),
            model=entry.data.get(CONF_MODEL),
            name=entry.title,
            configuration_url=f"http://{entry.data[CONF_HOST]}/",
        )

    @property
    def available(self) -> bool:
        """Entities are unavailable whenever the connection is down.

        That includes deep standby, where the receiver leaves the network entirely.
        """
        return self.runtime.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to state pushes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self.runtime.signal, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Re-read the library state after a received frame."""
        self.async_write_ha_state()

    async def _async_call(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Send a command to the receiver.

        No refresh is needed afterwards: state changes flow back as status frames
        through the dispatcher. The library confirms each command from the state
        the receiver reports, because this firmware never echoes the RC5-simulated
        ones (input, mute, decode mode, power). So a timeout means the receiver did
        not do what was asked, such as an input it never switched to. That fails
        the service call, as a rejection with an answer code does, each as a
        HomeAssistantError with a translation key.
        """
        try:
            await coro
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_not_confirmed",
            ) from err
        except ArcamException as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                # Fall back to the type for exceptions that stringify to nothing.
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
