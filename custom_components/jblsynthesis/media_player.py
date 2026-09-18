"""Media player entity for the JBL Synthesis integration."""

from __future__ import annotations

from arcam.fmj.codecs import DecodeMode2CH, DecodeModeMCH, SourceCodes
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import JBLSynthesisEntity
from .runtime import JBLSynthesisConfigEntry, JBLSynthesisRuntime

# Push integration: received frames drive updates, nothing is polled.
PARALLEL_UPDATES = 0

#: The receiver's volume scale (0x0D takes 0-99).
VOLUME_MAX = 99

#: Wire-enum member name -> label shown in the source list.
SOURCE_LABELS: dict[str, str] = {
    "CD": "CD",
    "BD": "BD",
    "AV": "AV",
    "SAT": "Sat",
    "PVR": "PVR",
    "UHD": "UHD",
    "AUX": "Aux",
    "DISPLAY": "Display",
    "FM": "FM",
    "DAB": "DAB",
    "NET": "Net",
    "USB": "USB",
    "STB": "STB",
    "GAME": "Game",
    "BT": "Bluetooth",
}

#: Decode-mode member name -> label shown in the sound-mode list. DOLBY_D_EX_OR_DTS_ES
#: is the multi-channel 0x03, which means DTS Neural:X on this platform.
DECODE_MODE_LABELS: dict[str, str] = {
    "STEREO": "Stereo",
    "STEREO_DOWNMIX": "Stereo Downmix",
    "MULTI_CHANNEL": "Multi-channel",
    "DOLBY_D_EX_OR_DTS_ES": "DTS Neural:X",
    "DOLBY_SURROUND": "Dolby Surround",
    "DTS_NEO_6_CINEMA": "DTS Neo:6 Cinema",
    "DTS_NEO_6_MUSIC": "DTS Neo:6 Music",
    "MCH_STEREO": "Multi-channel Stereo",
    "DTS_NEURAL_X": "DTS Neural:X",
    "LOGIC_16_IMMERSION": "Logic 16 Immersion",
    "DTS_VIRTUAL_X": "DTS Virtual:X",
    "DOLBY_VIRTUAL_HEIGHT": "Dolby Virtual Height",
    "AURO_NATIVE": "Auro Native",
    "AURO_MATIC_3D": "Auro-Matic 3D",
    "AURO_2D": "Auro-2D",
}


def _source_label(source: SourceCodes) -> str:
    """Return the display label for a source."""
    return SOURCE_LABELS.get(source.name, source.name.title())


def _decode_mode_label(mode: DecodeMode2CH | DecodeModeMCH) -> str:
    """Return the display label for a decode mode."""
    return DECODE_MODE_LABELS.get(mode.name, mode.name.replace("_", " ").title())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JBLSynthesisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player."""
    async_add_entities([JBLSynthesisMediaPlayer(entry.runtime_data)])


class JBLSynthesisMediaPlayer(JBLSynthesisEntity, MediaPlayerEntity):
    """The receiver's master zone."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )

    def __init__(self, runtime: JBLSynthesisRuntime) -> None:
        """Initialise the media player."""
        super().__init__(runtime)
        self._attr_unique_id = self.device_identifier

    @property
    def state(self) -> MediaPlayerState | None:
        """Return off (standby)/on, or None before the first power frame arrives."""
        power = self.runtime.state.get_power()
        if power is None:
            return None
        return MediaPlayerState.ON if power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Return the volume as 0..1 of the receiver's 0-99 scale."""
        volume = self.runtime.state.get_volume()
        if volume is None:
            return None
        return volume / VOLUME_MAX

    @property
    def is_volume_muted(self) -> bool | None:
        """Return whether the zone is muted."""
        return self.runtime.state.get_mute()

    @property
    def source(self) -> str | None:
        """Return the current source."""
        source = self.runtime.state.get_source()
        if source is None:
            return None
        return _source_label(source)

    @property
    def source_list(self) -> list[str]:
        """Return the selectable sources."""
        return [
            _source_label(source) for source in self.runtime.state.get_source_list()
        ]

    @property
    def sound_mode(self) -> str | None:
        """Return the active decode mode."""
        mode = self.runtime.state.get_decode_mode()
        if mode is None:
            return None
        return _decode_mode_label(mode)

    @property
    def sound_mode_list(self) -> list[str] | None:
        """Return the decode modes valid for the current stream type.

        The receiver offers different mode sets for stereo and multi-channel material,
        so this list changes with the incoming stream.
        """
        modes = self.runtime.state.get_decode_modes()
        if not modes:
            return None
        return [_decode_mode_label(mode) for mode in modes]

    async def async_turn_on(self) -> None:
        """Power the zone on.

        Only reaches the receiver when it is network-reachable, i.e. standby with
        'HDMI Bypass & IP' on and Standby Mode set to Manual. In deep standby
        nothing can reach it.
        """
        await self._async_call(self.runtime.state.set_power(True))

    async def async_turn_off(self) -> None:
        """Put the zone into standby."""
        await self._async_call(self.runtime.state.set_power(False))

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume from 0..1."""
        await self._async_call(
            self.runtime.state.set_volume(round(volume * VOLUME_MAX))
        )

    async def async_volume_up(self) -> None:
        """Step the volume up one unit of the receiver's 0-99 scale."""
        await self._async_call(self.runtime.state.inc_volume())

    async def async_volume_down(self) -> None:
        """Step the volume down one unit of the receiver's 0-99 scale."""
        await self._async_call(self.runtime.state.dec_volume())

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the zone."""
        await self._async_call(self.runtime.state.set_mute(mute))

    async def async_select_source(self, source: str) -> None:
        """Switch input."""
        for candidate in self.runtime.state.get_source_list():
            if _source_label(candidate) == source:
                await self._async_call(self.runtime.state.set_source(candidate))
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_source",
            translation_placeholders={"source": source},
        )

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Switch decode mode, within the set valid for the current stream."""
        for candidate in self.runtime.state.get_decode_modes() or []:
            if _decode_mode_label(candidate) == sound_mode:
                await self._async_call(self.runtime.state.set_decode_mode(candidate))
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_sound_mode",
            translation_placeholders={"sound_mode": sound_mode},
        )
