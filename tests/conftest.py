"""Shared fixtures for the JBL Synthesis integration tests.

Mocking happens at the arcam-fmj boundary rather than at the socket: the library has
its own protocol-level tests, so repeating them here would test the same code twice and
couple these tests to the wire format.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from arcam.fmj.client import Client
from arcam.fmj.codecs import (
    CompressionMode,
    ControlOption,
    DecodeModeMCH,
    DisplayOnTime,
    GeneralSetup,
    IncomingAudioConfig,
    IncomingAudioFormat,
    IncomingVideoAspectRatio,
    IncomingVideoColorspace,
    MenuLanguage,
    PowerOnOption,
    RoomEqMode,
    SourceCodes,
    VideoParameters,
)
from arcam.fmj.packets import AmxDuetResponse
from arcam.fmj.state import State
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jblsynthesis.const import CONF_MANUFACTURER, DOMAIN

HOST = "192.168.128.18"
PORT = 50000
UNIQUE_ID = "0011e0123456"

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading this custom integration in every test."""
    return


@pytest.fixture
def amx_response() -> AmxDuetResponse:
    """Return the receiver's AMX identification, as the SDR-35 reports it."""
    return AmxDuetResponse(
        {
            "Device-SDKClass": "Receiver",
            "Device-Make": "JBL",
            "Device-Model": "SDR-35",
            "Device-Revision": "2.05",
        }
    )


@pytest.fixture
def general_setup() -> GeneralSetup:
    """Return a decoded 0x29 block: Atmos from the BD input, renamed PIANO."""
    return GeneralSetup(
        source_name="PIANO",
        audio_format=IncomingAudioFormat.DOLBY_ATMOS,
        audio_config=IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_LR_LFE,
        sample_rate=48000,
        bitrate=768000,
        dialnorm=4,
        horizontal_resolution=3840,
        vertical_resolution=2160,
        refresh_rate=60,
        interlaced=False,
        aspect_ratio=IncomingVideoAspectRatio.ASPECT_16_9,
        colorspace=IncomingVideoColorspace.HDR10,
        compression=CompressionMode.OFF,
        balance=0,
        dts_dialogue_control=0,
        max_volume=83,
        max_on_volume=45,
        display_on_time=DisplayOnTime.ALWAYS_ON,
        control_option=ControlOption.IP,
        power_on_option=PowerOnOption.STANDBY,
        language=MenuLanguage.ENGLISH,
    )


@pytest.fixture
def video_parameters() -> VideoParameters:
    """Return decoded incoming video parameters."""
    return VideoParameters(
        horizontal_resolution=3840,
        vertical_resolution=2160,
        refresh_rate=60,
        interlaced=False,
        aspect_ratio=IncomingVideoAspectRatio.ASPECT_16_9,
        colorspace=IncomingVideoColorspace.HDR10,
    )


@pytest.fixture
def mock_state(
    general_setup: GeneralSetup, video_parameters: VideoParameters
) -> MagicMock:
    """Return a library State whose getters describe a receiver playing Atmos."""
    state = MagicMock(spec=State)
    state.model = "SDR-35"
    state.revision = "2.05"
    state.get_power.return_value = True
    state.get_volume.return_value = 45
    state.get_mute.return_value = False
    state.get_source.return_value = SourceCodes.BD
    state.get_source_list.return_value = [
        SourceCodes.CD,
        SourceCodes.BD,
        SourceCodes.AV,
        SourceCodes.UHD,
        SourceCodes.BT,
    ]
    state.get_decode_mode.return_value = DecodeModeMCH.LOGIC_16_IMMERSION
    state.get_decode_modes.return_value = [
        DecodeModeMCH.STEREO_DOWNMIX,
        DecodeModeMCH.MULTI_CHANNEL,
        DecodeModeMCH.DOLBY_D_EX_OR_DTS_ES,
        DecodeModeMCH.DOLBY_SURROUND,
        DecodeModeMCH.LOGIC_16_IMMERSION,
        DecodeModeMCH.AURO_MATIC_3D,
    ]
    state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.DOLBY_ATMOS,
        IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_LR_LFE,
    )
    state.get_incoming_audio_sample_rate.return_value = 48000
    state.get_general_setup.return_value = general_setup
    state.get_incoming_video_parameters.return_value = video_parameters
    state.get_room_eq_names.return_value = ["Cinema", "Music", ""]
    state.get_room_equalization.return_value = RoomEqMode.EQ1
    state.to_dict.return_value = {"POWER": True}
    return state


@pytest.fixture
def mock_client(amx_response: AmxDuetResponse) -> MagicMock:
    """Return a library Client that connects successfully and never disconnects."""
    client = MagicMock(spec=Client)
    client.host = HOST
    client.port = PORT
    client.connected = True

    async def _process_forever() -> None:
        await asyncio.Event().wait()

    client.process.side_effect = _process_forever
    client.request_raw.return_value = amx_response

    listeners: list[Callable[[object], None]] = []
    client.listeners = listeners

    @contextmanager
    def _listen(callback: Callable[[object], None]) -> Generator[MagicMock]:
        listeners.append(callback)
        try:
            yield client
        finally:
            listeners.remove(callback)

    client.listen = _listen
    return client


@pytest.fixture
def mock_library(
    mock_client: MagicMock, mock_state: MagicMock
) -> Generator[tuple[MagicMock, MagicMock]]:
    """Patch the arcam-fmj entry points everywhere the integration constructs them."""
    with (
        patch("custom_components.jblsynthesis.Client", return_value=mock_client),
        patch("custom_components.jblsynthesis.State", return_value=mock_state),
        patch(
            "custom_components.jblsynthesis.config_flow.Client",
            return_value=mock_client,
        ),
        patch(
            "custom_components.jblsynthesis.config_flow.get_uniqueid_from_host",
            return_value=UNIQUE_ID,
        ),
    ):
        yield mock_client, mock_state


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the receiver."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="SDR-35",
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_MODEL: "SDR-35",
            CONF_MANUFACTURER: "JBL",
        },
        unique_id=UNIQUE_ID,
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> MockConfigEntry:
    """Set up the integration with a mocked receiver."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


async def push_update(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Simulate a status frame arriving from the receiver."""
    for callback in mock_client.listeners:
        callback(None)
    await hass.async_block_till_done()
