"""Tests for JBL Synthesis diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

from arcam.fmj.codecs import IncomingAudioFormat, SourceCodes
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
    general_setup,
) -> None:
    """The download redacts the host and serialises library values."""
    _, mock_state = mock_library
    mock_state.to_dict.return_value = {
        "POWER": True,
        "VOLUME": 45,
        "SOURCE": SourceCodes.BD,
        "INCOMING_AUDIO_FORMAT": (IncomingAudioFormat.DOLBY_ATMOS, None),
        "GENERAL_SETUP": general_setup,
        "RAW": b"\x21\x01",
        "NESTED": {"names": ["Cinema", None]},
        "OTHER": complex(1, 2),
    }

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    assert diagnostics["entry"]["host"] == "**REDACTED**"
    assert diagnostics["entry"]["model"] == "SDR-35"
    assert diagnostics["connected"] is True
    assert diagnostics["model"] == "SDR-35"
    assert diagnostics["revision"] == "2.05"

    state = diagnostics["state"]
    assert state["POWER"] is True
    assert state["VOLUME"] == 45
    assert state["SOURCE"] == "BD"
    assert state["INCOMING_AUDIO_FORMAT"] == ["DOLBY_ATMOS", None]
    assert state["GENERAL_SETUP"]["source_name"] == "PIANO"
    assert state["GENERAL_SETUP"]["audio_format"] == "DOLBY_ATMOS"
    assert state["RAW"] == "21 01"
    assert state["NESTED"] == {"names": ["Cinema", None]}
    assert state["OTHER"] == "(1+2j)"
