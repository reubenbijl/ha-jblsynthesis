"""Tests for the JBL Synthesis media player."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from arcam.fmj.codecs import DecodeMode2CH, DecodeModeMCH, SourceCodes
from arcam.fmj.errors import ArcamException
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE,
    ATTR_SOUND_MODE_LIST,
    SERVICE_SELECT_SOUND_MODE,
    SERVICE_SELECT_SOURCE,
)
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jblsynthesis.media_player import (
    _decode_mode_label,
    _source_label,
)

from .conftest import push_update

ENTITY = "media_player.sdr_35"


async def _call(hass: HomeAssistant, service: str, data: dict | None = None) -> None:
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY, **(data or {})},
        blocking=True,
    )


async def test_state_and_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The player reflects the receiver playing Atmos on the PIANO input."""
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "on"
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == pytest.approx(45 / 99)
    assert state.attributes[ATTR_MEDIA_VOLUME_MUTED] is False
    assert state.attributes[ATTR_INPUT_SOURCE] == "BD"
    assert state.attributes[ATTR_INPUT_SOURCE_LIST] == [
        "CD",
        "BD",
        "AV",
        "UHD",
        "Bluetooth",
    ]
    assert state.attributes[ATTR_SOUND_MODE] == "Logic 16 Immersion"
    assert "DTS Neural:X" in state.attributes[ATTR_SOUND_MODE_LIST]
    assert state.attributes["device_class"] == "receiver"


async def test_standby_and_unknown_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Standby and not-yet-received values map to standby/unknown."""
    mock_client, mock_state = mock_library

    mock_state.get_power.return_value = False
    await push_update(hass, mock_client)
    assert hass.states.get(ENTITY).state == "standby"

    mock_state.get_power.return_value = None
    mock_state.get_volume.return_value = None
    mock_state.get_source.return_value = None
    mock_state.get_decode_mode.return_value = None
    mock_state.get_decode_modes.return_value = []
    await push_update(hass, mock_client)

    state = hass.states.get(ENTITY)
    assert state.state == "unknown"
    assert ATTR_MEDIA_VOLUME_LEVEL not in state.attributes
    assert ATTR_INPUT_SOURCE not in state.attributes
    assert ATTR_SOUND_MODE not in state.attributes
    assert ATTR_SOUND_MODE_LIST not in state.attributes


async def test_commands(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Every control maps to the right library call."""
    _, mock_state = mock_library

    await _call(hass, SERVICE_TURN_ON)
    mock_state.set_power.assert_awaited_with(True)

    await _call(hass, SERVICE_TURN_OFF)
    mock_state.set_power.assert_awaited_with(False)

    await _call(hass, SERVICE_VOLUME_SET, {ATTR_MEDIA_VOLUME_LEVEL: 45 / 99})
    mock_state.set_volume.assert_awaited_with(45)

    await _call(hass, SERVICE_VOLUME_UP)
    mock_state.inc_volume.assert_awaited_once()

    await _call(hass, SERVICE_VOLUME_DOWN)
    mock_state.dec_volume.assert_awaited_once()

    await _call(hass, SERVICE_VOLUME_MUTE, {ATTR_MEDIA_VOLUME_MUTED: True})
    mock_state.set_mute.assert_awaited_with(True)

    await _call(hass, SERVICE_SELECT_SOURCE, {ATTR_INPUT_SOURCE: "UHD"})
    mock_state.set_source.assert_awaited_with(SourceCodes.UHD)

    await _call(
        hass, SERVICE_SELECT_SOUND_MODE, {ATTR_SOUND_MODE: "Logic 16 Immersion"}
    )
    mock_state.set_decode_mode.assert_awaited_with(DecodeModeMCH.LOGIC_16_IMMERSION)


async def test_select_invalid_source(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """An unknown source is rejected before anything is sent."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SELECT_SOURCE, {ATTR_INPUT_SOURCE: "Phono"})
    assert err.value.translation_key == "invalid_source"


async def test_select_invalid_sound_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """A mode not valid for the current stream is rejected."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SELECT_SOUND_MODE, {ATTR_SOUND_MODE: "Stereo"})
    assert err.value.translation_key == "invalid_sound_mode"

    # Also when the mode list is not known at all yet.
    _, mock_state = mock_library
    mock_state.get_decode_modes.return_value = None
    with pytest.raises(ServiceValidationError):
        await _call(
            hass, SERVICE_SELECT_SOUND_MODE, {ATTR_SOUND_MODE: "Logic 16 Immersion"}
        )


async def test_command_failure_is_translated(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """A rejected command surfaces as a translated, never-blank error."""
    _, mock_state = mock_library
    mock_state.set_power.side_effect = ArcamException("rejected")

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, SERVICE_TURN_ON)
    assert err.value.translation_key == "command_failed"
    assert err.value.translation_placeholders["error"]


async def test_command_timeout_is_tolerated(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """A missing command echo is not an error on this firmware.

    The receiver executes RC5-simulated commands (input, mute, decode mode,
    power) without echoing the command frame; the status push that follows
    updates the entities, so the service call must succeed quietly.
    """
    _, mock_state = mock_library
    mock_state.set_power.side_effect = TimeoutError()

    await _call(hass, SERVICE_TURN_ON)


def test_label_fallbacks() -> None:
    """Members without a curated label fall back to a readable form."""
    assert _source_label(SourceCodes.PHONO) == "Phono"
    assert _decode_mode_label(DecodeMode2CH.DOLBY_PL) == "Dolby Pl"
