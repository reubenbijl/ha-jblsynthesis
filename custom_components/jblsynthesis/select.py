"""Select entities for the JBL Synthesis integration."""

from __future__ import annotations

from arcam.fmj.codecs import RoomEqMode
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import JBLSynthesisEntity
from .runtime import JBLSynthesisConfigEntry, JBLSynthesisRuntime

# Push integration: received frames drive updates, nothing is polled.
PARALLEL_UPDATES = 0

OPTION_OFF = "Off"

#: The three Dirac/room-EQ slots the receiver holds.
EQ_SLOTS = (RoomEqMode.EQ1, RoomEqMode.EQ2, RoomEqMode.EQ3)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JBLSynthesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entities."""
    async_add_entities([JBLSynthesisRoomEqSelect(entry.runtime_data)])


class JBLSynthesisRoomEqSelect(JBLSynthesisEntity, SelectEntity):
    """Which room-equalisation (Dirac Live) preset is active.

    The receiver stores up to three calibration slots with user-assigned names; the
    options carry those names once the receiver has reported them.
    """

    _attr_translation_key = "room_eq"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, runtime: JBLSynthesisRuntime) -> None:
        """Initialise the select."""
        super().__init__(runtime)
        self._attr_unique_id = f"{self.device_identifier}_room_eq"

    def _slot_names(self) -> list[str]:
        """Return a display name per EQ slot, falling back to generic labels.

        The receiver truncates long names to 20 characters, which can leave two
        slots reading identically (seen in the wild with two "Dirac Live Room
        C..." slots), so duplicates get the slot number appended — options must
        stay distinct for selection to be able to target every slot.
        """
        names = self.runtime.state.get_room_eq_names() or []
        labels: list[str] = []
        for index in range(len(EQ_SLOTS)):
            name = names[index] if index < len(names) else ""
            label = name or f"EQ {index + 1}"
            if label in labels:
                label = f"{label} ({index + 1})"
            labels.append(label)
        return labels

    @property
    def options(self) -> list[str]:
        """Return off plus the named calibration slots."""
        return [OPTION_OFF, *self._slot_names()]

    @property
    def current_option(self) -> str | None:
        """Return the active preset, or None when unknown or not calculated."""
        mode = self.runtime.state.get_room_equalization()
        if mode is None or mode == RoomEqMode.NOT_CALCULATED:
            return None
        if mode == RoomEqMode.OFF:
            return OPTION_OFF
        try:
            slot = EQ_SLOTS.index(mode)
        except ValueError:
            return None
        return self._slot_names()[slot]

    async def async_select_option(self, option: str) -> None:
        """Activate a preset, or turn room EQ off.

        Home Assistant's select service has already validated the option against
        ``options``, so anything here is either off or one of the slot names.
        """
        if option == OPTION_OFF:
            mode = RoomEqMode.OFF
        else:
            mode = EQ_SLOTS[self._slot_names().index(option)]
        await self._async_call(self.runtime.state.set_room_equalization(mode))
