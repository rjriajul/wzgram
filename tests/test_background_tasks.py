import asyncio
import gc
import time
from datetime import datetime, timedelta

import pytest

import pyrogram
from pyrogram import raw
from pyrogram.connection.connection import Connection
from pyrogram.dispatcher import Dispatcher
from pyrogram.errors import PersistentTimestampInvalid, PersistentTimestampOutdated
from pyrogram.methods.advanced.recover_gaps import RecoverGaps
from pyrogram.session.auth import Auth


class _RefusingProtocol:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def connect(self, address):
        raise OSError("[Errno 111] Connect call failed")

    async def close(self):
        self.closed = True


async def test_a_failed_connect_says_what_went_wrong(monkeypatch):
    monkeypatch.setattr(Connection, "MAX_CONNECTION_ATTEMPTS", 2)

    connection = Connection(2, False, False, None, protocol_factory=_RefusingProtocol)

    with pytest.raises(OSError) as caught:
        await connection.connect()

    assert "Connect call failed" in str(caught.value), (
        "the socket error that actually stopped the connection must survive; "
        f"got {caught.value!r}"
    )


class _ClosingConnection:
    def __init__(self, *args, **kwargs):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def send(self, data):
        pass

    async def recv(self):
        return None


async def test_auth_reports_a_closed_socket_as_a_connection_error(monkeypatch):
    auth = Auth.__new__(Auth)
    auth.connection = _ClosingConnection()

    with pytest.raises(OSError) as caught:
        await auth.invoke(raw.functions.ReqPqMulti(nonce=1))

    assert not isinstance(caught.value, TypeError), (
        "a server that hangs up during the auth handshake must not surface as a "
        f"TypeError from BytesIO(None); got {caught.value!r}"
    )


async def test_auth_reports_a_transport_error_by_its_code(monkeypatch):
    class _TransportError(_ClosingConnection):
        async def recv(self):
            return (-404).to_bytes(4, "little", signed=True)

    auth = Auth.__new__(Auth)
    auth.connection = _TransportError()

    with pytest.raises(OSError) as caught:
        await auth.invoke(raw.functions.ReqPqMulti(nonce=1))

    assert "404" in str(caught.value), (
        f"the transport error the server sent must reach the caller, got {caught.value!r}"
    )


class _WatchdogClient:
    UPDATES_WATCHDOG_INTERVAL = 0.01
    updates_watchdog = pyrogram.Client.updates_watchdog

    def __init__(self, failure):
        self.updates_watchdog_event = asyncio.Event()
        self.last_update_time = datetime.now() - timedelta(days=1)
        self._last_update_monotonic = time.monotonic() - 86400
        self.failure = failure
        self.calls = 0

    async def invoke(self, query, **kwargs):
        self.calls += 1
        raise self.failure

    async def recover_gaps(self):
        return (0, 0)


async def test_the_updates_watchdog_survives_a_failed_poll():
    client = _WatchdogClient(TimeoutError("Request timed out"))

    task = asyncio.ensure_future(client.updates_watchdog())
    await asyncio.sleep(0.2)

    try:
        assert not task.done(), (
            "one failed poll must not retire the watchdog for the life of the "
            f"client; it died with {task.exception()!r}"
        )
        assert client.calls > 1, (
            f"the watchdog must keep polling after a failure, it polled {client.calls} time(s)"
        )
    finally:
        client.updates_watchdog_event.set()
        await asyncio.wait_for(task, timeout=5)


class _GapClient(RecoverGaps):
    _save_update_state = pyrogram.Client._save_update_state

    def __init__(self, error):
        self._state_marks = {}
        self.skip_updates = False
        self.error = error
        self.calls = 0
        self.deleted = []

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                if value is object:
                    return [(-100123, 5, 0, 7, 1)]
                if isinstance(value, int):
                    outer.deleted.append(value)

        self.storage = _Storage()

    async def resolve_peer(self, peer_id):
        return raw.types.InputChannel(channel_id=1, access_hash=0)

    async def invoke(self, query, **kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        PersistentTimestampOutdated(500, "PERSISTENT_TIMESTAMP_OUTDATED"),
        PersistentTimestampInvalid(400, "PERSISTENT_TIMESTAMP_INVALID"),
    ],
)
async def test_gap_recovery_gives_up_instead_of_spinning(error):
    client = _GapClient(error)

    started = time.monotonic()
    await asyncio.wait_for(client.recover_gaps(), timeout=10)
    elapsed = time.monotonic() - started

    assert client.calls < 10, (
        "an unusable persistent timestamp is re-sent unchanged, so retrying it "
        f"without a bound is a hot loop; it was sent {client.calls} times"
    )
    assert elapsed < 9


class _HandlerlessClient:
    listeners = None


def test_registering_a_handler_outside_a_loop_leaves_no_coroutine_behind(recwarn):
    dispatcher = Dispatcher(_HandlerlessClient())
    handler = object()

    dispatcher.add_handler(handler, 0)

    assert dispatcher.groups == {0: [handler]}

    dispatcher.remove_handler(handler, 0)

    assert dispatcher.groups == {}

    gc.collect()

    unawaited = [w for w in recwarn.list if "never awaited" in str(w.message)]

    assert not unawaited, (
        "the coroutine must not be built before the loop it needs is known; "
        f"got {[str(w.message) for w in unawaited]}"
    )
