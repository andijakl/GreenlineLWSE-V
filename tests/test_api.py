"""Test the Greenline MControl2 WebSocket client."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.greenline_lwse_v.api import (
    RECONNECT_DELAY,
    GreenlineLWSEAuthError,
    GreenlineLWSEClient,
    GreenlineLWSEConnectionError,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_login_failure_closes_websocket() -> None:
    """Test a login rejection closes the WebSocket."""
    websocket = MagicMock(closed=False)
    websocket.send_str = AsyncMock()
    websocket.close = AsyncMock()
    websocket.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            aiohttp.WSMsgType.TEXT,
            '#{"command":"login","error":"invalid_auth"}',
            "",
        )
    )
    session = MagicMock()
    session.ws_connect = AsyncMock(return_value=websocket)
    client = GreenlineLWSEClient(
        session=session,
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=MagicMock(),
    )

    with pytest.raises(GreenlineLWSEAuthError, match="invalid_auth"):
        await client.async_connect()

    websocket.close.assert_awaited_once()


async def test_login_timeout_closes_websocket() -> None:
    """Test a missing login response closes the WebSocket."""
    websocket = MagicMock(closed=False)
    websocket.send_str = AsyncMock()
    websocket.close = AsyncMock()
    websocket.receive = AsyncMock(side_effect=TimeoutError)
    session = MagicMock()
    session.ws_connect = AsyncMock(return_value=websocket)
    client = GreenlineLWSEClient(
        session=session,
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=MagicMock(),
    )

    with pytest.raises(GreenlineLWSEConnectionError, match="Timed out"):
        await client.async_connect()

    websocket.close.assert_awaited_once()


async def test_send_payload_uses_controller_framing() -> None:
    """Test outgoing values use the controller frame format."""
    websocket = MagicMock(closed=False)
    websocket.send_str = AsyncMock()
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=MagicMock(),
    )
    client._ws = websocket

    await client.async_set_value("1.100.1.5", 21.5)

    websocket.send_str.assert_awaited_once_with(
        '#{"command": "setVMValue", "parameter": {"dap": "1.100.1.5", "value": "21.5"}}\n'
    )


def test_handle_payload_dispatches_valid_hotlink_data() -> None:
    """Test valid framed hotlink data is forwarded to the coordinator."""
    on_data = MagicMock()
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=on_data,
        on_connection_lost=MagicMock(),
    )

    client._handle_payload(
        '#{"command":"HLVal","values":[{"path":"1.100.1.5","result":"21.5"},{"path":3,"result":"ignored"}]}'
    )

    on_data.assert_called_once_with({"1.100.1.5": "21.5"})


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not-framed", id="missing-prefix"),
        pytest.param("#{not-json}", id="invalid-json"),
        pytest.param("#[]", id="non-object"),
        pytest.param('#{"command":"HLVal","values":"invalid"}', id="invalid-values"),
    ],
)
def test_handle_payload_ignores_malformed_messages(raw: str) -> None:
    """Test malformed device payloads cannot update coordinator data."""
    on_data = MagicMock()
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=on_data,
        on_connection_lost=MagicMock(),
    )

    client._handle_payload(raw)

    on_data.assert_not_called()


async def test_connection_failure_reconnects_after_backoff() -> None:
    """Test a transport failure restores subscriptions after a delay."""
    on_connection_lost = MagicMock()
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=on_connection_lost,
    )
    client._subscriptions.add("1.100.1.5")
    client._async_connect_and_login = AsyncMock()
    client._async_receive_forever = AsyncMock(
        side_effect=GreenlineLWSEConnectionError("lost")
    )
    client._async_send = AsyncMock()

    async def stop_after_backoff(delay: float) -> None:
        assert delay == RECONNECT_DELAY
        client._stopping = True

    sleep = AsyncMock(side_effect=stop_after_backoff)
    with patch("custom_components.greenline_lwse_v.api.asyncio.sleep", sleep):
        await client.async_run()

    on_connection_lost.assert_called_once()
    sleep.assert_awaited_once_with(RECONNECT_DELAY)
    client._async_connect_and_login.assert_awaited_once()
    client._async_send.assert_awaited_once_with(
        {"command": "addHotlink", "parameter": {"dap": "1.100.1.5"}}
    )


async def test_authentication_failure_does_not_reconnect() -> None:
    """Test a runtime authentication failure starts reauth without retrying."""
    on_connection_lost = MagicMock()
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=on_connection_lost,
    )
    client._async_connect_and_login = AsyncMock(
        side_effect=GreenlineLWSEAuthError("invalid_auth")
    )

    await client.async_run()

    client._async_connect_and_login.assert_awaited_once()
    on_connection_lost.assert_called_once()


async def test_write_failure_raises_connection_error() -> None:
    """Test a failed WebSocket write is translated to a client error."""
    websocket = MagicMock(closed=False)
    websocket.send_str = AsyncMock(side_effect=aiohttp.ClientError("write failed"))
    client = GreenlineLWSEClient(
        session=MagicMock(),
        host="host",
        username="username",
        password="password",
        on_data=MagicMock(),
        on_connection_lost=MagicMock(),
    )
    client._ws = websocket

    with pytest.raises(GreenlineLWSEConnectionError, match="write failed"):
        await client.async_set_value("1.100.1.5", 21.5)
