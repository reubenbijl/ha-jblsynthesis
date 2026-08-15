"""Config flow for the JBL Synthesis integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from arcam.fmj.client import Client
from arcam.fmj.errors import ArcamException, ConnectionFailed
from arcam.fmj.packets import AmxDuetRequest, AmxDuetResponse
from arcam.fmj.utils import cancel_and_wait, get_uniqueid_from_host
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MANUFACTURER,
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    DOMAIN,
    IDENTIFY_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class JBLSynthesisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a JBL Synthesis receiver."""

    VERSION = 1

    async def _async_validate(
        self, host: str, port: int
    ) -> tuple[AmxDuetResponse | None, str | None]:
        """Probe a host, returning either its AMX identity or an error key.

        The AMX Duet reply proves the address speaks the Arcam/JBL protocol and carries
        the make and model, so the entry can be titled before the receiver is ever
        polled. An address that accepts TCP but never answers AMX is some other device.
        """
        client = Client(host, port)
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await client.start()
        except (ConnectionFailed, TimeoutError, OSError):
            return None, "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error connecting to %s:%s", host, port)
            return None, "unknown"

        process_task = asyncio.get_running_loop().create_task(client.process())
        try:
            async with asyncio.timeout(IDENTIFY_TIMEOUT):
                return await client.request_raw(AmxDuetRequest()), None
        except (TimeoutError, ArcamException):
            return None, "invalid_response"
        except Exception:
            _LOGGER.exception("Unexpected error identifying %s:%s", host, port)
            return None, "unknown"
        finally:
            await cancel_and_wait(process_task)
            await client.stop()

    async def _async_unique_id(self, host: str) -> str | None:
        """Fetch a stable unique id from the receiver's UPnP description.

        Falls back to None when the description is unavailable; the flow then guards
        against duplicates by host instead.
        """
        return await get_uniqueid_from_host(async_get_clientsession(self.hass), host)

    @staticmethod
    def _entry_data(host: str, port: int, amx: AmxDuetResponse) -> dict[str, Any]:
        """Build entry data from the validated connection."""
        return {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_MODEL: amx.device_model,
            CONF_MANUFACTURER: amx.device_make,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow started by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            amx, error = await self._async_validate(host, port)
            if amx is not None:
                unique_id = await self._async_unique_id(host)
                if unique_id is not None:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                else:
                    self._async_abort_entries_match({CONF_HOST: host})
                return self.async_create_entry(
                    title=amx.device_model or host,
                    data=self._entry_data(host, port, amx),
                )
            assert error is not None
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user point an existing entry at a new address.

        Useful when the receiver's DHCP lease changes: the entry keeps its entities and
        history rather than having to be removed and re-added.
        """
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            amx, error = await self._async_validate(host, port)
            if amx is not None:
                # Refuse to repoint an entry at a *different* receiver: its entities and
                # history belong to the unit the entry was created for. Only enforceable
                # when the UPnP unique id is available.
                unique_id = await self._async_unique_id(host)
                if unique_id is not None:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._entry_data(host, port, amx)
                )
            assert error is not None
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                {
                    CONF_HOST: entry.data[CONF_HOST],
                    CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                },
            ),
            errors=errors,
        )
