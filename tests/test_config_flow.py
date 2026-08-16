"""Tests for the JBL Synthesis config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from arcam.fmj.errors import ArcamException, ConnectionFailed
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jblsynthesis.const import CONF_MANUFACTURER, DOMAIN

from .conftest import HOST, PORT, UNIQUE_ID

USER_INPUT = {CONF_HOST: HOST, CONF_PORT: PORT}


async def test_user_flow(
    hass: HomeAssistant, mock_library: tuple[MagicMock, MagicMock]
) -> None:
    """A reachable receiver is identified and added."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SDR-35"
    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_PORT: PORT,
        CONF_MODEL: "SDR-35",
        CONF_MANUFACTURER: "JBL SYNTHESIS",
    }
    assert result["result"].unique_id == UNIQUE_ID


@pytest.mark.parametrize(
    ("connect_error", "identify_error", "expected"),
    [
        (ConnectionFailed(), None, "cannot_connect"),
        (TimeoutError(), None, "cannot_connect"),
        (OSError(), None, "cannot_connect"),
        (RuntimeError(), None, "unknown"),
        (None, TimeoutError(), "invalid_response"),
        (None, ArcamException(), "invalid_response"),
        (None, RuntimeError(), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    connect_error: Exception | None,
    identify_error: Exception | None,
    expected: str,
) -> None:
    """Failures surface as form errors, and the flow recovers afterwards."""
    mock_client, _ = mock_library
    if connect_error is not None:
        mock_client.start.side_effect = connect_error
    if identify_error is not None:
        mock_client.request_raw.side_effect = identify_error

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    mock_client.start.side_effect = None
    mock_client.request_raw.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_without_unique_id(
    hass: HomeAssistant, mock_library: tuple[MagicMock, MagicMock]
) -> None:
    """A receiver without a UPnP description is still added, keyed by host."""
    with patch(
        "custom_components.jblsynthesis.config_flow.get_uniqueid_from_host",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id is None


async def test_user_flow_duplicate_host_without_unique_id(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without a unique id, the same host cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.jblsynthesis.config_flow.get_uniqueid_from_host",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """Re-adding the same receiver updates its host and aborts."""
    mock_config_entry.add_to_hass(hass)
    new_host = "192.168.128.99"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: new_host, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == new_host


async def test_reconfigure(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """The entry can be pointed at a new address for the same receiver."""
    mock_config_entry.add_to_hass(hass)
    new_host = "192.168.128.99"

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: new_host, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # The abort schedules an entry reload; let it finish inside the test so its
    # storage writes cannot linger past teardown (seen as flakes on slower CI).
    await hass.async_block_till_done()
    assert mock_config_entry.data[CONF_HOST] == new_host


async def test_reconfigure_wrong_device(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """Repointing at a different receiver is refused."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.jblsynthesis.config_flow.get_uniqueid_from_host",
        return_value="another-receiver",
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.128.99", CONF_PORT: PORT}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_HOST] == HOST


async def test_reconfigure_without_unique_id(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without a UPnP id the identity check is skipped and the update applied."""
    mock_config_entry.add_to_hass(hass)
    new_host = "192.168.128.99"

    with patch(
        "custom_components.jblsynthesis.config_flow.get_uniqueid_from_host",
        return_value=None,
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: new_host, CONF_PORT: PORT}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # The abort schedules an entry reload; let it finish inside the test so its
    # storage writes cannot linger past teardown (seen as flakes on slower CI).
    await hass.async_block_till_done()
    assert mock_config_entry.data[CONF_HOST] == new_host


async def test_reconfigure_error_and_recovery(
    hass: HomeAssistant,
    mock_library: tuple[MagicMock, MagicMock],
    mock_config_entry: MockConfigEntry,
) -> None:
    """A validation failure shows the form again, then the flow recovers."""
    mock_config_entry.add_to_hass(hass)
    mock_client, _ = mock_library
    mock_client.start.side_effect = ConnectionFailed()

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.128.99", CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.start.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.128.99", CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # The abort schedules an entry reload; let it finish inside the test so its
    # storage writes cannot linger past teardown (seen as flakes on slower CI).
    await hass.async_block_till_done()
