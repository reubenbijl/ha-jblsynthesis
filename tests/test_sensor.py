"""Tests for the JBL Synthesis sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

import attr
from arcam.fmj.codecs import (
    IncomingAudioConfig,
    IncomingAudioFormat,
    IncomingVideoColorspace,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jblsynthesis.sensor import _audio_format

from .conftest import push_update


async def test_sensor_values(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """All sensors reflect the Atmos stream from the fixtures."""
    assert hass.states.get("sensor.sdr_35_audio_format").state == "Dolby Atmos"
    assert hass.states.get("sensor.sdr_35_input_name").state == "PIANO"
    assert (
        hass.states.get("sensor.sdr_35_incoming_video").state == "3840x2160p60 (HDR10)"
    )
    assert hass.states.get("sensor.sdr_35_sample_rate").state == "48.0"
    assert hass.states.get("sensor.sdr_35_bitrate").state == "768.0"
    assert hass.states.get("sensor.sdr_35_dialogue_normalisation").state == "4"


async def test_audio_format_combinations(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """The format sensor words streams the way the front panel does."""
    mock_client, mock_state = mock_library
    sensor = "sensor.sdr_35_audio_format"

    mock_state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.DTS_HD_MASTER_AUDIO,
        IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_LR_LFE,
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "DTS-HD Master Audio 3/4.1"

    mock_state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.AURO_3D,
        IncomingAudioConfig.AURO_11_1,
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "Auro 11.1"

    # A channel configuration the label table does not know: format alone.
    mock_state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.PCM,
        IncomingAudioConfig.UNKNOWN,
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "PCM"

    mock_state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.UNDETECTED,
        IncomingAudioConfig.UNDETECTED,
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "unknown"

    mock_state.get_incoming_audio_format.return_value = (None, None)
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "unknown"


def test_audio_format_unmapped_format() -> None:
    """A format byte the enum has no member for still renders."""
    state = MagicMock()
    state.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.from_int(0x11),
        IncomingAudioConfig.STEREO_ONLY,
    )
    assert _audio_format(state) == "Code_17 2.0"


async def test_video_variants(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Interlaced, SDR and absent video are all represented."""
    mock_client, mock_state = mock_library
    sensor = "sensor.sdr_35_incoming_video"
    video = mock_state.get_incoming_video_parameters.return_value

    mock_state.get_incoming_video_parameters.return_value = attr.evolve(
        video,
        horizontal_resolution=1920,
        vertical_resolution=1080,
        refresh_rate=50,
        interlaced=True,
        colorspace=None,
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "1920x1080i50"

    mock_state.get_incoming_video_parameters.return_value = attr.evolve(
        video, colorspace=IncomingVideoColorspace.DOLBY_VISION
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "3840x2160p60 (Dolby Vision)"

    mock_state.get_incoming_video_parameters.return_value = attr.evolve(
        video, horizontal_resolution=0
    )
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "unknown"

    mock_state.get_incoming_video_parameters.return_value = None
    await push_update(hass, mock_client)
    assert hass.states.get(sensor).state == "unknown"


async def test_general_setup_absent(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Sensors fed by 0x29 read unknown before the first block arrives."""
    mock_client, mock_state = mock_library
    mock_state.get_general_setup.return_value = None
    await push_update(hass, mock_client)

    assert hass.states.get("sensor.sdr_35_input_name").state == "unknown"
    assert hass.states.get("sensor.sdr_35_bitrate").state == "unknown"
    assert hass.states.get("sensor.sdr_35_dialogue_normalisation").state == "unknown"


async def test_symbolic_bitrate_and_blank_name(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_library: tuple[MagicMock, MagicMock],
) -> None:
    """Symbolic bitrates and an unnamed input read as unknown."""
    mock_client, mock_state = mock_library
    setup = mock_state.get_general_setup.return_value
    mock_state.get_general_setup.return_value = attr.evolve(
        setup, bitrate="lossless", source_name=""
    )
    await push_update(hass, mock_client)

    assert hass.states.get("sensor.sdr_35_bitrate").state == "unknown"
    assert hass.states.get("sensor.sdr_35_input_name").state == "unknown"
