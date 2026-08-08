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