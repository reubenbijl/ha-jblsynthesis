"""Switch entities for the JBL Synthesis integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import JBLSynthesisEntity
from .runtime import JBLSynthesisConfigEntry, JBLSynthesisRuntime

# Push integration: received frames drive updates, nothing is polled.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JBLSynthesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch entities."""
    async_add_entities([JBLSynthesisConnectionSwitch(entry.runtime_data)])


class JBLSynthesisConnectionSwitch(JBLSynthesisEntity, SwitchEntity):
    """Whether this integration holds the receiver's control connection.

    The receiver accepts a single controller at a time. Turning this off releases the
    connection so another tool — typically Dirac Live during calibration — can reach
    the unit; turning it back on reconnects, and the state refreshes itself from the
    library's update cycle.
    """

    _attr_translation_key = "connection"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, runtime: JBLSynthesisRuntime) -> None:
        """Initialise the switch."""
        super().__init__(runtime)
        self._attr_unique_id = f"{self.device_identifier}_connection"

    @property
    def available(self) -> bool:
        """The switch is always available.

        Every other entity goes unavailable while the connection is released; this one
        must not, or there would be no way to retake the connection.
        """
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the connection is held."""
        return self.runtime.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Retake the control connection."""
        await self.runtime.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Release the control connection for external tools such as Dirac Live."""
        await self.runtime.async_set_enabled(False)
        self.async_write_ha_state()
