import asyncio
import logging

import pytest

import pyrogram
import pyrogram.session.session as session_mod
from pyrogram import raw
from pyrogram.errors import PeerIdInvalid
from pyrogram.methods.advanced.recover_gaps import RecoverGaps
from pyrogram.session.session import Session

from tests.test_session import DummyClient


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
    monkeypatch.setattr(DummyClient, "connection_factory", _NeverConnects)

    session = Session(
        DummyClient(), 1, b"\x00" * 256, False, is_media=False, crypto_executor=None
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
