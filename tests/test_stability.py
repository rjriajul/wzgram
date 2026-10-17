import asyncio
import gc
import logging
import socket
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import pyrogram
import pyrogram.session.session as session_mod
from pyrogram import raw
from pyrogram.connection import Connection
from pyrogram.connection.connection import Connection
from pyrogram.connection.transport.tcp.tcp import TCP
from pyrogram.connection.transport.tcp.tcp_abridged import TCPAbridged
from pyrogram.dispatcher import Dispatcher
from pyrogram.errors import (
    UnknownError,
    PersistentTimestampInvalid,
    PersistentTimestampOutdated,
    PeerIdInvalid,
)
from pyrogram.errors.rpc_error import RPCError
from pyrogram.file_id import FileId, FileType
from pyrogram.methods.advanced.recover_gaps import RecoverGaps
from pyrogram.session.auth import Auth
from pyrogram.session.internals import MsgId
from pyrogram.session.session import ConnectionLost, Result, Session
from pyrogram.storage import SQLiteStorage
from tests.test_audit_regressions import make_dispatcher as make_audit_dispatcher
from tests.test_session import DummyClient as SessionDummyClient


class DummyClient:
    name = "stability"
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

    def __init__(self):
        self.updates = []

    async def handle_updates(self, body):
        self.updates.append(body)


class RecordingConnection:

    def __init__(self):
        self.protocol = SimpleNamespace(crypto_executor=None)
        self.closed = False
        self.sent = []

    async def connect(self):
        pass

    async def close(self):
        self.closed = True

    async def send(self, payload):
        self.sent.append(payload)

    async def recv(self):
        await asyncio.sleep(3600)


def make_session(client=None):
    return Session(
        client or DummyClient(),
        1,
        b"\x00" * 256,
        False,
        is_media=False,
        crypto_executor=None,
    )


async def _packed(*args, **kwargs):
    return b"packed"


def unpacked_as(msg_id: int, body: bytes):
    # small packets are decrypted inline, so the seam is the decrypt call itself
    length = len(body)
    total_len = 16 + length + 16

    def run(*args, **kwargs):
        return msg_id, 1, length, body, total_len

    return run


async def test_a_replayed_msg_id_is_dropped_without_closing_the_connection(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    msg_id = MsgId()
    msg_id |= 1  # msg_id must be odd
    body = raw.types.Pong(msg_id=msg_id, ping_id=0).write()

    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(msg_id, body))

    await session.handle_packet(b"ignored")
    assert session.stored_msg_ids == [msg_id]

    await session.handle_packet(b"ignored")

    assert session.stored_msg_ids == [msg_id], "a replayed msg_id must not be stored twice"
    assert not session.connection.closed, (
        "a duplicate msg_id must not cost a reconnect"
    )


async def test_a_msg_id_below_the_replay_window_is_dropped_not_fatal(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    recent = MsgId() | 1
    stale = recent - (1 << 33)  # comfortably below the pruned floor
    session.stored_msg_ids = [recent]
    session._msg_id_floor = recent - (1 << 32)

    body = raw.types.Pong(msg_id=stale, ping_id=0).write()
    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(stale, body))

    await session.handle_packet(b"ignored")

    assert not session.connection.closed
    assert session.stored_msg_ids == [recent]


async def test_an_out_of_order_msg_id_is_not_mistaken_for_a_replay(monkeypatch):
    """The oldest msg_id seen so far is not by itself a replay window.

    Rejecting everything below stored_msg_ids[0] discards legitimate messages -
    an RpcResult among them - whenever the server hands us msg_ids out of
    ascending order, which a MsgContainer is free to do. The floor only means
    something once entries have actually been pruned away.
    """
    session = make_session()
    session.connection = RecordingConnection()

    later = MsgId() | 1
    earlier = later - (1 << 32) - 4

    for msg_id in (later, earlier):
        body = raw.types.Pong(msg_id=msg_id, ping_id=0).write()
        monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(msg_id, body))
        await session.handle_packet(b"ignored")

    assert session.stored_msg_ids == [earlier, later], (
        "a msg_id never seen before and inside the time window is not a replay "
        "merely for arriving after a higher one"
    )
    assert not session.connection.closed


async def test_pruning_the_window_is_what_arms_the_floor(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    base = MsgId() >> 32
    session.stored_msg_ids = [
        (base << 32) | (i << 2) | 1
        for i in range(Session.STORED_MSG_IDS_MAX_SIZE + 1)
    ]
    pruned = session.stored_msg_ids[Session.STORED_MSG_IDS_MAX_SIZE // 2 - 1]

    fresh = (base << 32) | ((Session.STORED_MSG_IDS_MAX_SIZE + 8) << 2) | 1
    body = raw.types.Pong(msg_id=fresh, ping_id=0).write()
    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(fresh, body))

    await session.handle_packet(b"ignored")

    assert session._msg_id_floor == pruned, (
        "dropping the older half of the window must record what was dropped, or "
        "those msg_ids become replayable"
    )
    assert len(session.stored_msg_ids) == Session.STORED_MSG_IDS_MAX_SIZE // 2 + 2


async def test_a_clock_skew_mismatch_drops_the_message_not_the_connection(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    session.stored_msg_ids = [MsgId() | 1]

    future = ((MsgId() >> 32) + 600) << 32 | 1
    body = raw.types.Pong(msg_id=future, ping_id=0).write()
    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(future, body))

    await session.handle_packet(b"ignored")

    assert not session.connection.closed, (
        "one skewed packet must cost one message, not a full reconnect and "
        "handshake that the next packet will trip all over again"
    )
    assert future not in session.stored_msg_ids
    assert session._skew_breaches == 1


async def test_a_broken_packet_tears_the_connection_down_exactly_once(monkeypatch, caplog):
    session = make_session()
    session.connection = RecordingConnection()

    restarts = []

    async def record_restart():
        restarts.append(1)

    monkeypatch.setattr(session, "_safe_restart", record_restart)

    body = raw.types.Pong(msg_id=1, ping_id=0).write()

    def unpack(*args, **kwargs):
        return 2, 1, len(body), body, 16 + len(body) + 16  # an even msg_id is a violation

    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpack)

    with caplog.at_level(logging.WARNING, logger="pyrogram.session.session"):
        await asyncio.gather(*(
            session.handle_packet(b"ignored")
            for _ in range(Session.MAX_INFLIGHT_PACKETS)
        ))

    await asyncio.sleep(0)

    assert restarts == [1], (
        "every packet already decrypted when the connection went bad must not "
        "queue a restart of its own"
    )
    assert len([
        r for r in caplog.records if "closing connection" in r.getMessage()
    ]) == 1


class ClosingWriter:
    """Stands in for an asyncio transport, which swallows a write once closed."""

    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, data):
        if not self.closed:
            self.written.append(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


async def test_a_write_to_a_closed_transport_is_refused_not_swallowed():
    transport = TCP(False, None)
    transport.writer = ClosingWriter()
    transport.is_connected = True

    await transport.send(b"before")
    assert transport.writer.written == [b"before"]

    await transport.close()

    with pytest.raises(OSError):
        await transport.send(b"after")

    assert transport.writer.written == [b"before"], (
        "asyncio drops a write to a closed transport and logs it itself, so a "
        "send that is not refused here is recorded as delivered and then spends "
        "the whole timeout waiting for a reply to bytes that never left"
    )


async def test_in_flight_requests_report_a_lost_connection_not_a_timeout(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)

    pending = asyncio.ensure_future(
        session.send(raw.functions.Ping(ping_id=0), timeout=30)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert session.results, "the request should be waiting for a reply"

    await session.stop()

    with pytest.raises(ConnectionResetError):
        await asyncio.wait_for(pending, timeout=5)


async def test_a_genuine_timeout_is_still_reported_as_one(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)

    with pytest.raises(TimeoutError, match="Request timed out"):
        await session.send(raw.functions.Ping(ping_id=0), timeout=0.05)


class _HandshakeFailingConnection(RecordingConnection):
    """Refuses the handshake, whichever of send and recv the loop runs first."""

    reply = None

    def __init__(self):
        super().__init__()
        self.requested = asyncio.Event()

    async def send(self, payload):
        await super().send(payload)
        self.requested.set()

    async def recv(self):
        await self.requested.wait()

        if isinstance(self.reply, BaseException):
            raise self.reply

        return self.reply


async def _failed_handshake(monkeypatch, reply):
    conn = _HandshakeFailingConnection()
    conn.reply = reply

    session = make_session()
    monkeypatch.setattr(DummyClient, "connection_factory", lambda *a, **kw: conn)
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)
    monkeypatch.setattr(Session, "START_TIMEOUT", 5)

    started = time.monotonic()

    with pytest.raises(BaseException) as caught:
        await asyncio.wait_for(session.start(max_attempts=1), timeout=30)

    return caught.value, time.monotonic() - started


async def test_a_transport_error_during_the_handshake_names_itself(monkeypatch):
    error, elapsed = await _failed_handshake(monkeypatch, (-404).to_bytes(4, "little", signed=True))

    assert isinstance(error, ConnectionResetError), (
        "a server that refuses the handshake must not be reported as a timeout, "
        f"got {error!r}"
    )
    assert "404" in str(error) and "auth key not found" in str(error), (
        f"the transport error the server sent must reach the caller, got {error!r}"
    )
    assert elapsed < Session.START_TIMEOUT, (
        f"the handshake must fail as soon as the server answers, took {elapsed:.2f}s"
    )


async def test_a_drop_during_the_handshake_is_not_a_timeout(monkeypatch):
    error, elapsed = await _failed_handshake(monkeypatch, ConnectionResetError("peer closed"))

    assert isinstance(error, ConnectionResetError) and not isinstance(error, TimeoutError), (
        f"a connection lost mid-handshake must raise ConnectionResetError, got {error!r}"
    )
    assert elapsed < Session.START_TIMEOUT, (
        f"the handshake must fail as soon as the socket dies, took {elapsed:.2f}s"
    )


async def test_connection_loss_is_retried_by_invoke(monkeypatch):
    session = make_session()
    session.is_started.set()

    attempts = []
    sentinel = object()

    async def send(data, timeout=None, **kwargs):
        attempts.append(data)
        if len(attempts) == 1:
            raise ConnectionResetError("Connection lost while awaiting a response")
        return sentinel

    monkeypatch.setattr(session, "send", send)
    monkeypatch.setattr(session, "restart", _packed)

    assert await session.invoke(raw.functions.Ping(ping_id=0)) is sentinel
    assert len(attempts) == 2, "the dropped request should have been re-sent once"


async def test_stop_leaves_an_already_answered_result_alone():
    session = make_session()
    session.connection = RecordingConnection()

    answered = Result()
    answered.value = "the real answer"
    session.results = {1: answered}

    await session.stop()

    assert answered.value == "the real answer", (
        "a reply that already arrived must not be overwritten by the shutdown marker"
    )
    assert answered.value is not ConnectionLost


async def test_the_receive_loop_stops_reading_once_the_decrypt_backlog_is_full():
    session = make_session()

    reads = 0
    blocked = asyncio.Event()

    class FloodingConnection(RecordingConnection):
        async def recv(self):
            nonlocal reads
            reads += 1
            await asyncio.sleep(0)
            return b"\x00" * 64

    session.connection = FloodingConnection()
    session._packet_semaphore = asyncio.Semaphore(2)

    async def never_finishes(packet):
        await blocked.wait()

    session.handle_packet = never_finishes

    worker = asyncio.ensure_future(session.recv_worker())
    await asyncio.sleep(0.1)

    try:
        assert reads <= 3, (
            "with 2 decrypt slots the loop may read 2 packets and block on the "
            f"third; it read {reads}, so nothing is throttling the socket"
        )

        settled = reads
        await asyncio.sleep(0.1)
        assert reads == settled, "a blocked backlog must not keep draining the socket"
    finally:
        blocked.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def _reads_under_cap(session, handler, cap=2, limit=20, timeout=5):
    reads = 0

    class CountingConnection(RecordingConnection):
        async def recv(self):
            nonlocal reads
            reads += 1
            if reads > limit:
                await asyncio.sleep(3600)
            await asyncio.sleep(0)
            return b"\x00" * 64

    session.connection = CountingConnection()
    session._packet_semaphore = asyncio.Semaphore(cap)
    session.handle_packet = handler

    worker = asyncio.ensure_future(session.recv_worker())

    # Wait for the loop to get past the cap rather than for a fixed stretch of
    # wall clock. A handler that raises costs a formatted traceback per packet,
    # so a timed window measures how fast the runner is, not whether the
    # semaphore came back.
    deadline = time.monotonic() + timeout

    while reads <= cap and time.monotonic() < deadline:
        await asyncio.sleep(0)

    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    return reads


async def test_a_handled_packet_returns_its_slot():
    async def instant(packet):
        return None

    reads = await _reads_under_cap(make_session(), instant)

    assert reads > 2, (
        "slots must come back as packets complete, or the loop wedges after "
        f"MAX_INFLIGHT_PACKETS messages; it stopped at {reads}"
    )


async def test_a_failing_packet_also_returns_its_slot():
    async def explodes(packet):
        raise ValueError("bad packet")

    reads = await _reads_under_cap(make_session(), explodes)

    assert reads > 2, (
        f"a packet that raised must not leak its slot; the loop stopped at {reads}"
    )


class FragmentedReader:

    def __init__(self, payload: bytes, piece: int = 7):
        self.buf = payload
        self.piece = piece
        self.calls = 0

    async def read(self, n):
        self.calls += 1
        take = min(n, self.piece)
        out, self.buf = self.buf[:take], self.buf[take:]
        return out


def make_transport(payload: bytes, piece: int = 7):
    transport = TCP(False, None)
    transport.reader = FragmentedReader(payload, piece)
    return transport


async def test_recv_reassembles_a_fragmented_message():
    payload = bytes(range(256)) * 4
    transport = make_transport(payload)

    got = await transport.recv(len(payload))

    assert got == payload
    assert transport.reader.calls > 1, "the payload should have arrived in pieces"


async def test_recv_of_nothing_is_empty_not_none():
    assert await make_transport(b"").recv(0) == b""


async def test_recv_reports_a_closed_socket_as_none():
    assert await make_transport(b"ab").recv(8) is None, (
        "a short read means the peer went away"
    )


async def test_an_abridged_frame_still_round_trips():
    body = b"A" * 64
    framed = bytes([len(body) // 4]) + body

    protocol = TCPAbridged(False, None)
    protocol.reader = FragmentedReader(framed, piece=5)

    assert await protocol.recv() == body


class FakeSocket:
    def __init__(self, existing: int):
        self.existing = existing
        self.applied = {}

    def getsockopt(self, level, option):
        return self.existing

    def setsockopt(self, level, option, value):
        self.applied[option] = value


def apply_buffers(sock):
    if TCP.SOCKET_BUFFER > 0:
        for option in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            current = sock.getsockopt(socket.SOL_SOCKET, option)
            if TCP.SOCKET_BUFFER > current:
                sock.setsockopt(socket.SOL_SOCKET, option, TCP.SOCKET_BUFFER)


def test_the_socket_buffer_is_never_shrunk_below_the_os_default(monkeypatch):
    monkeypatch.setattr(TCP, "SOCKET_BUFFER", 256 * 1024)
    sock = FakeSocket(existing=8 * 1024 * 1024)

    apply_buffers(sock)

    assert sock.applied == {}, "a host tuned for large buffers must keep them"


def test_the_socket_buffer_is_raised_when_the_default_is_tiny(monkeypatch):
    monkeypatch.setattr(TCP, "SOCKET_BUFFER", 256 * 1024)
    sock = FakeSocket(existing=4096)

    apply_buffers(sock)

    assert sock.applied[socket.SO_SNDBUF] == 256 * 1024
    assert sock.applied[socket.SO_RCVBUF] == 256 * 1024


def test_the_socket_buffer_can_be_left_to_the_os(monkeypatch):
    monkeypatch.setattr(TCP, "SOCKET_BUFFER", 0)
    sock = FakeSocket(existing=4096)

    apply_buffers(sock)

    assert sock.applied == {}


def test_the_kernel_autotunes_socket_buffers_by_default():
    assert TCP.SOCKET_BUFFER == 0, (
        "pinning SO_SNDBUF/SO_RCVBUF disables autotuning, so every session pays "
        "the fixed size in kernel memory and cannot grow on a high-latency link"
    )


def make_dispatcher(**kwargs):
    client = SimpleNamespace(
        workers=1,
        no_updates=False,
        rate_limiter=None,
        start_handler=None,
        stop_handler=None,
        **kwargs
    )
    return Dispatcher(client)


async def test_an_update_is_queued_when_there_is_room():
    dispatcher = make_dispatcher()

    assert await dispatcher.enqueue_update("update", {}, {}) is True
    assert dispatcher.updates_queue.qsize() == 1


async def test_a_full_queue_waits_for_room_instead_of_raising(monkeypatch):
    dispatcher = make_dispatcher()
    dispatcher.handler_worker_tasks.append(asyncio.Future())
    monkeypatch.setattr(Dispatcher, "ENQUEUE_TIMEOUT", 5)

    for _ in range(dispatcher.updates_queue.maxsize):
        dispatcher.updates_queue.put_nowait(("filler", {}, {}))

    pending = asyncio.ensure_future(dispatcher.enqueue_update("late", {}, {}))
    await asyncio.sleep(0.05)
    assert not pending.done(), "a burst should be absorbed by waiting, not dropped"

    await dispatcher.updates_queue.get()

    assert await asyncio.wait_for(pending, timeout=2) is True


async def test_a_permanently_full_queue_drops_and_says_so(monkeypatch, caplog):
    dispatcher = make_dispatcher()
    dispatcher.handler_worker_tasks.append(asyncio.Future())
    monkeypatch.setattr(Dispatcher, "ENQUEUE_TIMEOUT", 0.05)

    for _ in range(dispatcher.updates_queue.maxsize):
        dispatcher.updates_queue.put_nowait(("filler", {}, {}))

    with caplog.at_level("WARNING"):
        queued = await dispatcher.enqueue_update("late", {}, {})

    assert queued is False
    assert "Dropping" in caplog.text, "a dropped update must not be silent"


async def test_a_full_queue_with_no_handler_workers_drops_at_once_and_warns_once(monkeypatch, caplog):
    dispatcher = make_dispatcher()
    monkeypatch.setattr(Dispatcher, "ENQUEUE_TIMEOUT", 5)

    for _ in range(dispatcher.updates_queue.maxsize):
        dispatcher.updates_queue.put_nowait(("filler", {}, {}))

    with caplog.at_level("WARNING"):
        results = await asyncio.wait_for(
            asyncio.gather(*(dispatcher.enqueue_update("late", {}, {}) for _ in range(3))),
            timeout=1
        )

    assert results == [False, False, False]
    assert caplog.text.count("no handler worker is running") == 1
    assert "cannot keep up" not in caplog.text


async def test_a_full_queue_waits_while_the_start_handler_runs(monkeypatch):
    monkeypatch.setattr(Dispatcher, "ENQUEUE_TIMEOUT", 5)
    release = asyncio.Event()
    entered = asyncio.Event()

    async def start_handler(_):
        entered.set()
        await release.wait()

    dispatcher = make_dispatcher(skip_updates=True, loop=asyncio.get_running_loop())
    dispatcher.client.start_handler = start_handler

    for _ in range(dispatcher.updates_queue.maxsize):
        dispatcher.updates_queue.put_nowait(("filler", {}, {}))

    starting = asyncio.ensure_future(dispatcher.start())
    await entered.wait()

    pending = asyncio.ensure_future(dispatcher.enqueue_update("late", {}, {}))
    await asyncio.sleep(0.05)
    assert not pending.done()

    await dispatcher.updates_queue.get()
    assert await asyncio.wait_for(pending, timeout=2) is True

    release.set()
    await starting
    assert dispatcher.starting is False
    await dispatcher.stop()


async def test_the_updates_queue_stays_bounded():
    dispatcher = make_dispatcher()

    assert dispatcher.updates_queue.maxsize > 0, (
        "an unbounded update queue turns a slow handler into unbounded memory use"
    )


async def test_update_batches_waiting_for_handlers_are_capped(monkeypatch, caplog):
    class BlockedClient(DummyClient):
        def __init__(self):
            super().__init__()
            self.gate = asyncio.Event()

        async def handle_updates(self, body):
            await self.gate.wait()
            self.updates.append(body)

    client = BlockedClient()
    session = make_session(client)
    session.connection = RecordingConnection()
    monkeypatch.setattr(Session, "MAX_PENDING_UPDATES", 40)

    body = raw.types.UpdatesTooLong().write()
    base = MsgId() | 1

    with caplog.at_level("WARNING"):
        for i in range(100):
            monkeypatch.setattr(
                session_mod.warpcrypto, "unpack_message", unpacked_as(base + 4 * i, body)
            )
            await session.handle_packet(b"ignored")

        assert session._pending_updates == 40, (
            "update batches must stop piling up once handlers fall behind"
        )
        assert session._dropped_updates == 60
        assert caplog.text.count("Dropping") == 1, "one warning per overload, not one per batch"

        client.gate.set()

        for _ in range(100):
            if session._pending_updates == 0:
                break
            await asyncio.sleep(0.01)

    assert len(client.updates) == 40
    assert session._pending_updates == 0
    assert session._dropped_updates == 0
    assert "Dropped 60 update batches" in caplog.text


class FakeSession:
    def __init__(self, last_used: float, results=None):
        self.last_used = last_used
        self.results = results or {}
        self.stopped = False
        self.is_started = asyncio.Event()
        self.is_started.set()

    async def stop(self):
        self.stopped = True
        self.is_started.clear()


class ReapableClient:
    reap_media_sessions = pyrogram.Client.reap_media_sessions
    MEDIA_SESSION_IDLE_TIMEOUT = pyrogram.Client.MEDIA_SESSION_IDLE_TIMEOUT

    def __init__(self):
        self.media_session_pools = {}
        self._media_sessions_locks = {}
        self.media_sessions = {}
        self.sessions = {}
        self._session_locks = {}
        self.session = FakeSession(last_used=0)


async def test_reaping_also_closes_the_idle_per_dc_sessions():
    import time

    now = time.monotonic()
    client = ReapableClient()

    idle_media = FakeSession(last_used=now - 10_000)
    idle_foreign = FakeSession(last_used=now - 10_000)
    busy_media = FakeSession(last_used=now - 10_000, results={1: object()})
    fresh_foreign = FakeSession(last_used=now)
    client.media_sessions = {2: idle_media, 4: busy_media}
    client.sessions = {2: idle_foreign, 4: fresh_foreign, 1: client.session}

    reaped = await client.reap_media_sessions(idle_timeout=300)

    assert reaped == 2
    assert idle_media.stopped and idle_foreign.stopped
    assert not busy_media.stopped and not fresh_foreign.stopped
    assert not client.session.stopped, "the main session is never reaped"
    assert client.media_sessions == {4: busy_media}
    assert client.sessions == {4: fresh_foreign, 1: client.session}, (
        "a stopped session left in the dict would be handed out again and fail"
    )


async def test_reaping_closes_idle_sessions_and_keeps_busy_ones():
    import time

    now = time.monotonic()
    client = ReapableClient()

    busy = FakeSession(last_used=now)
    idle = FakeSession(last_used=now - 10_000)
    client.media_session_pools[2] = [busy, idle]

    reaped = await client.reap_media_sessions(idle_timeout=300)

    assert reaped == 1
    assert idle.stopped and not busy.stopped
    assert client.media_session_pools[2] == [busy]


async def test_reaping_forgets_a_datacenter_once_its_pool_is_empty():
    import time

    client = ReapableClient()
    client.media_session_pools[2] = [FakeSession(last_used=time.monotonic() - 10_000)]

    await client.reap_media_sessions(idle_timeout=300)

    assert 2 not in client.media_session_pools, (
        "an emptied pool must be dropped, not left as a stale key"
    )


async def test_reaping_keeps_everything_when_nothing_is_idle():
    import time

    client = ReapableClient()
    fresh = [FakeSession(last_used=time.monotonic()) for _ in range(3)]
    client.media_session_pools[2] = list(fresh)

    assert await client.reap_media_sessions(idle_timeout=300) == 0
    assert client.media_session_pools[2] == fresh


async def test_reaping_spares_a_session_with_a_request_still_in_flight():
    import time

    client = ReapableClient()
    stalled = FakeSession(last_used=time.monotonic() - 10_000, results={1: object()})
    client.media_session_pools[2] = [stalled]

    assert await client.reap_media_sessions(idle_timeout=300) == 0
    assert not stalled.stopped, (
        "an RPC blocked on a long flood-wait leaves last_used stale; closing "
        "the session under it would fail the request"
    )


async def test_invoking_marks_a_session_as_recently_used(monkeypatch):
    session = make_session()
    session.is_started.set()
    session.last_used = 0.0

    monkeypatch.setattr(session, "send", _packed)

    await session.invoke(raw.functions.Ping(ping_id=0))

    assert session.last_used > 0.0


async def test_a_keepalive_ping_does_not_count_as_use(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)
    session.last_used = 0.0

    await session.send(raw.functions.PingDelayDisconnect(ping_id=0, disconnect_delay=25), False)

    assert session.last_used == 0.0, (
        "pings must not keep an otherwise idle pooled session alive forever"
    )
CHUNK = 1024 * 1024


class ChunkSession:

    def __init__(self, file_size: int):
        self.file_size = file_size
        self.served = 0

    async def invoke(self, query, *args, **kwargs):
        self.served += 1
        remaining = max(0, self.file_size - query.offset)
        return raw.types.upload.File(
            type=raw.types.storage.FilePartial(),
            mtime=0,
            bytes=b"\x00" * min(CHUNK, remaining),
        )


def make_download_client(monkeypatch, session):
    client = pyrogram.Client("buffering", api_id=1, api_hash="x", in_memory=True)
    client.me = SimpleNamespace(is_bot=False, is_premium=False)

    async def get_session(*args, **kwargs):
        return session

    async def pool(dc_id, n):
        return [session] * n

    monkeypatch.setattr(client, "get_session", get_session)
    monkeypatch.setattr(client, "_get_media_session_pool", pool)
    return client


async def test_a_slow_consumer_does_not_let_the_whole_file_into_memory(monkeypatch):
    file_size = 400 * CHUNK
    session = ChunkSession(file_size)
    client = make_download_client(monkeypatch, session)

    file_id = FileId(file_type=FileType.DOCUMENT, dc_id=2, media_id=1, access_hash=1)

    consumed = 0
    async for _chunk in client.get_file(file_id, file_size):
        consumed += 1
        await asyncio.sleep(0.3)
        if consumed == 5:
            break

    read_ahead = session.served - consumed
    budget = pyrogram.Client.MAX_READ_AHEAD_CHUNKS

    assert read_ahead <= budget + 8, (
        f"workers buffered {read_ahead} chunks ahead of the consumer against a "
        f"budget of {budget}. The rate limiter only caps chunks per second, so "
        "a consumer that stays slow long enough pulls the whole file into "
        "memory unless the read-ahead itself is bounded"
    )


def test_the_transfer_budget_fits_a_small_host():
    budget = pyrogram.Client.MAX_READ_AHEAD_CHUNKS

    assert budget <= 128, (
        f"a {budget} MiB transfer budget is too much for a 500 MiB host; it is "
        "shared process-wide, so this is the ceiling for every client together"
    )


class SharedLink:

    def __init__(self, file_size: int, step: float = 0.01):
        self.file_size = file_size
        self.step = step
        self.served = 0
        self.timeouts = 0
        self.inflight = {}
        self.peak = {}

    def session(self, dc_id: int = 2) -> Session:
        session = Session(
            DummyClient(), dc_id, b"\x00" * 256, False,
            is_media=True, crypto_executor=None
        )
        session.is_started.set()
        session.send = self._send_for(session)
        return session

    def _send_for(self, session):
        key = id(session)

        async def send(query, wait_response=True, timeout=None, retry=0):
            live = self.inflight.get(key, 0) + 1
            self.inflight[key] = live
            self.peak[key] = max(self.peak.get(key, 0), live)
            try:
                await asyncio.sleep(self.step * sum(self.inflight.values()))
                self.served += 1
                remaining = max(0, self.file_size - query.offset)
                return raw.types.upload.File(
                    type=raw.types.storage.FilePartial(),
                    mtime=0,
                    bytes=b"\x00" * min(CHUNK, remaining),
                )
            finally:
                self.inflight[key] -= 1

        return send


def link_client(monkeypatch, link, pool):
    client = pyrogram.Client("link", api_id=1, api_hash="x", in_memory=True)
    client.me = SimpleNamespace(is_bot=False, is_premium=False)

    async def get_session(*args, **kwargs):
        return pool[0]

    async def get_pool(dc_id, n):
        return pool

    monkeypatch.setattr(client, "get_session", get_session)
    monkeypatch.setattr(client, "_get_media_session_pool", get_pool)
    return client


async def test_concurrent_downloads_cannot_pile_up_on_one_connection(monkeypatch):
    file_size = 8 * CHUNK
    link = SharedLink(file_size)
    pool = [link.session() for _ in range(3)]
    for session in pool:
        session._invoke_semaphore = asyncio.Semaphore(4)
    client = link_client(monkeypatch, link, pool)

    file_id = FileId(file_type=FileType.DOCUMENT, dc_id=2, media_id=1, access_hash=1)

    async def download():
        async for _ in client.get_file(file_id, file_size):
            pass

    await asyncio.gather(*(download() for _ in range(4)))

    worst = max(link.peak.values())

    assert worst <= 4, (
        f"{worst} requests were in flight on a single media connection with 4 "
        "parallel downloads sharing a 3-session pool"
    )


class SlowLink(SharedLink):

    def _send_for(self, session):
        async def send(query, wait_response=True, timeout=None, retry=0):
            self.inflight[id(session)] = self.inflight.get(id(session), 0) + 1
            session.last_packet_received = time.monotonic()
            try:
                needed = self.step * sum(self.inflight.values())
                await asyncio.sleep(min(needed, timeout))
                session.last_packet_received = time.monotonic()

                if needed > timeout:
                    self.timeouts += 1
                    raise TimeoutError("Request timed out")

                self.served += 1
                remaining = max(0, self.file_size - query.offset)
                return raw.types.upload.File(
                    type=raw.types.storage.FilePartial(),
                    mtime=0,
                    bytes=b"\x00" * min(CHUNK, remaining),
                )
            finally:
                self.inflight[id(session)] -= 1

        return send
DEADLINE = 0.1
STEP = 0.004
PARALLEL_WORKERS = 48


def request():
    return raw.functions.upload.GetFile(
        location=raw.types.InputDocumentFileLocation(
            id=1, access_hash=1, file_reference=b"", thumb_size=""
        ),
        offset=0,
        limit=CHUNK,
    )


async def timeouts_for(cap):
    link = SlowLink(file_size=64 * CHUNK, step=STEP)
    session = link.session()
    session._invoke_semaphore = asyncio.Semaphore(cap) if cap else None

    async def one():
        try:
            await session.invoke(request(), retries=1, timeout=DEADLINE)
        except TimeoutError:
            pass

    await asyncio.gather(*(one() for _ in range(PARALLEL_WORKERS)))
    return link.timeouts


async def test_uncapped_parallel_transfers_breach_their_deadline():
    assert await timeouts_for(cap=None) > 0


async def test_a_capped_connection_meets_its_deadline_at_the_same_load():
    assert await timeouts_for(cap=4) == 0


async def test_media_connections_ship_with_a_cap():
    session = Session(
        DummyClient(), 2, b"\x00" * 256, False, is_media=True, crypto_executor=None
    )

    assert session._invoke_semaphore is not None
    assert 1 <= Session.MAX_INFLIGHT_MEDIA <= 8, (
        f"a cap of {Session.MAX_INFLIGHT_MEDIA} parts per connection is outside "
        "the range that keeps latency under the transfer deadline"
    )


async def test_the_cap_does_not_apply_to_control_connections():
    session = Session(DummyClient(), 2, b"\x00" * 256, False, crypto_executor=None)

    assert session._invoke_semaphore is None, (
        "only media connections carry large parts; capping ordinary RPCs would "
        "throttle the client for nothing"
    )


async def test_a_capped_transfer_still_delivers_the_whole_file(monkeypatch):
    file_size = 8 * CHUNK
    link = SharedLink(file_size)
    pool = [link.session() for _ in range(3)]
    client = link_client(monkeypatch, link, pool)

    file_id = FileId(file_type=FileType.DOCUMENT, dc_id=2, media_id=1, access_hash=1)

    total = 0
    async for chunk in client.get_file(file_id, file_size):
        total += len(chunk)

    assert total == file_size, f"capping cost data: got {total} of {file_size}"


async def test_every_chunk_still_arrives_in_order(monkeypatch):
    file_size = 12 * CHUNK
    session = ChunkSession(file_size)
    client = make_download_client(monkeypatch, session)

    file_id = FileId(file_type=FileType.DOCUMENT, dc_id=2, media_id=1, access_hash=1)

    total = 0
    async for chunk in client.get_file(file_id, file_size):
        total += len(chunk)

    assert total == file_size, (
        f"bounding the read-ahead must not lose data: got {total} of {file_size}"
    )


def bare_vector(prim, values):
    from pyrogram.raw.core import Int, Vector
    return Int(Vector.ID, False) + Int(len(values)) + b"".join(prim(v) for v in values)


def test_a_bare_vector_of_ints_still_reads():
    from io import BytesIO
    from pyrogram.raw.core import Int, TLObject

    assert list(TLObject.read(BytesIO(bare_vector(Int, [1, 2, 3, 4])))) == [1, 2, 3, 4]


def test_a_bare_vector_of_longs_still_reads():
    from io import BytesIO
    from pyrogram.raw.core import Long, TLObject

    values = [1 << 40, 2 << 40, 3]
    assert list(TLObject.read(BytesIO(bare_vector(Long, values)))) == values


def test_reading_a_vector_does_not_consume_what_follows():
    from io import BytesIO
    from pyrogram.raw.core import Int, Vector

    stream = BytesIO(Int(2) + Int(7) + Int(9) + Int(0x5EEDBEEF, False))
    got = Vector.read(stream, Int)

    assert list(got) == [7, 9]
    assert Int.read(stream, False) == 0x5EEDBEEF, (
        "a typed vector must leave the stream positioned right after its elements"
    )


async def test_a_dropped_connection_does_not_restart_once_per_request(monkeypatch):
    session = make_session()
    session.is_started.set()

    restarts = []
    attempts = []
    sentinel = object()

    async def send(data, timeout=None, **kwargs):
        attempts.append(data)
        if len(attempts) == 1:
            raise ConnectionResetError("Connection lost while awaiting a response")
        return sentinel

    async def restart():
        restarts.append(1)

    monkeypatch.setattr(session, "send", send)
    monkeypatch.setattr(session, "restart", restart)

    assert await session.invoke(raw.functions.Ping(ping_id=0)) is sentinel
    assert restarts == [], (
        "the connection was already torn down; restarting again turns one drop "
        "into one restart per in-flight request, which is what wedges a busy "
        "session under load"
    )


async def test_a_real_timeout_with_a_silent_link_still_restarts(monkeypatch):
    session = make_session()
    session.is_started.set()
    session.last_packet_received = 0.0

    restarts = []
    attempts = []
    sentinel = object()

    async def send(data, timeout=None, **kwargs):
        attempts.append(data)
        if len(attempts) == 1:
            raise TimeoutError("Request timed out")
        return sentinel

    async def restart():
        restarts.append(1)

    monkeypatch.setattr(session, "send", send)
    monkeypatch.setattr(session, "restart", restart)

    assert await session.invoke(raw.functions.Ping(ping_id=0)) is sentinel
    assert restarts == [1]


async def test_the_handshake_gets_longer_after_a_failed_attempt(monkeypatch):
    session = make_session()
    seen = []

    class Flaky:
        def __init__(self, *a, **k):
            self.protocol = SimpleNamespace(crypto_executor=None)

        async def connect(self):
            pass

        async def close(self):
            pass

        async def recv(self):
            await asyncio.sleep(3600)

    monkeypatch.setattr(DummyClient, "connection_factory", Flaky)

    async def send(data, wait_response=True, timeout=None, retry=0):
        seen.append(timeout)
        raise TimeoutError("Request timed out")

    monkeypatch.setattr(session, "send", send)

    with pytest.raises(TimeoutError):
        await session.start(max_attempts=3)

    assert seen == sorted(seen) and seen[0] < seen[-1], (
        f"handshake timeouts {seen} never grew; a congested link that misses "
        "the first one will miss every retry the same way"
    )


async def test_a_cancelled_send_does_not_leave_its_slot_behind(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    async def slow_pack(*args, **kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr(session.loop, "run_in_executor", slow_pack)

    task = asyncio.ensure_future(session.send(raw.functions.Ping(ping_id=0)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert session.results == {}, (
        "a cancelled send left a result slot behind; handle_packet fills those "
        "with the whole response body and nothing ever pops them"
    )


async def test_a_send_cancelled_on_the_wire_does_not_leave_its_slot_behind(monkeypatch):
    session = make_session()

    class Stalling(RecordingConnection):
        async def send(self, payload):
            await asyncio.sleep(3600)

    session.connection = Stalling()
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)

    task = asyncio.ensure_future(session.send(raw.functions.Ping(ping_id=0)))
    for _ in range(6):
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert session.results == {}


async def test_an_orphaned_slot_would_hold_the_whole_response(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    msg_id = MsgId() | 1
    payload = b"\x00" * 4096
    body = raw.types.Pong(msg_id=msg_id, ping_id=0).write()
    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpacked_as(msg_id, body))

    session.results[msg_id] = Result()
    await session.handle_packet(b"ignored")

    assert session.results[msg_id].value is not None, (
        "this documents why a leaked slot matters: an arriving reply is stored "
        "in it, so each orphan retains a whole response payload"
    )
    assert len(payload) > 0


class CountingPing(raw.functions.Ping):
    writes = 0

    def write(self, *args, **kwargs):
        type(self).writes += 1
        return super().write(*args, **kwargs)


async def test_an_outgoing_message_is_serialised_once(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()
    monkeypatch.setattr(session.loop, "run_in_executor", _packed)

    CountingPing.writes = 0

    with pytest.raises(TimeoutError):
        await session.send(CountingPing(ping_id=0), timeout=0.05)

    assert CountingPing.writes == 1, (
        f"the message body was serialised {CountingPing.writes} times; "
        "len(TLObject) serialises it too, so measuring and packing must share "
        "one pass"
    )


def test_measuring_a_message_costs_a_serialisation():
    query = raw.functions.upload.SaveBigFilePart(
        file_id=1, file_part=0, file_total_parts=8, bytes=b"\x00" * 4096
    )
    assert len(query) == len(query.write()), (
        "len() on a TLObject is not free: it serialises. This test exists so "
        "the cost is visible if someone adds a len() to the send path."
    )


async def test_the_transfer_budget_is_shared_between_clients():
    a = pyrogram.Client("budget_a", api_id=1, api_hash="x", in_memory=True)
    b = pyrogram.Client("budget_b", api_id=1, api_hash="x", in_memory=True)

    assert a.read_ahead_slots is b.read_ahead_slots, (
        "each client holding its own budget means fifteen clients reserve "
        "fifteen times the memory, which is how a small host runs out"
    )


async def test_a_disk_download_also_draws_on_the_budget(tmp_path):
    from .e2e import CHUNK, FakeDC, document, make_client

    file_size = 40 * CHUNK
    dc = FakeDC(file_size, step=0.0005)
    client = make_client(dc, "diskbudget")
    budget = client.read_ahead_slots
    before = budget._value
    low = [before]

    async def watch():
        while True:
            low[0] = min(low[0], budget._value)
            await asyncio.sleep(0)

    watcher = asyncio.ensure_future(watch())
    path = tmp_path / "d.bin"
    with open(path, "w+b") as handle:
        handle.truncate(file_size)
        async for _ in client.get_file(document(), file_size, _write_file=handle):
            pass
    watcher.cancel()
    await asyncio.gather(watcher, return_exceptions=True)

    assert low[0] < before, (
        "writing straight to disk never touched the shared budget, so fifteen "
        "clients downloading to disk are bounded only per session"
    )
    assert budget._value == before


async def test_clients_share_one_handler_thread_pool():
    a = pyrogram.Client("pool_a", api_id=1, api_hash="x", in_memory=True)
    b = pyrogram.Client("pool_b", api_id=1, api_hash="x", in_memory=True)

    assert a.executor is b.executor, (
        "a thread pool per client means fifteen pools of blocking workers on a "
        "host that has a couple of cores"
    )
    assert a.executor._max_workers <= 32


async def test_terminating_one_client_leaves_the_shared_pool_alive():
    from pyrogram.methods.auth.terminate import Terminate

    source = Terminate.terminate.__code__.co_consts
    assert not any(
        isinstance(c, str) and "shutdown" in c for c in source if isinstance(c, str)
    )

    a = pyrogram.Client("pool_c", api_id=1, api_hash="x", in_memory=True)
    assert not a.executor._shutdown


async def test_uploads_draw_on_the_shared_budget(tmp_path):
    from types import SimpleNamespace as NS
    from .e2e import CHUNK, FakeDC, make_client

    size = 8 * CHUNK
    path = tmp_path / "u.bin"
    with open(path, "wb") as handle:
        handle.truncate(size)

    dc = FakeDC(size, step=0.00002)
    client = make_client(dc, "upbudget", pool=dc.pool(4))
    client.me = NS(is_bot=False, is_premium=False)
    await client.storage.open()

    budget = client.read_ahead_slots
    before = budget._value
    low = [before]

    async def watch():
        while True:
            low[0] = min(low[0], budget._value)
            await asyncio.sleep(0)

    watcher = asyncio.ensure_future(watch())
    await client.save_file(str(path))
    watcher.cancel()
    await asyncio.gather(watcher, return_exceptions=True)

    assert low[0] < before, (
        "uploads never touched the shared budget, so fifteen clients uploading "
        "at once are bounded only per client"
    )
    assert budget._value == before, "the upload gave back fewer slots than it took"


def entity_cases():
    return [
        (raw.types.MessageEntityBold(offset=1, length=2), "BOLD", {}),
        (raw.types.MessageEntityItalic(offset=0, length=5), "ITALIC", {}),
        (
            raw.types.MessageEntityTextUrl(offset=2, length=3, url="https://x.dev"),
            "TEXT_LINK",
            {"url": "https://x.dev"},
        ),
        (
            raw.types.MessageEntityPre(offset=0, length=9, language="python"),
            "PRE",
            {"language": "python"},
        ),
        (
            raw.types.MessageEntityCustomEmoji(offset=0, length=1, document_id=99),
            "CUSTOM_EMOJI",
            {"custom_emoji_id": "99"},
        ),
        (
            raw.types.MessageEntityBlockquote(offset=0, length=4, collapsed=True),
            "BLOCKQUOTE",
            {"expandable": True},
        ),
    ]


def test_every_entity_kind_parses_to_the_same_fields():
    from pyrogram import enums, types

    for entity, expected_type, expected in entity_cases():
        parsed = types.MessageEntity._parse(None, entity, {})

        assert parsed.type is getattr(enums.MessageEntityType, expected_type), entity
        assert parsed.offset == entity.offset
        assert parsed.length == entity.length

        for field in ("url", "language", "custom_emoji_id", "expandable"):
            assert getattr(parsed, field) == expected.get(field), (entity, field)


def test_a_mention_entity_still_resolves_its_user():
    from pyrogram import enums, types

    user = raw.types.User(
        id=7, is_self=False, contact=False, mutual_contact=False, deleted=False,
        bot=False, bot_chat_history=False, bot_nochats=False, verified=False,
        restricted=False, min=False, bot_inline_geo=False, support=False,
        scam=False, apply_min_photo=False, fake=False, bot_attach_menu=False,
        premium=False, attach_menu_enabled=False, first_name="m", access_hash=1,
        usernames=[], restriction_reason=[],
    )
    entity = raw.types.MessageEntityMentionName(offset=0, length=2, user_id=7)
    parsed = types.MessageEntity._parse(None, entity, {7: user})

    assert parsed.type is enums.MessageEntityType.TEXT_MENTION
    assert parsed.user is not None and parsed.user.id == 7


def test_an_input_mention_entity_still_resolves_its_user():
    from pyrogram import enums, types

    entity = raw.types.InputMessageEntityMentionName(
        offset=0, length=2, user_id=raw.types.InputUser(user_id=7, access_hash=1)
    )
    parsed = types.MessageEntity._parse(None, entity, {})

    assert parsed.type is enums.MessageEntityType.TEXT_MENTION
    assert parsed.user is None


def test_a_formatted_date_entity_keeps_its_format_string():
    from pyrogram import enums, types

    entity = raw.types.MessageEntityFormattedDate(
        offset=0, length=1, date=1700000000, relative=False, day_of_week=True,
        short_date=True, long_date=False, short_time=True, long_time=False,
    )
    parsed = types.MessageEntity._parse(None, entity, {})

    assert parsed.type is enums.MessageEntityType.DATE_TIME
    assert parsed.unix_time == 1700000000
    assert parsed.date_time_format == "wdt"


def test_a_relative_formatted_date_entity_is_marked_relative():
    from pyrogram import types

    entity = raw.types.MessageEntityFormattedDate(
        offset=0, length=1, date=1, relative=True, day_of_week=False,
        short_date=False, long_date=False, short_time=False, long_time=False,
    )
    assert types.MessageEntity._parse(None, entity, {}).date_time_format == "r"


def test_a_raw_object_is_truthy_without_serialising_itself():
    from pyrogram.raw.core import TLObject

    calls = []

    class Counting(raw.types.MessageEntityBold):
        def write(self, *args, **kwargs):
            calls.append(1)
            return super().write(*args, **kwargs)

    entity = Counting(offset=0, length=1)

    assert bool(entity) is True
    assert calls == [], (
        "truthiness fell back to __len__, which serialises the whole object; "
        "that runs on every `if message.media:` style check in the codebase"
    )
    assert isinstance(TLObject.__bool__(entity), bool)


def test_an_empty_raw_list_is_still_falsy():
    from pyrogram.raw.core import List

    assert not List()
    assert bool(List([1]))


def test_len_of_a_raw_object_still_measures_its_wire_size():
    entity = raw.types.MessageEntityBold(offset=0, length=1)

    assert len(entity) == len(entity.write())


def test_int_primitives_read_the_same_values_as_before():
    from io import BytesIO
    from pyrogram.raw.core import Int, Int128, Int256, Long

    cases = [
        (Int, 4, [0, 1, -1, 2 ** 31 - 1, -(2 ** 31)]),
        (Long, 8, [0, 1, -1, 2 ** 63 - 1, -(2 ** 63)]),
        (Int128, 16, [0, 1, 2 ** 127 - 1, -(2 ** 127)]),
        (Int256, 32, [0, 1, 2 ** 255 - 1, -(2 ** 255)]),
    ]

    for cls, size, values in cases:
        for value in values:
            raw_bytes = value.to_bytes(size, "little", signed=True)
            assert cls.read(BytesIO(raw_bytes)) == value, (cls, value)
            assert bytes(cls(value)) == raw_bytes, (cls, value)


def test_unsigned_int_primitives_still_work():
    from io import BytesIO
    from pyrogram.raw.core import Int, Long

    for cls, size, value in ((Int, 4, 2 ** 32 - 1), (Long, 8, 2 ** 64 - 1)):
        raw_bytes = value.to_bytes(size, "little")
        assert cls.read(BytesIO(raw_bytes), False) == value
        assert cls.read(BytesIO(raw_bytes)) == -1


def test_bytes_and_string_primitives_round_trip():
    from io import BytesIO
    from pyrogram.raw.core import Bytes, String

    for payload in (b"", b"a", b"x" * 253, b"y" * 254, b"z" * 1000):
        assert Bytes.read(BytesIO(bytes(Bytes(payload)))) == payload

    for text in ("", "hello", "é中文", "x" * 300):
        assert String.read(BytesIO(bytes(String(text)))) == text


def test_a_string_with_invalid_utf8_is_still_replaced():
    from io import BytesIO
    from pyrogram.raw.core import Bytes, String

    assert String.read(BytesIO(bytes(Bytes(b"\xff\xfe")))) == "��"


def test_bool_primitive_reads_both_values():
    from io import BytesIO
    from pyrogram.raw.core import Bool

    assert Bool.read(BytesIO(bytes(Bool(True)))) is True
    assert Bool.read(BytesIO(bytes(Bool(False)))) is False
    assert Bool.read(BytesIO(b"\x00\x00\x00\x00")) is False


def test_double_primitive_round_trips():
    import struct
    from io import BytesIO
    from pyrogram.raw.core import Double

    for value in (0.0, 1.5, -3.25, 1e300, -1e-300):
        assert bytes(Double(value)) == struct.pack("d", value), value
        assert Double.read(BytesIO(bytes(Double(value)))) == value, value


def test_a_typed_vector_reads_every_element():
    from io import BytesIO
    from pyrogram.raw.core import Int, Vector

    values = [1, -2, 3, -4]
    buf = bytes(Int(Vector.ID, False)) + bytes(Int(len(values)))
    buf += b"".join(bytes(Int(v)) for v in values)

    stream = BytesIO(buf)
    stream.read(4)
    assert list(Vector.read(stream, Int)) == values


def test_a_bare_vector_of_objects_reads_every_element():
    from io import BytesIO
    from pyrogram.raw.core import Int, TLObject, Vector

    items = [raw.types.MessageEntityBold(offset=i, length=1) for i in range(3)]
    buf = bytes(Int(Vector.ID, False)) + bytes(Int(len(items)))
    buf += b"".join(i.write() for i in items)

    got = TLObject.read(BytesIO(buf))
    assert [e.offset for e in got] == [0, 1, 2]


def test_tlobject_read_still_forwards_extra_arguments():
    from io import BytesIO
    from pyrogram.raw.core import TLObject

    seen = []

    class Probe:
        @staticmethod
        def read(b, *args):
            seen.append(args)
            return "ok"

    from pyrogram.raw.all import objects

    marker = 0x7E571234
    objects[marker] = Probe
    try:
        buf = marker.to_bytes(4, "little")
        assert TLObject.read(BytesIO(buf)) == "ok"
        assert TLObject.read(BytesIO(buf), 1, 2) == "ok"
        assert seen == [(), (1, 2)]
    finally:
        objects.pop(marker, None)


def test_an_unknown_constructor_still_raises_key_error():
    from io import BytesIO
    from pyrogram.raw.core import TLObject

    with pytest.raises(KeyError):
        TLObject.read(BytesIO((0x0BADF00D).to_bytes(4, "little")))


class _WatchdogClient:
    UPDATES_WATCHDOG_INTERVAL = 0.05
    updates_watchdog = pyrogram.Client.updates_watchdog

    def __init__(self):
        self.updates_watchdog_event = asyncio.Event()
        self.calls = 0

        # an update arrived an hour of monotonic time ago, and the host clock
        # then stepped back an hour, so the wall-clock stamp is in the future
        self.last_update_time = datetime.now() + timedelta(hours=1)
        self._last_update_monotonic = time.monotonic() - 3600

    async def invoke(self, query, **kwargs):
        self.calls += 1

    async def recover_gaps(self):
        return (0, 0)


async def test_the_updates_watchdog_measures_idle_time_on_the_monotonic_clock():
    client = _WatchdogClient()

    task = asyncio.ensure_future(client.updates_watchdog())
    await asyncio.sleep(0.3)

    try:
        assert client.calls > 0, (
            "idle time is a duration, so a host clock that steps backwards must "
            "not stall the watchdog for the length of the step"
        )
    finally:
        client.updates_watchdog_event.set()
        await asyncio.wait_for(task, timeout=5)


async def test_a_small_write_batch_is_committed_without_waiting_for_more(monkeypatch, tmp_path):
    monkeypatch.setattr(SQLiteStorage, "_AUTO_COMMIT_SECONDS", 0.1)

    storage = SQLiteStorage("bounded", tmp_path, in_memory=True)
    await storage.open()

    try:
        await storage.update_peers([(1, 2, "user", None)])

        assert storage._dirty, "one write is below the batch size, so it is still pending"

        await asyncio.sleep(0.4)

        assert not storage._dirty, (
            "a batch that never reaches its size sits in an open write transaction "
            "for as long as the process runs; a kill loses it and the transaction "
            "keeps the WAL from being checkpointed"
        )
    finally:
        await storage.close()


async def test_a_stopped_dispatcher_leaves_nothing_in_its_queue():
    dispatcher = make_audit_dispatcher()

    await dispatcher.start()

    # a worker cancelled during a previous stop never took its sentinel
    dispatcher.updates_queue.put_nowait(None)

    await dispatcher.stop()

    assert dispatcher.updates_queue.empty(), (
        "a sentinel left in the queue retires a worker of the next generation the "
        "instant it starts, and parsed updates left there hold their peer graphs"
    )

    await dispatcher.start()
    await asyncio.sleep(0.05)
    dispatcher.prune_workers()

    assert len(dispatcher.handler_worker_tasks) == dispatcher.client.workers, (
        "every worker of a freshly started dispatcher must still be running"
    )

    await dispatcher.stop()


def _unknown():
    RPCError.raise_it(
        raw.types.RpcError(error_code=999, error_message="NOT_A_REAL_ERROR"),
        raw.functions.Ping,
    )


async def test_an_unknown_error_does_not_write_to_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(UnknownError):
        _unknown()

    assert not (tmp_path / "unknown_errors.txt").exists(), (
        "a library must not append to a file in the caller's working directory, "
        "unbounded, from inside an exception constructor"
    )


async def test_an_unwritable_working_directory_does_not_replace_the_error(monkeypatch):
    import builtins

    real_open = builtins.open

    def refusing_open(*args, **kwargs):
        if args and str(args[0]).endswith("unknown_errors.txt"):
            raise OSError(30, "Read-only file system")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", refusing_open)

    with pytest.raises(UnknownError):
        _unknown()


class _AckRecordingConnection:
    def __init__(self):
        self.protocol = None

    async def close(self):
        pass


async def test_pending_acks_are_flushed_even_when_the_link_goes_quiet(monkeypatch):
    from tests.test_stability import make_session

    monkeypatch.setattr(pyrogram.session.Session, "PING_INTERVAL", 0.05)

    session = make_session()
    session.connection = _AckRecordingConnection()
    session.pending_acks = {12345}

    sent = []

    async def record(data, wait_response=True, **kwargs):
        sent.append(data)

    monkeypatch.setattr(session, "send", record)

    task = asyncio.ensure_future(session.ping_worker())
    await asyncio.sleep(0.3)
    session.ping_task_event.set()
    await asyncio.wait_for(task, timeout=5)

    assert any(isinstance(d, raw.types.MsgsAck) for d in sent), (
        "acks are only flushed once ACKS_THRESHOLD of them pile up inside "
        "handle_packet, so a link that goes quiet below that leaves them owed "
        "and the server re-delivers those updates for as long as the client runs"
    )
    assert not session.pending_acks


async def test_idle_puts_back_the_signal_handlers_it_took():
    import signal

    from pyrogram.methods.utilities.idle import idle

    watched = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)
    before = {s: signal.getsignal(s) for s in watched}

    task = asyncio.ensure_future(idle())
    await asyncio.sleep(0.05)

    assert signal.getsignal(signal.SIGINT) is not before[signal.SIGINT], (
        "idle should have installed its own handler by now"
    )

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert {s: signal.getsignal(s) for s in watched} == before, (
        "idle leaves its handler installed, so the next Ctrl-C cancels a task "
        "that is already done and the process can no longer be interrupted - "
        "including during the client.stop() that Client.run does next"
    )


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage("hotpath", tmp_path)


async def test_a_peer_is_read_from_the_database_once(storage):
    await storage.open()

    try:
        await storage.update_peers([(7, 99, "user", None)])

        queries = []
        original = storage.conn.execute

        async def counting(sql, *args, **kwargs):
            queries.append(sql)
            return await original(sql, *args, **kwargs)

        storage.conn.execute = counting

        first = await storage.get_peer_by_id(7)
        second = await storage.get_peer_by_id(7)

        assert first == second
        assert not [q for q in queries if "FROM peers" in q], (
            "a peer lookup costs a thread hand-off into aiosqlite; resolve_peer "
            "runs on every send, so the same peer must not be fetched twice"
        )
    finally:
        await storage.close()


async def test_a_changed_access_hash_is_still_written(storage):
    await storage.open()

    try:
        await storage.update_peers([(7, 99, "user", None)])
        assert (await storage.get_peer_by_id(7)).access_hash == 99

        await storage.update_peers([(7, 1234, "user", None)])

        assert (await storage.get_peer_by_id(7)).access_hash == 1234, (
            "skipping a write the cache already knows must not skip a peer whose "
            "access hash actually changed"
        )
    finally:
        await storage.close()


async def test_a_cached_peer_survives_a_reopen(storage):
    await storage.open()
    await storage.update_peers([(7, 99, "user", None)])
    await storage.close()

    await storage.open()

    try:
        assert (await storage.get_peer_by_id(7)).access_hash == 99, (
            "the cache must not be what a peer is stored in"
        )
    finally:
        await storage.close()


async def test_an_unchanged_peer_is_not_rewritten(storage):
    await storage.open()

    try:
        await storage.update_peers([(7, 99, "user", None)])

        writes = []
        original = storage.conn.executemany

        async def counting(sql, *args, **kwargs):
            writes.append(sql)
            return await original(sql, *args, **kwargs)

        storage.conn.executemany = counting

        await storage.update_peers([(7, 99, "user", None)])

        assert not writes, (
            "every invoke feeds r.users and r.chats back through fetch_peers, so "
            "the same unchanged peers are written over and over"
        )
    finally:
        await storage.close()


class _StateClient:
    handle_updates = pyrogram.Client.handle_updates
    _save_update_state = pyrogram.Client._save_update_state

    def __init__(self):
        self.states = []
        self._state_marks = {}
        self.enqueued = []

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                outer.states.append(value)

        class _Dispatcher:
            async def enqueue_update(self, update, users, chats):
                outer.enqueued.append(update)
                return True

        self.storage = _Storage()
        self.dispatcher = _Dispatcher()

    async def fetch_peers(self, peers):
        return False


async def test_one_state_write_per_peer_per_batch():
    client = _StateClient()

    updates = raw.types.Updates(
        updates=[
            raw.types.UpdateNewMessage(
                message=raw.types.MessageEmpty(id=i), pts=i + 1, pts_count=1
            )
            for i in range(30)
        ],
        users=[],
        chats=[],
        date=1700000000,
        seq=1,
    )

    await client.handle_updates(updates)

    assert len(client.enqueued) == 30

    assert len(client.states) == 1, (
        "each state write costs a thread hand-off into aiosqlite; only the "
        f"highest pts of a batch matters, but {len(client.states)} were written"
    )
    assert client.states[0][1] == 30, (
        f"the state kept must be the highest pts of the batch, got {client.states[0][1]}"
    )


async def test_a_small_packet_is_decrypted_without_a_thread(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    body = raw.types.Pong(msg_id=1, ping_id=0).write()
    hops = []

    def unpack(*args, **kwargs):
        return 3, 1, len(body), body, 32 + len(body)

    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpack)

    original = session.loop.run_in_executor

    def counting(*args, **kwargs):
        hops.append(args[1] if len(args) > 1 else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(session.loop, "run_in_executor", counting)

    await session.handle_packet(b"\x00" * 512)

    assert not hops, (
        "a hand-off to the crypto pool costs a flat ~110us and a 512 byte packet "
        "costs about one to decrypt, so small packets must not pay for a thread"
    )


async def test_a_transfer_sized_packet_still_uses_the_pool(monkeypatch):
    session = make_session()
    session.connection = RecordingConnection()

    body = raw.types.Pong(msg_id=1, ping_id=0).write()
    hops = []

    def unpack(*args, **kwargs):
        return 3, 1, len(body), body, 32 + len(body)

    monkeypatch.setattr(session_mod.warpcrypto, "unpack_message", unpack)

    async def counting(executor, fn, *args):
        hops.append(fn)
        return fn(*args)

    monkeypatch.setattr(session.loop, "run_in_executor", counting)

    await session.handle_packet(b"\x00" * (Session.INLINE_CRYPTO_MAX + 1))

    assert hops, (
        "a megabyte part would stall the event loop for milliseconds; above the "
        "threshold the crypto pool is what keeps it off the loop"
    )


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


class _BackgroundTasksWatchdogClient:
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
    client = _BackgroundTasksWatchdogClient(TimeoutError("Request timed out"))

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


class _UnresolvableGapClient(RecoverGaps):
    """One stored channel can no longer be resolved; the others still can."""

    _save_update_state = pyrogram.Client._save_update_state

    def __init__(self):
        self._state_marks = {}
        self.skip_updates = False
        self.recovered = []
        self.dropped = []

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                if value is object:
                    return [(-1001111111111, 5, 0, 7, 1), (-1002222222222, 5, 0, 7, 1)]
                if isinstance(value, int):
                    outer.dropped.append(value)

        self.storage = _Storage()

        class _Dispatcher:
            async def enqueue_update(self, *args):
                return True

        self.dispatcher = _Dispatcher()

    async def resolve_peer(self, peer_id):
        if peer_id == -1001111111111:
            raise PeerIdInvalid

        return raw.types.InputChannel(channel_id=1, access_hash=0)

    async def invoke(self, query, **kwargs):
        self.recovered.append(query)
        await asyncio.sleep(0)

        return raw.types.updates.ChannelDifferenceEmpty(final=True, pts=9)


async def test_one_unresolvable_peer_does_not_abort_gap_recovery():
    client = _UnresolvableGapClient()

    await asyncio.wait_for(client.recover_gaps(), timeout=10)

    assert client.recovered, (
        "a peer that can no longer be resolved must not stop the peers after it "
        "from recovering - recover_gaps runs inside dispatcher.start(), so this "
        "aborts start() and the client can never come up again"
    )
    assert -1001111111111 in client.dropped, (
        "the state of a peer that cannot be resolved is unusable and must be "
        "dropped, or every start repeats the same failure"
    )


class _Listeners:
    def reopen(self):
        pass


class _FakeDispatcher:
    def __init__(self, fail: bool):
        self.fail = fail
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

        if self.fail:
            raise RuntimeError("recover_gaps blew up")

    async def stop(self, clear_handlers: bool = True):
        self.stopped = True


class _InitClient:
    initialize = pyrogram.Client.initialize
    updates_watchdog = pyrogram.Client.updates_watchdog
    media_pool_reaper = pyrogram.Client.media_pool_reaper

    UPDATES_WATCHDOG_INTERVAL = 60
    MEDIA_SESSION_REAP_INTERVAL = 60

    def __init__(self, fail: bool):
        self.is_connected = True
        self.is_initialized = False
        self.listeners = _Listeners()
        self.rate_limiter = None
        self.dispatcher = _FakeDispatcher(fail)
        self.updates_watchdog_task = None
        self.updates_watchdog_event = asyncio.Event()
        self.media_pool_reaper_task = None
        self.media_pool_reaper_event = asyncio.Event()
        self.plugins_loaded = False

    def load_plugins(self):
        self.plugins_loaded = True


async def test_a_failed_initialize_takes_its_workers_with_it():
    client = _InitClient(fail=True)

    with pytest.raises(RuntimeError):
        await client.initialize()

    assert not client.is_initialized

    assert client.dispatcher.stopped, (
        "initialize left the dispatcher running with is_initialized still False, "
        "so terminate() refuses to run and the handler workers block on the "
        "update queue for the life of the process"
    )

    for task in (client.updates_watchdog_task, client.media_pool_reaper_task):
        assert task is None or task.done(), (
            "a background task started before the failure must not outlive it"
        )


class _StartClient:
    start = pyrogram.Client.start

    def __init__(self):
        self.takeout = False
        self.takeout_id = None
        self.disconnected = False
        self.me = None

        class _Storage:
            async def is_bot(self):
                return True

        self.storage = _Storage()

    async def connect(self):
        return True

    async def invoke(self, query, **kwargs):
        return None

    async def get_me(self):
        raise RuntimeError("the server hung up right after GetState")

    async def initialize(self):
        raise AssertionError("initialize should not be reached")

    async def disconnect(self):
        self.disconnected = True


async def test_a_start_that_fails_late_still_disconnects():
    client = _StartClient()

    with pytest.raises(RuntimeError):
        await client.start()

    assert client.disconnected, (
        "get_me and initialize sit outside the try that disconnects, so a failure "
        "in either leaves a connected client the caller cannot clean up"
    )


class _NeverConnects:
    attempts = 0

    def __init__(self, *args, **kwargs):
        _NeverConnects.attempts += 1

    async def connect(self):
        raise OSError("no route to host")

    async def close(self):
        pass


async def test_an_unbounded_start_says_something_before_the_second_minute(monkeypatch, caplog):
    _NeverConnects.attempts = 0
    monkeypatch.setattr(SessionDummyClient, "connection_factory", _NeverConnects)

    session = Session(
        SessionDummyClient(), 1, b"\x00" * 256, False, is_media=False, crypto_executor=None
    )

    real_sleep = asyncio.sleep
    monkeypatch.setattr(session_mod.asyncio, "sleep", lambda *_: real_sleep(0))

    task = asyncio.ensure_future(session.start())

    with caplog.at_level(logging.WARNING, logger="pyrogram.session.session"):
        await real_sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert any("retry" in r.message.lower() or "attempt" in r.message.lower()
               for r in caplog.records), (
        "an unbounded connect retries forever and logs only at debug, so a client "
        f"that cannot reach Telegram looks hung with no output at all "
        f"({_NeverConnects.attempts} attempts made silently)"
    )
