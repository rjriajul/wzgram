import asyncio

import pytest

from pyrogram import raw
from pyrogram.connection import Connection
from pyrogram.connection.transport import TCPAbridged
from pyrogram.errors import AuthKeyUnregistered
from pyrogram.session.session import Session, _serialize_file_part


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
    protocol_factory = TCPAbridged
    connection_factory = Connection
    init_connection_params = None
    dc_id = 2
    session = None
    connect_handler = None
    disconnect_handler = None

    class storage:
        conn = object()

        @staticmethod
        async def api_id():
            return 1

        @staticmethod
        async def open():
            pass


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


class _AlwaysFails:
    attempts = 0

    def __init__(self, *args, **kwargs):
        _AlwaysFails.attempts += 1

    async def connect(self):
        raise OSError("persistent outage")

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
    monkeypatch.setattr(DummyClient, "connection_factory", _AuthFailThenUnreg)

    started = asyncio.get_event_loop().time()
    with pytest.raises(AuthKeyUnregistered):
        await asyncio.wait_for(session_factory().start(), timeout=5)

    elapsed = asyncio.get_event_loop().time() - started
    assert _AuthFailThenUnreg.attempts == 2, (
        f"expected transient OSError then fatal auth, got {_AuthFailThenUnreg.attempts} attempts"
    )
    assert elapsed < 4, f"fatal error should propagate fast, took {elapsed:.1f}s"


async def test_bounded_start_raises_instead_of_looping(monkeypatch, session_factory):
    _AlwaysFails.attempts = 0
    monkeypatch.setattr(DummyClient, "connection_factory", _AlwaysFails)

    started = asyncio.get_event_loop().time()
    with pytest.raises(OSError):
        await asyncio.wait_for(session_factory().start(max_attempts=2), timeout=5)

    elapsed = asyncio.get_event_loop().time() - started
    assert _AlwaysFails.attempts == 2, (
        f"expected start to stop after max_attempts, got {_AlwaysFails.attempts} attempts"
    )
    assert elapsed < 4, f"max_attempts should cap retries, took {elapsed:.1f}s"


class _BlackHoleThenHealthy:
    attempts = 0

    def __init__(self, *args, **kwargs):
        _BlackHoleThenHealthy.attempts += 1
        self.attempt = _BlackHoleThenHealthy.attempts
        self.protocol = type("P", (), {"crypto_executor": None})()
        self.queue = asyncio.Queue()

    async def connect(self):
        pass

    async def close(self):
        pass

    async def send(self, payload):
        if self.attempt >= 2:
            self.queue.put_nowait(b"reply")

    async def recv(self):
        return await self.queue.get()


async def test_start_retry_still_dispatches_packets(monkeypatch, session_factory):
    _BlackHoleThenHealthy.attempts = 0
    monkeypatch.setattr(DummyClient, "connection_factory", _BlackHoleThenHealthy)

    s = session_factory()
    s.is_media = True
    s.is_cdn = True
    handled = []

    async def fake_handle_packet(packet):
        handled.append(packet)
        for result in list(s.results.values()):
            result.value = object()
            result.event.set()

    monkeypatch.setattr(s, "handle_packet", fake_handle_packet)
    monkeypatch.setattr(s.loop, "run_in_executor", lambda ex, fn, *a: _packed())

    await asyncio.wait_for(s.start(max_attempts=4), timeout=30)

    assert _BlackHoleThenHealthy.attempts == 2, (
        f"a healthy second attempt must succeed, took {_BlackHoleThenHealthy.attempts}"
    )
    assert handled, "packets on a retried attempt must reach handle_packet"
    assert not s._stopping, "_stopping must be cleared for each start attempt"

    await s.stop()


async def _packed():
    return b"packed"


async def test_send_timeout_normalises_error_and_frees_result(monkeypatch, session_factory):
    s = session_factory()

    async def never_completes(payload):
        await asyncio.sleep(30)

    s.connection = type("C", (), {
        "protocol": type("P", (), {"crypto_executor": None})(),
        "send": staticmethod(never_completes),
    })()
    monkeypatch.setattr(s.loop, "run_in_executor", lambda ex, fn, *a: _packed())

    with pytest.raises(TimeoutError, match="send timed out"):
        await s.send(raw.functions.Ping(ping_id=0), timeout=0.05)

    assert not s.results, f"a timed-out send must release its result slot, got {s.results}"


class _OutageConn:
    outage = False

    def __init__(self, *args, **kwargs):
        self.protocol = type("P", (), {"crypto_executor": None})()
        self.queue = asyncio.Queue()

    async def connect(self):
        if _OutageConn.outage:
            raise OSError("no route to host")

    async def close(self):
        pass

    async def send(self, payload):
        if _OutageConn.outage:
            raise OSError("broken pipe")
        self.queue.put_nowait(b"reply")

    async def recv(self):
        while True:
            if _OutageConn.outage:
                return None
            try:
                return self.queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)


async def _wait_until(predicate, timeout=10):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def test_dead_session_rearms_when_network_returns(monkeypatch):
    monkeypatch.setattr(DummyClient, "connection_factory", _OutageConn)
    monkeypatch.setattr(Session, "MAX_RETRIES", 2)
    monkeypatch.setattr(_OutageConn, "outage", False)

    s = Session(DummyClient(), 1, b"\x00" * 256, False, is_media=True, crypto_executor=None)
    s.is_cdn = True

    async def fake_handle_packet(packet):
        for result in list(s.results.values()):
            result.value = object()
            result.event.set()

    monkeypatch.setattr(s, "handle_packet", fake_handle_packet)
    monkeypatch.setattr(s.loop, "run_in_executor", lambda ex, fn, *a: _packed())

    await s.start(max_attempts=2)
    assert s.is_started.is_set()

    _OutageConn.outage = True
    assert await _wait_until(lambda: not s.is_started.is_set() and not s._start_active)
    assert isinstance(s._start_exc, OSError), (
        f"a restart driven by recv_worker must record why it failed, got {s._start_exc!r}"
    )

    _OutageConn.outage = False
    await asyncio.wait_for(
        s.invoke(raw.functions.Ping(ping_id=0), retries=3, timeout=1), timeout=15
    )
    assert s.is_started.is_set(), "invoke must re-arm a session nothing else will restart"

    await s.stop()


async def test_invoke_surfaces_real_start_failure(monkeypatch, session_factory):
    _AuthFailThenUnreg.attempts = 1
    monkeypatch.setattr(DummyClient, "connection_factory", _AuthFailThenUnreg)

    s = session_factory()

    started = asyncio.get_event_loop().time()
    with pytest.raises(AuthKeyUnregistered):
        await asyncio.wait_for(s.invoke(raw.functions.Ping(ping_id=0)), timeout=10)

    elapsed = asyncio.get_event_loop().time() - started
    assert elapsed < 4, f"a fatal start error must not be retried, took {elapsed:.1f}s"


async def test_invoke_waits_out_active_start_then_proceeds(monkeypatch, session_factory):
    s = session_factory()
    s._start_active = True
    s._start_completed.clear()
    assert not s.is_started.is_set()

    async def _finish_start():
        await asyncio.sleep(0.05)
        s.is_started.set()
        s._start_completed.set()

    task = asyncio.ensure_future(_finish_start())
    try:
        with pytest.raises(OSError, match="Connection is not established"):
            await asyncio.wait_for(
                s.invoke(raw.functions.Ping(ping_id=0), retries=1, timeout=1),
                timeout=2,
            )
    finally:
        await task


async def test_invoke_raises_bounded_start_error_after_active_finishes(monkeypatch, session_factory):
    _AlwaysFails.attempts = 0
    monkeypatch.setattr(DummyClient, "connection_factory", _AlwaysFails)
    monkeypatch.setattr(Session, "MAX_RETRIES", 2)

    s = session_factory()
    s._start_active = True
    s._start_completed.clear()

    async def _fail_start():
        await asyncio.sleep(0.05)
        s._start_active = False
        s._start_completed.set()

    task = asyncio.ensure_future(_fail_start())
    try:
        with pytest.raises(OSError, match="persistent outage"):
            await asyncio.wait_for(
                s.invoke(raw.functions.Ping(ping_id=0), retries=2, timeout=1), timeout=15
            )
    finally:
        await task

async def test_restart_tolerates_storage_without_conn(monkeypatch, session_factory):
    class NoConnStorage:
        @staticmethod
        async def api_id():
            return 1

        @staticmethod
        async def open():
            raise AssertionError("open must not be called for a storage without conn")

    monkeypatch.setattr(DummyClient, "connection_factory", _AlwaysFails)
    monkeypatch.setattr(DummyClient, "storage", NoConnStorage)
    monkeypatch.setattr(Session, "MAX_RETRIES", 1)

    with pytest.raises(OSError):
        await asyncio.wait_for(session_factory().restart(), timeout=5)


UPLOAD_PART_SIZES = [0, 1, 3, 4, 252, 253, 254, 255, 256, 1024, 512 * 1024, 512 * 1024 + 3]


def _upload_parts(payload):
    return [
        raw.functions.upload.SaveBigFilePart(
            file_id=7, file_part=1, file_total_parts=64, bytes=payload
        ),
        raw.functions.upload.SaveFilePart(file_id=7, file_part=1, bytes=payload),
    ]


@pytest.mark.parametrize("size", UPLOAD_PART_SIZES)
def test_hand_packed_upload_part_matches_the_generated_writer(size):
    payload = bytes(range(256)) * (size // 256) + bytes(range(size % 256))

    for part in _upload_parts(payload):
        assert _serialize_file_part(part) == part.write(), (
            f"{type(part).__name__} of {size} B serialises differently by hand"
        )


def test_only_upload_parts_take_the_hand_packed_path():
    assert _serialize_file_part(raw.functions.Ping(ping_id=0)) is None


async def test_send_hand_packs_upload_parts_and_declares_their_real_length(
    monkeypatch, session_factory
):
    s = session_factory()
    part = _upload_parts(bytes([0x11]) * (512 * 1024))[0]

    s.connection = type("C", (), {
        "protocol": type("P", (), {"crypto_executor": None})(),
        "send": staticmethod(lambda payload: _packed()),
    })()

    packed = []
    monkeypatch.setattr(
        "pyrogram.session.session.warpcrypto.pack_message",
        lambda msg_id, seq_no, serialized, *rest: packed.append(bytes(serialized)) or b"p",
    )

    declared = []
    real_factory = s.msg_factory
    s.msg_factory = lambda data, length: declared.append(length) or real_factory(data, length)

    await s.send(part, wait_response=False)

    assert packed[0] == part.write(), "the wire bytes must match the generated writer"
    assert declared == [len(packed[0])], (
        f"declared {declared} but put {len(packed[0])} B on the wire"
    )
