"""WebSocket client for the Greenline LWSE-V MControl2 controller."""

import asyncio
from collections.abc import Callable
import json
import logging
from typing import Any

import aiohttp

from .const import PORT

_LOGGER = logging.getLogger(__name__)

LOGIN_TIMEOUT = 10
RECONNECT_DELAY = 30


class GreenlineLWSEError(Exception):
    """Base error for the Greenline API client."""


class GreenlineLWSEAuthError(GreenlineLWSEError):
    """Raised when authentication with the device fails."""


class GreenlineLWSEConnectionError(GreenlineLWSEError):
    """Raised when the connection to the device fails or is lost."""


class GreenlineLWSEClient:
    """Client for the MControl2 WebSocket JSON protocol."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        on_data: Callable[[dict[str, str]], None],
        on_connection_lost: Callable[[Exception], None],
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._host = host
        self._username = username
        self._password = password
        self._on_data = on_data
        self._on_connection_lost = on_connection_lost
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._subscriptions: set[str] = set()
        self._pending_login: asyncio.Future[str | None] | None = None
        self._serial: str | None = None
        self._stopping = False

    async def async_connect(self) -> str:
        """Open the connection, log in, and return the controller serial."""
        return await self._async_connect_and_login()

    async def async_disconnect(self) -> None:
        """Close the connection."""
        self._stopping = True
        await self._async_close_websocket()

    async def async_subscribe(self, dap: str) -> None:
        """Subscribe to data-point updates."""
        self._subscriptions.add(dap)
        await self._async_send({"command": "addHotlink", "parameter": {"dap": dap}})

    async def async_set_value(self, dap: str, value: float | str) -> None:
        """Set a data-point value on the device."""
        await self._async_send(
            {"command": "setVMValue", "parameter": {"dap": dap, "value": str(value)}}
        )

    async def async_run(self) -> None:
        """Maintain the connection until it is explicitly disconnected."""
        self._stopping = False
        while not self._stopping:
            try:
                if self._ws is None or self._ws.closed:
                    await self._async_connect_and_login()
                    for dap in self._subscriptions:
                        await self._async_send(
                            {"command": "addHotlink", "parameter": {"dap": dap}}
                        )
                await self._async_receive_forever()
            except GreenlineLWSEAuthError as err:
                if not self._stopping:
                    self._on_connection_lost(err)
                return
            except GreenlineLWSEConnectionError as err:
                if self._stopping:
                    return
                self._on_connection_lost(err)
                await asyncio.sleep(RECONNECT_DELAY)

    async def _async_connect_and_login(self) -> str:
        """Open the WebSocket connection and wait for the login response."""
        url = f"ws://{self._host}:{PORT}"
        try:
            self._ws = await self._session.ws_connect(url, heartbeat=30)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GreenlineLWSEConnectionError(str(err)) from err

        pending_login = asyncio.get_running_loop().create_future()
        self._pending_login = pending_login
        try:
            serial = await self._async_get_serial()
            if self._serial is not None and serial != self._serial:
                raise GreenlineLWSEConnectionError(
                    "Connected controller serial changed during reconnect"
                )
            await self._async_send_frame(f"serial?{serial}")
            await self._async_send(
                {
                    "command": "login",
                    "parameter": {
                        "username": self._username,
                        "password": self._password,
                    },
                }
            )
            try:
                async with asyncio.timeout(LOGIN_TIMEOUT):
                    while not pending_login.done():
                        self._handle_ws_message(await self._async_receive())
            except TimeoutError as err:
                raise GreenlineLWSEConnectionError(
                    "Timed out waiting for login response"
                ) from err

            error = pending_login.result()
            if error is not None:
                raise GreenlineLWSEAuthError(error)
        except GreenlineLWSEError:
            await self._async_close_websocket()
            raise
        else:
            self._serial = serial
            return serial
        finally:
            self._pending_login = None

    async def _async_get_serial(self) -> str:
        """Fetch the controller serial required by the WebSocket handshake."""
        url = f"http://{self._host}/serial.html"
        timeout = aiohttp.ClientTimeout(total=LOGIN_TIMEOUT)
        try:
            async with self._session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                serial = (await response.text()).strip()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GreenlineLWSEConnectionError(
                f"Could not retrieve controller serial: {err}"
            ) from err
        if not serial:
            raise GreenlineLWSEConnectionError("Controller returned an empty serial")
        return serial

    async def _async_receive_forever(self) -> None:
        """Read and process messages until the connection is closed."""
        if self._ws is None:
            raise GreenlineLWSEConnectionError("Not connected")
        ws = self._ws
        while True:
            self._handle_ws_message(await self._async_receive(ws))

    async def _async_receive(
        self, ws: aiohttp.ClientWebSocketResponse | None = None
    ) -> aiohttp.WSMessage:
        """Receive a WebSocket message, translating transport errors."""
        ws = ws or self._ws
        if ws is None:
            raise GreenlineLWSEConnectionError("Not connected")
        try:
            return await ws.receive()
        except (aiohttp.ClientError, ConnectionError) as err:
            raise GreenlineLWSEConnectionError(str(err)) from err

    def _handle_ws_message(self, msg: aiohttp.WSMessage) -> None:
        """Handle a single WebSocket message."""
        if msg.type is aiohttp.WSMsgType.TEXT:
            self._handle_payload(msg.data)
        elif msg.type in (
            aiohttp.WSMsgType.ERROR,
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSED,
        ):
            raise GreenlineLWSEConnectionError("Connection to the device was closed")

    def _handle_payload(self, raw: str) -> None:
        """Parse and dispatch a single text payload from the device."""
        if not raw.startswith(("#", "@")):
            _LOGGER.debug("Ignoring message with an invalid frame prefix: %s", raw)
            return
        try:
            message = json.loads(raw[1:])
        except ValueError:
            _LOGGER.debug("Ignoring message that could not be parsed: %s", raw)
            return

        if not isinstance(message, dict):
            _LOGGER.debug("Ignoring malformed message: %s", raw)
            return

        command = message.get("command")
        if command == "login":
            error = message.get("error")
            if self._pending_login is not None and not self._pending_login.done():
                self._pending_login.set_result(
                    error if isinstance(error, str) else None
                )
        elif command == "HLVal" and isinstance(message.get("values"), list):
            values = {
                value["path"]: value["result"]
                for value in message["values"]
                if isinstance(value, dict)
                and isinstance(value.get("path"), str)
                and isinstance(value.get("result"), str)
            }
            if values:
                self._on_data(values)

    async def _async_send(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to the device."""
        await self._async_send_frame(json.dumps(payload))

    async def _async_send_frame(self, payload: str) -> None:
        """Send a framed protocol payload to the device."""
        if self._ws is None:
            raise GreenlineLWSEConnectionError("Not connected")
        try:
            await self._ws.send_str(f"#{payload}\n")
        except (aiohttp.ClientError, ConnectionError) as err:
            raise GreenlineLWSEConnectionError(str(err)) from err

    async def _async_close_websocket(self) -> None:
        """Close and clear the current WebSocket connection."""
        ws, self._ws = self._ws, None
        if ws is not None and not ws.closed:
            await ws.close()
