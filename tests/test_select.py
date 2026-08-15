"""Tests for the room-EQ select."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from arcam.fmj.codecs import RoomEqMode
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import push_update

ENTITY = "select.sdr_35_room_eq"


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: ENTITY, ATTR_OPTION: option},
        blocking=True,
    )


async def test_options_use_slot_names(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Options are Off plus the named slots, with a fallback for unnamed ones."""
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.attributes[ATTR_OPTIONS] == ["Off", "Cinema", "Music", "EQ 3"]
    assert state.state == "Cinema"


async def test_states(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Off, unknown, not-calculated and unexpected modes are all handled."""
    mock_client, mock_state = mock_library

    mock_state.get_room_equalization.return_value = RoomEqMode.OFF
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).state == "Off"

    mock_state.get_room_equalization.return_value = RoomEqMode.NOT_CALCULATED
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).state == "unknown"

    mock_state.get_room_equalization.return_value = None
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).state == "unknown"

    # A value outside the known modes (future firmware) reads as unknown.
    mock_state.get_room_equalization.return_value = RoomEqMode.from_int(0x0F)
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).state == "unknown"


async def test_fallback_names_without_report(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Before the receiver reports slot names, generic labels are used."""
    mock_client, mock_state = mock_library
    mock_state.get_room_eq_names.return_value = None
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).attributes[ATTR_OPTIONS] == [
        "Off",
        "EQ 1",
        "EQ 2",
        "EQ 3",
    ]


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("Off", RoomEqMode.OFF),
        ("Cinema", RoomEqMode.EQ1),
        ("Music", RoomEqMode.EQ2),
        ("EQ 3", RoomEqMode.EQ3),
    ],
)
async def test_select_option(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
    option: str,
    expected: RoomEqMode,
) -> None:
    """Choosing a preset sends the matching mode."""
    _, mock_state = mock_library
    await _select(hass, option)
    mock_state.set_room_equalization.assert_awaited_with(expected)


async def test_select_invalid_option(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """An option that is not a preset is rejected by the select service."""
    with pytest.raises(ServiceValidationError):
        await _select(hass, "Concert")
