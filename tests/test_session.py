import asyncio
import time

import pytest

import pyrogram.session.session as session_mod
from pyrogram import raw
from pyrogram.connection.transport import TCP
from pyrogram.errors import AuthKeyUnregistered
from pyrogram.session.session import Session


class DummyClient:
    name = "regress"
    app_version = "1.0"
    device_model = "Test"
    system_version = "Linux"
    lang_code = "en"
    loop = None
    is_media = False
    proxy = None
    ipv6 = False
    dc_id = 2
    disconnect_handler = None


class _AuthFailThenUnreg:
    kills_with_unregistered_on = 0
    attempts = 0

    def __init__(self, *args, **kwargs):
        _AuthFailThenUnreg.attempts += 1

    async def connect(self):
        if self.attempts == 1:
            raise OSError("transient socket failure")
        raise AuthKeyUnregistered(401, "AUTH_KEY_UNREGISTERED")

    async def close(self):
        pass


@pytest.fixture
def session_factory():
    return lambda: Session(
        DummyClient(),
        1,
        b"\x00" * 256,
        False,
        is_media=False,
        crypto_executor=None,
    )


async def test_fatal_auth_after_transient_retry_propagates(monkeypatch, session_factory):
    _AuthFailThenUnreg.attempts = 0
    monkeypatch.setattr(session_mod, "Connection", _AuthFailThenUnreg)

    started = asyncio.get_event_loop().time()
    with pytest.raises(AuthKeyUnregistered):
        await asyncio.wait_for(session_factory().start(), timeout=5)

    elapsed = asyncio.get_event_loop().time() - started
    assert _AuthFailThenUnreg.attempts == 2, (
        f"expected transient OSError then fatal auth, got {_AuthFailThenUnreg.attempts} attempts"
    )
    assert elapsed < 4, f"fatal error should propagate fast, took {elapsed:.1f}s"


def _timing_out_session(session_factory, last_packet_age: float, failures: int = 1):
    session = session_factory()
    session.is_started.set()
    session._last_packet = time.monotonic() - last_packet_age
    session.restarts = 0
    session.sent = 0

    async def fake_restart():
        session.restarts += 1

    async def fake_send(query, wait_response=True, timeout=None, retry=0):
        session.sent += 1
        if session.sent <= failures:
            raise TimeoutError("Request timed out")
        return "ok"

    session.restart = fake_restart
    session.send = fake_send

    return session


async def test_request_timeout_keeps_live_session(session_factory):
    session = _timing_out_session(session_factory, last_packet_age=0)

    assert await session.invoke(raw.functions.Ping(ping_id=0)) == "ok"
    assert session.restarts == 0, (
        "a single timed-out request must not tear down a session that is still "
        "receiving — that fails every other request in flight on it"
    )
    assert session.sent == 2


async def test_request_timeout_restarts_silent_session(session_factory):
    session = _timing_out_session(session_factory, last_packet_age=Session.WAIT_TIMEOUT + 5)

    assert await session.invoke(raw.functions.Ping(ping_id=0)) == "ok"
    assert session.restarts == 1, "a session receiving nothing at all must be restarted"


async def test_start_attempts_are_bounded(monkeypatch, session_factory):
    class _AlwaysRefused:
        def __init__(self, *args, **kwargs):
            _AlwaysRefused.attempts += 1

        async def connect(self):
            raise OSError("connection refused")

        async def close(self):
            pass

    _AlwaysRefused.attempts = 0
    monkeypatch.setattr(session_mod, "Connection", _AlwaysRefused)

    session = session_factory()

    with pytest.raises(OSError):
        await asyncio.wait_for(session.start(max_attempts=3), timeout=10)

    assert _AlwaysRefused.attempts == 3, (
        f"start() must stop after max_attempts, tried {_AlwaysRefused.attempts}"
    )


async def test_send_deadline_excludes_queued_writers():
    class _SlowWriter:
        def __init__(self):
            self.written = []

        def write(self, data):
            self.written.append(data)

        async def drain(self):
            await asyncio.sleep(0.15)

    tcp = TCP.__new__(TCP)
    tcp.lock = asyncio.Lock()
    tcp.writer = _SlowWriter()

    await asyncio.gather(*(tcp.send(b"part", 0.3) for _ in range(4)))

    assert len(tcp.writer.written) == 4, (
        "the send deadline must cover only this write, not the time spent "
        "queued behind other writers on the same connection"
    )


async def test_is_usable_covers_in_flight_restart(session_factory):
    session = session_factory()

    assert not session.is_usable

    session.is_started.set()
    assert session.is_usable

    session.is_started.clear()
    session._restart_done.clear()
    assert session.is_usable, "a session mid-restart must not be dropped and replaced"

    session._restart_done.set()
    assert not session.is_usable

async def test_midmessage_read_timeout_is_fatal(monkeypatch):
    from pyrogram.connection.transport import TCPAbridged

    monkeypatch.setattr(TCP, "TIMEOUT", 0.05)

    class _StallingReader:
        def __init__(self):
            self.reads = 0

        async def read(self, n):
            self.reads += 1
            if self.reads == 1:
                return b"\x02"
            await asyncio.sleep(1)
            return b""

    tcp = TCPAbridged.__new__(TCPAbridged)
    tcp.reader = _StallingReader()

    with pytest.raises(OSError) as exc:
        await tcp.recv()

    assert not isinstance(exc.value, TimeoutError), (
        "a timeout after the length prefix leaves the stream desynced; it must "
        "not look like a benign idle-read timeout the recv loop can continue past"
    )


async def test_slow_drain_is_not_reported_as_a_dead_socket(monkeypatch):
    monkeypatch.setattr(TCP, "TIMEOUT", 0.05)

    class _StallingWriter:
        def write(self, data):
            pass

        async def drain(self):
            await asyncio.sleep(1)

    tcp = TCP.__new__(TCP)
    tcp.writer = _StallingWriter()
    tcp.lock = asyncio.Lock()

    with pytest.raises(TimeoutError):
        await tcp.send(b"\x00\x00\x00\x00")


async def test_slow_drain_keeps_the_request_in_flight(session_factory):
    from types import SimpleNamespace

    session = session_factory()
    drain_deadlines = []

    class _Connection:
        protocol = SimpleNamespace(crypto_executor=None)

        async def send(self, payload, timeout=None):
            drain_deadlines.append(timeout)
            raise TimeoutError("Socket write backpressure")

    session.connection = _Connection()

    async def _reply_late():
        while not session.results:
            await asyncio.sleep(0)
        for result in session.results.values():
            result.value = "pong"
            result.event.set()

    asyncio.ensure_future(_reply_late())

    got = await session.send(raw.functions.Ping(ping_id=0), timeout=Session.MEDIA_TIMEOUT)

    assert got == "pong", (
        "the payload is already in the transport when drain times out — failing "
        "the request just puts a duplicate part on the link that is the bottleneck"
    )
    assert drain_deadlines == [Session.WAIT_TIMEOUT], (
        "the drain deadline bounds how long a write holds the connection lock, so "
        "it must stay capped even for media requests or the ping cannot get out"
    )
