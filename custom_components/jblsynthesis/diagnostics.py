"""Diagnostics support for the JBL Synthesis integration."""

from __future__ import annotations

import enum
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import attr
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .runtime import JBLSynthesisConfigEntry

TO_REDACT = {CONF_HOST}


def _serialisable(value: Any) -> Any:
    """Reduce library values (enums, attrs classes, bytes) to JSON-safe data."""
    if isinstance(value, enum.Enum):
        return value.name
    if attr.has(type(value)):
        return {
            field.name: _serialisable(getattr(value, field.name))
            for field in attr.fields(type(value))
        }
    if isinstance(value, bytes):
        return value.hex(" ")
    if isinstance(value, dict):
        return {str(key): _serialisable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialisable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _library_version() -> str | None:
    """Return the installed arcam-fmj version.

    The requirement is a branch archive URL, so the version installed is not
    otherwise visible on a running system.
    """
    try:
        return version("arcam-fmj")
    except PackageNotFoundError:
        return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JBLSynthesisConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "connected": runtime.connected,
        "model": runtime.state.model,
        "revision": runtime.state.revision,
        # Reads package metadata from disk, so off the event loop.
        "library_version": await hass.async_add_executor_job(_library_version),
        "state": _serialisable(runtime.state.to_dict()),
    }
