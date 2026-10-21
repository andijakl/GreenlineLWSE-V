"""Test the MControl2 WebSocket client against a fake controller."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
import pytest

from custom_components.greenline_lwse_v.api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEClient,
    GreenlineLWSEConnectionError,
)

from .conftest import TEST_DEVICE_ID, TEST_PASSWORD, TEST_USERNAME
from .fake_controller import CONTROLLER_HOST, FakeController, wait_for

TARGET = "1.100.1.5"
WARM_WATER = "1.101.1.20"


class Recorder:
    """Collect the callbacks of a client."""

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.values: dict[str, str] = {}
        self.updates: list[dict[str, str]] = []
        self.errors: list[Exception] = []

    def on_data(self, values: dict[str, str]) -> None:
        """Record pushed values."""
        self.values.update(values)
        self.updates.append(values)

    def on_connection_lost(self, err: Exception) -> None:
        """Record connection losses."""
        self.errors.append(err)


@pytest.fixture
def recorder() -> Recorder:
    """Return a callback recorder."""
    return Recorder()


@pytest.fixture
def client(
    controller_session: aiohttp.ClientSession, recorder: Recorder
) -> GreenlineLWSEClient:
    """Return a client for the fake controller."""
    return GreenlineLWSEClient(
        session=controller_session,
        host=CONTROLLER_HOST,
        username=TEST_USERNAME,
        password=TEST_PASSWORD,
        on_data=recorder.on_data,
        on_connection_lost=recorder.on_connection_lost,
    )


@pytest.fixture
async def running_client(
    client: GreenlineLWSEClient, fake_controller: FakeController, recorder: Recorder
) -> AsyncGenerator[asyncio.Task[None]]:
    """Connect, subscribe like the coordinator, and keep the connection running."""
    assert await client.async_connect() == TEST_DEVICE_ID
    await client.async_subscribe(TARGET)
    await client.async_subscribe(WARM_WATER)
    task = asyncio.create_task(client.async_run())
    await wait_for(lambda: {TARGET, WARM_WATER} <= recorder.values.keys())
    yield task
    await client.async_disconnect()
    await asyncio.wait_for(task, 5)


async def test_connect_logs_in_and_returns_serial(
    client: GreenlineLWSEClient, fake_controller: FakeController
) -> None:
    """Test the handshake and login used by the controller web app."""
    assert await client.async_connect() == TEST_DEVICE_ID

    assert fake_controller.commands("login") == [
        {"username": TEST_USERNAME, "password": TEST_PASSWORD}
    ]
    assert fake_controller.connection_count == 1
    await client.async_disconnect()
    await wait_for(lambda: fake_controller.connection_count == 0)


@pytest.mark.parametrize(
    "login_error",
    [
        pytest.param("Login failed", id="text"),
        pytest.param(1, id="number"),
        pytest.param({"code": 1}, id="object"),
    ],
)
async def test_rejected_login_raises_auth_error(
    client: GreenlineLWSEClient, fake_controller: FakeController, login_error: Any
) -> None:
    """Test any login error is an authentication failure and closes the socket."""
    fake_controller.password = "changed-on-controller"
    fake_controller.login_error = login_error

    with pytest.raises(GreenlineLWSEAuthError):
        await client.async_connect()

    await wait_for(lambda: fake_controller.connection_count == 0)


async def test_unanswered_login_times_out(
    client: GreenlineLWSEClient, fake_controller: FakeController
) -> None:
    """Test a controller that never answers the login does not hang setup."""
    fake_controller.answer_login = False

    with pytest.raises(GreenlineLWSEConnectionError, match="Timed out"):
        await client.async_connect()

    await wait_for(lambda: fake_controller.connection_count == 0)


async def test_unreachable_controller_raises_connection_error(
    client: GreenlineLWSEClient, fake_controller: FakeController
) -> None:
    """Test connecting while the controller is switched off."""
    await fake_controller.stop()

    with pytest.raises(GreenlineLWSEConnectionError, match="Cannot connect"):
        await client.async_connect()


@pytest.mark.parametrize(
    ("status", "serial", "message"),
    [
        pytest.param(503, TEST_DEVICE_ID, "Could not retrieve", id="http-error"),
        pytest.param(200, "", "empty serial", id="empty"),
    ],
)
async def test_unavailable_serial_raises_connection_error(
    client: GreenlineLWSEClient,
    fake_controller: FakeController,
    status: int,
    serial: str,
    message: str,
) -> None:
    """Test a controller that cannot serve its serial (e.g. while booting)."""
    fake_controller.serial_status = status
    fake_controller.serial = serial

    with pytest.raises(GreenlineLWSEConnectionError, match=message):
        await client.async_connect()

    await wait_for(lambda: fake_controller.connection_count == 0)
    assert not fake_controller.commands("login")


@pytest.mark.usefixtures("running_client")
async def test_pushed_values_and_malformed_frames(
    fake_controller: FakeController, recorder: Recorder
) -> None:
    """Test pushes are forwarded while unexpected frames are ignored."""
    recorder.updates.clear()
    for frame in (
        "not-framed\n",
        "@{not-json}\n",
        "@[]\n",
        '@{"command":"HLVal","values":"invalid"}\n',
        '@{"command":"HLVal","values":[{"path":3,"result":"1"}]}\n',
        '@{"command":"unknown"}\n',
    ):
        await fake_controller.send_raw(frame)
    await fake_controller.push({TARGET: "22.0"})

    await wait_for(lambda: recorder.updates)
    assert recorder.updates == [{TARGET: "22.0"}]
    assert not recorder.errors


@pytest.mark.usefixtures("running_client")
async def test_set_value_round_trip(
    client: GreenlineLWSEClient, fake_controller: FakeController, recorder: Recorder
) -> None:
    """Test a written value is sent as text and confirmed by the controller."""
    await client.async_set_value(TARGET, 21.5)

    await wait_for(lambda: recorder.values[TARGET] == "21.5")
    assert fake_controller.commands("setVMValue") == [{"dap": TARGET, "value": "21.5"}]


@pytest.mark.usefixtures("running_client")
async def test_reconnects_and_restores_subscriptions(
    fake_controller: FakeController, recorder: Recorder
) -> None:
    """Test a dropped connection is re-established with all subscriptions."""
    recorder.values.clear()

    await fake_controller.drop_connections()

    await wait_for(lambda: {TARGET, WARM_WATER} <= recorder.values.keys())
    assert len(recorder.errors) == 1
    assert isinstance(recorder.errors[0], GreenlineLWSEConnectionError)
    assert fake_controller.login_count == 2
    assert fake_controller.commands("addHotlink")[2:] in (
        [{"dap": TARGET}, {"dap": WARM_WATER}],
        [{"dap": WARM_WATER}, {"dap": TARGET}],
    )


@pytest.mark.usefixtures("running_client")
async def test_recovers_after_controller_power_cycle(
    fake_controller: FakeController, recorder: Recorder
) -> None:
    """Test the client keeps retrying while the controller is off."""
    await fake_controller.stop()
    await wait_for(lambda: len(recorder.errors) >= 2)
    recorder.values.clear()

    await fake_controller.start()

    await wait_for(lambda: {TARGET, WARM_WATER} <= recorder.values.keys())
    assert fake_controller.connection_count == 1


async def test_password_change_stops_reconnecting(
    running_client: asyncio.Task[None],
    fake_controller: FakeController,
    recorder: Recorder,
) -> None:
    """Test changed credentials end the connection loop instead of retrying."""
    fake_controller.password = "changed-on-controller"

    await fake_controller.drop_connections()

    await asyncio.wait_for(asyncio.shield(running_client), 5)
    assert isinstance(recorder.errors[-1], GreenlineLWSEAuthError)
    assert fake_controller.login_count == 2


@pytest.mark.usefixtures("running_client")
async def test_replaced_controller_is_not_accepted(
    fake_controller: FakeController, recorder: Recorder
) -> None:
    """Test the client does not log in to a different controller on reconnect."""
    fake_controller.serial = "999999999999999"

    await fake_controller.drop_connections()

    await wait_for(lambda: len(recorder.errors) >= 3)
    assert all("serial changed" in str(err) for err in recorder.errors[1:])
    assert fake_controller.login_count == 1


async def test_disconnect_stops_connection_loop(
    client: GreenlineLWSEClient,
    running_client: asyncio.Task[None],
    fake_controller: FakeController,
    recorder: Recorder,
) -> None:
    """Test disconnecting closes the socket without reporting a lost connection."""
    await client.async_disconnect()

    await asyncio.wait_for(asyncio.shield(running_client), 5)
    await wait_for(lambda: fake_controller.connection_count == 0)
    assert not recorder.errors
    assert fake_controller.login_count == 1


async def test_write_without_connection_raises(client: GreenlineLWSEClient) -> None:
    """Test writing before connecting fails with a client error."""
    with pytest.raises(GreenlineLWSEConnectionError, match="Not connected"):
        await client.async_set_value(TARGET, 21.5)
