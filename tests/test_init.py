"""Tests for JBL Synthesis setup, unload and reconnection."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from arcam.fmj.errors import ConnectionFailed
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import push_update


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """The entry connects on setup and disconnects on unload."""
    mock_client, mock_state = mock_library
    assert init_integration.state is ConfigEntryState.LOADED
    mock_client.start.assert_awaited_once()
    mock_state.start.assert_awaited_once()

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_state.stop.assert_awaited()
    mock_client.stop.assert_awaited()


@pytest.mark.parametrize("error", [ConnectionFailed(), TimeoutError(), OSError()])
async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
    error: Exception,
) -> None:
    """An unreachable receiver (deep standby) defers setup for retry."""
    mock_client, _ = mock_library
    mock_client.start.side_effect = error

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_reconnects_after_connection_loss(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dropped connection is retried until the receiver answers again."""
    from custom_components.jblsynthesis import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "RECONNECT_INTERVAL", 0.01)

    mock_client, _ = mock_library
    reconnected = asyncio.Event()
    process_calls = []

    async def _process() -> None:
        if not process_calls:
            process_calls.append(1)
            raise ConnectionFailed
        reconnected.set()
        await asyncio.Event().wait()

    # First process call dies, first reconnect attempt fails, second succeeds.
    mock_client.process.side_effect = _process
    mock_client.start.side_effect = [None, ConnectionFailed(), None]

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    async with asyncio.timeout(5):
        await reconnected.wait()

    assert mock_client.start.await_count == 3
    assert "Connection to 192.168.128.18 lost" in caplog.text
    assert "Connection to 192.168.128.18 re-established" in caplog.text


async def test_immediate_reconnect_is_not_an_outage(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A drop the receiver hands straight back never warns about availability.

    Home Assistant's startup congestion stalls the event loop past the library's
    read timeout often enough that this is the common case, and it self-heals in
    milliseconds — warning about it would cry wolf at every restart.
    """
    mock_client, _ = mock_library
    reconnected = asyncio.Event()
    process_calls = []

    async def _process() -> None:
        if not process_calls:
            process_calls.append(1)
            raise ConnectionFailed("Missed all pings")
        reconnected.set()
        await asyncio.Event().wait()

    mock_client.process.side_effect = _process

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    async with asyncio.timeout(5):
        await reconnected.wait()

    assert mock_client.start.await_count == 2
    assert "lost" not in caplog.text
    assert "Missed all pings" in caplog.text


async def test_entities_track_connection_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Entities become unavailable while the connection is down."""
    mock_client, _ = mock_library
    assert hass.states.get("media_player.sdr_35").state != "unavailable"

    mock_client.connected = False
    await push_update(hass, mock_client)
    assert hass.states.get("media_player.sdr_35").state == "unavailable"

    mock_client.connected = True
    await push_update(hass, mock_client)
    assert hass.states.get("media_player.sdr_35").state != "unavailable"
