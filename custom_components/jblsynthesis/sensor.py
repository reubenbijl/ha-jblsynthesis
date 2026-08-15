"""Sensors for the JBL Synthesis integration.

These mirror the incoming-stream readouts of the receiver's own display: what format is
playing, at what rate, and what the video pipeline is carrying. Values come from the
library State, fed by the persistent connection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from arcam.fmj.codecs import (
    IncomingAudioConfig,
    IncomingAudioFormat,
    IncomingVideoColorspace,
)
from arcam.fmj.state import State
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfDataRate, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .entity import JBLSynthesisEntity
from .runtime import JBLSynthesisConfigEntry, JBLSynthesisRuntime

# Push integration: received frames drive updates, nothing is polled.
PARALLEL_UPDATES = 0

#: Audio format -> display label, as the receiver's own display words them.
AUDIO_FORMAT_LABELS: dict[IncomingAudioFormat, str] = {
    IncomingAudioFormat.PCM: "PCM",
    IncomingAudioFormat.ANALOGUE_DIRECT: "Analogue Direct",
    IncomingAudioFormat.DOLBY_DIGITAL: "Dolby Digital",
    IncomingAudioFormat.DOLBY_DIGITAL_EX: "Dolby Digital EX",
    IncomingAudioFormat.DOLBY_DIGITAL_SURROUND: "Dolby Digital Surround",
    IncomingAudioFormat.DOLBY_DIGITAL_PLUS: "Dolby Digital Plus",
    IncomingAudioFormat.DOLBY_DIGITAL_TRUE_HD: "Dolby TrueHD",
    IncomingAudioFormat.DTS: "DTS",
    IncomingAudioFormat.DTS_96_24: "DTS 96/24",
    IncomingAudioFormat.DTS_ES_MATRIX: "DTS-ES Matrix",
    IncomingAudioFormat.DTS_ES_DISCRETE: "DTS-ES Discrete",
    IncomingAudioFormat.DTS_ES_MATRIX_96_24: "DTS-ES Matrix 96/24",
    IncomingAudioFormat.DTS_ES_DISCRETE_96_24: "DTS-ES Discrete 96/24",
    IncomingAudioFormat.DTS_HD_MASTER_AUDIO: "DTS-HD Master Audio",
    IncomingAudioFormat.DTS_HD_HIGH_RES_AUDIO: "DTS-HD High Res Audio",
    IncomingAudioFormat.DTS_LOW_BIT_RATE: "DTS Low Bit Rate",
    IncomingAudioFormat.DTS_CORE: "DTS Core",
    IncomingAudioFormat.PCM_ZERO: "PCM Zero",
    IncomingAudioFormat.UNSUPPORTED: "Unsupported",
    IncomingAudioFormat.UNDETECTED: "Undetected",
    IncomingAudioFormat.DOLBY_ATMOS: "Dolby Atmos",
    IncomingAudioFormat.DTS_X: "DTS:X",
    IncomingAudioFormat.IMAX_ENHANCED: "IMAX Enhanced",
    IncomingAudioFormat.AURO_3D: "Auro-3D",
}

#: Channel configuration -> compact label ("3/4.1" style), matching the front panel.
AUDIO_CONFIG_LABELS: dict[IncomingAudioConfig, str] = {
    IncomingAudioConfig.DUAL_MONO: "1.0",
    IncomingAudioConfig.MONO: "1.0",
    IncomingAudioConfig.STEREO_ONLY: "2.0",
    IncomingAudioConfig.STEREO_SURR_MONO: "2/1.0",
    IncomingAudioConfig.STEREO_SURR_LR: "2/2.0",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_MONO: "2/3.0",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_LR: "2/4.0",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_MATRIX: "2/2.0 + matrix",
    IncomingAudioConfig.STEREO_CENTER: "3.0",
    IncomingAudioConfig.STEREO_CENTER_SURR_MONO: "3/1.0",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR: "3/2.0",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_MONO: "3/3.0",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_LR: "3/4.0",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_MATRIX: "3/2.0 + matrix",
    IncomingAudioConfig.STEREO_DOWNMIX: "2.0",
    IncomingAudioConfig.STEREO_ONLY_LO_RO: "2.0",
    IncomingAudioConfig.DUAL_MONO_LFE: "1.1",
    IncomingAudioConfig.MONO_LFE: "1.1",
    IncomingAudioConfig.STEREO_LFE: "2.1",
    IncomingAudioConfig.STEREO_SURR_MONO_LFE: "2/1.1",
    IncomingAudioConfig.STEREO_SURR_LR_LFE: "2/2.1",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_MONO_LFE: "2/3.1",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_LR_LFE: "2/4.1",
    IncomingAudioConfig.STEREO_SURR_LR_BACK_MATRIX_LFE: "2/2.1 + matrix",
    IncomingAudioConfig.STEREO_CENTER_LFE: "3.1",
    IncomingAudioConfig.STEREO_CENTER_SURR_MONO_LFE: "3/1.1",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_LFE: "3/2.1",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_MONO_LFE: "3/3.1",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_LR_LFE: "3/4.1",
    IncomingAudioConfig.STEREO_CENTER_SURR_LR_BACK_MATRIX_LFE: "3/2.1 + matrix",
    IncomingAudioConfig.STEREO_DOWNMIX_LFE: "2.1",
    IncomingAudioConfig.STEREO_ONLY_LO_RO_LFE: "2.1",
    IncomingAudioConfig.AURO_QUAD: "Auro Quad",
    IncomingAudioConfig.AURO_5_0: "Auro 5.0",
    IncomingAudioConfig.AURO_5_1: "Auro 5.1",
    IncomingAudioConfig.AURO_2_2_2: "Auro 2.2.2",
    IncomingAudioConfig.AURO_8_0: "Auro 8.0",
    IncomingAudioConfig.AURO_9_1: "Auro 9.1",
    IncomingAudioConfig.AURO_10_1: "Auro 10.1",
    IncomingAudioConfig.AURO_11_1: "Auro 11.1",
    IncomingAudioConfig.AURO_13_1: "Auro 13.1",
}

#: Formats whose name already says everything, so the channel count is left off.
_SELF_DESCRIBING_FORMATS = {
    IncomingAudioFormat.DOLBY_ATMOS,
    IncomingAudioFormat.DTS_X,
    IncomingAudioFormat.IMAX_ENHANCED,
}

#: HDR colorspace -> label suffix for the video sensor. NORMAL adds nothing.
COLORSPACE_LABELS: dict[IncomingVideoColorspace, str] = {
    IncomingVideoColorspace.HDR10: "HDR10",
    IncomingVideoColorspace.DOLBY_VISION: "Dolby Vision",
    IncomingVideoColorspace.HLG: "HLG",
    IncomingVideoColorspace.HDR10_PLUS: "HDR10+",
}


def _audio_format(state: State) -> StateType:
    """Combine format and channel configuration the way the front panel does."""
    audio_format, audio_config = state.get_incoming_audio_format()
    if audio_format is None or audio_config is None:
        return None
    if audio_format is IncomingAudioFormat.UNDETECTED:
        return None
    if audio_format in _SELF_DESCRIBING_FORMATS:
        return AUDIO_FORMAT_LABELS[audio_format]
    config_label = AUDIO_CONFIG_LABELS.get(audio_config)
    if config_label is not None and config_label.startswith("Auro"):
        return config_label
    format_label = AUDIO_FORMAT_LABELS.get(audio_format, audio_format.name.title())
    if config_label is None:
        return format_label
    return f"{format_label} {config_label}"


def _sample_rate(state: State) -> StateType:
    """Return the incoming sample rate in Hz."""
    return state.get_incoming_audio_sample_rate()


def _bitrate(state: State) -> StateType:
    """Return the incoming bitrate in bit/s.

    Symbolic rates ("open", "variable", "lossless") have no numeric value; the audio
    format sensor already tells that story, so they read as unknown here.
    """
    setup = state.get_general_setup()
    if setup is None or not isinstance(setup.bitrate, int):
        return None
    return setup.bitrate


def _dialnorm(state: State) -> StateType:
    """Return the stream's dialogue normalisation in dB."""
    setup = state.get_general_setup()
    if setup is None:
        return None
    return setup.dialnorm


def _input_name(state: State) -> StateType:
    """Return the user-assigned name of the current input."""
    setup = state.get_general_setup()
    if setup is None or not setup.source_name:
        return None
    return setup.source_name


def _incoming_video(state: State) -> StateType:
    """Return the incoming video mode, e.g. 3840x2160p60 (Dolby Vision)."""
    video = state.get_incoming_video_parameters()
    if video is None or not video.horizontal_resolution:
        return None
    scan = "i" if video.interlaced else "p"
    label = (
        f"{video.horizontal_resolution}x{video.vertical_resolution}"
        f"{scan}{video.refresh_rate}"
    )
    colorspace = COLORSPACE_LABELS.get(video.colorspace) if video.colorspace else None
    if colorspace is not None:
        return f"{label} ({colorspace})"
    return label


@dataclass(frozen=True, kw_only=True)
class JBLSynthesisSensorDescription(SensorEntityDescription):
    """Describes a JBL Synthesis sensor."""

    value_fn: Callable[[State], StateType]


SENSORS: tuple[JBLSynthesisSensorDescription, ...] = (
    JBLSynthesisSensorDescription(
        key="audio_format",
        translation_key="audio_format",
        value_fn=_audio_format,
    ),
    JBLSynthesisSensorDescription(
        key="input_name",
        translation_key="input_name",
        value_fn=_input_name,
    ),
    JBLSynthesisSensorDescription(
        key="incoming_video",
        translation_key="incoming_video",
        value_fn=_incoming_video,
    ),
    JBLSynthesisSensorDescription(
        key="sample_rate",
        translation_key="sample_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_unit_of_measurement=UnitOfFrequency.KILOHERTZ,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sample_rate,
    ),
    JBLSynthesisSensorDescription(
        key="bitrate",
        translation_key="bitrate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_bitrate,
    ),
    JBLSynthesisSensorDescription(
        key="dialnorm",
        translation_key="dialnorm",
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_dialnorm,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JBLSynthesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(
        JBLSynthesisSensor(entry.runtime_data, description) for description in SENSORS
    )


class JBLSynthesisSensor(JBLSynthesisEntity, SensorEntity):
    """A read-out of the receiver's incoming stream."""

    entity_description: JBLSynthesisSensorDescription

    def __init__(
        self,
        runtime: JBLSynthesisRuntime,
        description: JBLSynthesisSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(runtime)
        self.entity_description = description
        self._attr_unique_id = f"{self.device_identifier}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the sensor value from the library state."""
        return self.entity_description.value_fn(self.runtime.state)
