"""Tests for the control-connection switch."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import push_update

ENTITY = "switch.sdr_35_control_connection"
PLAYER = "media_player.sdr_35"


async def _call(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY}, blocking=True
    )


async def _wait_for_start_count(mock_client: MagicMock, count: int) -> None:
    """Yield to the event loop until the background task has reconnected."""
    for _ in range(20):
        if mock_client.start.await_count >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"client.start not awaited {count} times")


async def test_defaults(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The switch ships on, as a config entity."""
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "on"
    registry_entry = er.async_get(hass).async_get(ENTITY)
    assert registry_entry is not None
    assert registry_entry.entity_category is EntityCategory.CONFIG


async def test_release_and_retake(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Releasing frees the connection; retaking reconnects and state refreshes."""
    mock_client, _ = mock_library

    # Releasing stops the client, after which connected reads False; the runtime
    # dispatches once more so entities notice. Mirror that ordering here.
    mock_client.connected = False
    await _call(hass, SERVICE_TURN_OFF)
    await hass.async_block_till_done()
    mock_client.stop.assert_awaited()

    # The receiver is now another tool's: everything else is unavailable, but the
    # switch itself must stay reachable or the connection could never be retaken.
    assert hass.states.get(PLAYER).state == "unavailable"
    assert hass.states.get(ENTITY).state == "off"

    await _call(hass, SERVICE_TURN_ON)
    assert hass.states.get(ENTITY).state == "on"
    await _wait_for_start_count(mock_client, 2)

    mock_client.connected = True
    await push_update(hass, mock_client)
    assert hass.states.get(PLAYER).state != "unavailable"


async def test_toggle_is_idempotent(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Re-asserting the current state does nothing."""
    mock_client, _ = mock_library

    await _call(hass, SERVICE_TURN_ON)
    assert mock_client.start.await_count == 1

    await _call(hass, SERVICE_TURN_OFF)
    stop_count = mock_client.stop.await_count
    await _call(hass, SERVICE_TURN_OFF)
    assert mock_client.stop.await_count == stop_count


async def test_unload_while_released(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """The entry unloads cleanly while the connection is released."""
    _, mock_state = mock_library
    await _call(hass, SERVICE_TURN_OFF)

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_state.stop.assert_awaited()
