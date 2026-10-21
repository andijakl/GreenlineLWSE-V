r"""In-process fake of the MControl2 controller for end-to-end tests.

Frames mirror those recorded from a real controller (web-app version 1.3):

    -> GET /serial.html                       <- "<serial>"
    -> #serial?<serial>\n
    -> #{"command": "login", ...}\n            <- @{"command":"login","userId":3}\n
    -> #{"command": "addHotlink", ...}\n       <- @{"command":"addHotlink",...,"retval":0}\n
                                               <- @{"command":"HLVal","values":[...]}\n
    -> #{"command": "setVMValue", ...}\n       <- HLVal with the new value

The controller serves HTTP on port 80 and the WebSocket on port 3118. Tests route
both to one local server through a resolver for CONTROLLER_HOST.
"""

import asyncio
import json
import socket
from typing import Any

from aiohttp import web
from aiohttp.abc import AbstractResolver, ResolveResult

CONTROLLER_HOST = "greenline.test"


class FakeController:
    """Serve the controller's serial endpoint and WebSocket protocol."""

    def __init__(
        self, *, serial: str, username: str, password: str, values: dict[str, str]
    ) -> None:
        """Initialize the controller state."""
        self.serial = serial
        self.username = username
        self.password = password
        self.values = dict(values)
        self.serial_status = 200
        self.login_error: Any = "Login failed"
        self.answer_login = True
        self.received: list[dict[str, Any]] = []
        self.login_count = 0
        self.port = 0
        self._sockets: dict[web.WebSocketResponse, set[str]] = {}
        self._runner: web.AppRunner | None = None

    @property
    def connection_count(self) -> int:
        """Return the number of open WebSocket connections."""
        return len(self._sockets)

    def commands(self, name: str) -> list[dict[str, Any]]:
        """Return the parameters of all received commands with the given name."""
        return [cmd["parameter"] for cmd in self.received if cmd["command"] == name]

    async def start(self) -> None:
        """Start serving on an ephemeral local port, reusing the previous port."""
        app = web.Application()
        app.router.add_get("/serial.html", self._handle_serial)
        app.router.add_get("/", self._handle_websocket)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        self.port = self._runner.addresses[0][1]

    async def stop(self) -> None:
        """Stop serving, closing all connections as a power loss would."""
        if self._runner is not None:
            await self.drop_connections()
            await self._runner.cleanup()
            self._runner = None

    async def drop_connections(self) -> None:
        """Close all WebSocket connections from the controller side."""
        for ws in list(self._sockets):
            await ws.close()

    async def push(self, values: dict[str, str]) -> None:
        """Change values on the controller and notify subscribed clients."""
        self.values.update(values)
        for ws, subscriptions in list(self._sockets.items()):
            if changed := [dap for dap in values if dap in subscriptions]:
                await ws.send_str(self._hotlink_values(changed))

    async def send_raw(self, frame: str) -> None:
        """Send an arbitrary frame to all connected clients."""
        for ws in list(self._sockets):
            await ws.send_str(frame)

    async def _handle_serial(self, request: web.Request) -> web.Response:
        return web.Response(
            status=self.serial_status, text=self.serial, content_type="text/html"
        )

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        subscriptions: set[str] = set()
        self._sockets[ws] = subscriptions
        handshake_done = logged_in = False
        try:
            async for msg in ws:
                frame = msg.data
                assert frame.startswith("#") and frame.endswith("\n"), frame
                body = frame[1:-1]
                if not handshake_done:
                    if body != f"serial?{self.serial}":
                        break
                    handshake_done = True
                    continue
                command = json.loads(body)
                self.received.append(command)
                parameter = command["parameter"]
                if command["command"] == "login":
                    self.login_count += 1
                    if not self.answer_login:
                        continue
                    logged_in = (parameter["username"], parameter["password"]) == (
                        self.username,
                        self.password,
                    )
                    reply = {"command": "login"}
                    reply |= {"userId": 3} if logged_in else {"error": self.login_error}
                    await ws.send_str(self._frame(reply))
                elif not logged_in:
                    continue
                elif command["command"] == "addHotlink":
                    subscriptions.add(parameter["dap"])
                    await ws.send_str(self._frame({**command, "retval": 0}))
                    if parameter["dap"] in self.values:
                        await ws.send_str(self._hotlink_values([parameter["dap"]]))
                elif command["command"] == "setVMValue":
                    await self.push({parameter["dap"]: parameter["value"]})
        finally:
            del self._sockets[ws]
        return ws

    def _hotlink_values(self, daps: list[str]) -> str:
        values = []
        for dap in daps:
            function, group, unit, variable = (int(part) for part in dap.split("."))
            values.append(
                {
                    "dap": {
                        "functionId": function,
                        "functiongroupId": group,
                        "unitId": unit,
                        "variableId": variable,
                    },
                    "path": dap,
                    "result": self.values[dap],
                    "type": 6,
                }
            )
        return self._frame({"command": "HLVal", "values": values})

    @staticmethod
    def _frame(message: dict[str, Any]) -> str:
        return f"@{json.dumps(message, separators=(',', ':'))}\n"


class FakeControllerResolver(AbstractResolver):
    """Resolve CONTROLLER_HOST on any port to the fake controller."""

    def __init__(self, controller: FakeController) -> None:
        """Initialize the resolver."""
        self._controller = controller

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        """Return the local address of the fake controller."""
        if host != CONTROLLER_HOST:
            raise OSError(f"Unknown host {host}")
        return [
            ResolveResult(
                hostname=host,
                host="127.0.0.1",
                port=self._controller.port,
                family=socket.AF_INET,
                proto=0,
                flags=socket.AI_NUMERICHOST,
            )
        ]

    async def close(self) -> None:
        """Release the resolver."""


async def wait_for(condition: Any, timeout: float = 5) -> None:
    """Wait until condition() is true, as real socket I/O completes asynchronously."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)
