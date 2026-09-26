import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import pyrogram
import pyrogram.session.session as session_mod
from pyrogram import raw
from pyrogram.session.session import Session
from pyrogram.storage import SQLiteStorage

from tests.test_stability import DummyClient, RecordingConnection, make_session


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
