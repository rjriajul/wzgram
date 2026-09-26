"""One behavioural suite, run against every storage engine.

Three engines implement the same contract and they drift apart quietly: a peer
lookup that raises the wrong error, a username TTL enforced in one place and not
another, an update state that comes back in a different shape. Parametrizing the
suite is what keeps them honest, and it is why a new engine only has to be added
to ``ENGINES`` to be held to the same rules.
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from pyrogram import raw
from pyrogram.storage import HybridStorage, RemoteStorage, SQLiteStorage


class FakeRemote(RemoteStorage):
    """A RemoteStorage backed by dicts, standing in for Mongo or Redis."""

    def __init__(self, name: str = "fake", session_string: Optional[str] = None):
        super().__init__(name, session_string=session_string)

        self.session: Optional[Dict[str, Any]] = None
        self.peers: Dict[int, Tuple[int, int, str, Optional[str], int]] = {}
        self.usernames: Dict[str, int] = {}
        self.states: Dict[int, Tuple[int, int, int, int, int]] = {}
        self.stored_version: Optional[int] = None

        self.connected = False
        self.reads = 0
        self.writes = 0
        self.fail_reads = False
        self.fail_writes = False

    async def _connect(self):
        self.connected = True

    async def _disconnect(self):
        self.connected = False

    async def _load_session(self):
        self.reads += 1

        if self.fail_reads:
            raise ConnectionError("backend is down")

        return dict(self.session) if self.session is not None else None

    async def _save_session(self, fields):
        self.writes += 1

        if self.fail_writes:
            raise ConnectionError("backend is down")

        if self.session is None:
            self.session = {}

        self.session.update(fields)

    async def _load_version(self):
        return self.stored_version

    async def _save_version(self, version):
        self.stored_version = version

    async def _upsert_peers(self, rows):
        self.writes += 1

        if self.fail_writes:
            raise ConnectionError("backend is down")

        now = int(time.time())

        for peer_id, access_hash, peer_type, phone_number in rows:
            self.peers[peer_id] = (peer_id, access_hash, peer_type, phone_number, now)

    async def _fetch_peer(self, peer_id):
        self.reads += 1

        if self.fail_reads:
            raise ConnectionError("backend is down")

        stored = self.peers.get(peer_id)

        return None if stored is None else (stored[0], stored[1], stored[2], stored[4])

    async def _fetch_peer_by_username(self, username):
        peer_id = self.usernames.get(username)

        return None if peer_id is None else await self._fetch_peer(peer_id)

    async def _fetch_peer_by_phone(self, phone_number):
        for stored in self.peers.values():
            if stored[3] == phone_number:
                return (stored[0], stored[1], stored[2], stored[4])

        return None

    async def _iter_peers(self, limit=None):
        rows = [(p[0], p[1], p[2], p[3]) for p in self.peers.values()]

        return rows if limit is None else rows[:limit]

    async def _replace_usernames(self, usernames):
        self.writes += 1

        for peer_id, _ in usernames:
            for name in [n for n, pid in self.usernames.items() if pid == peer_id]:
                del self.usernames[name]

        for peer_id, names in usernames:
            for name in names:
                self.usernames[name] = peer_id

    async def _load_states(self):
        return sorted(self.states.values(), key=lambda state: state[3])

    async def _save_state(self, state):
        self.writes += 1
        stored = self.states.get(state[0], (state[0], None, None, None, None))
        self.states[state[0]] = tuple(
            new if new is not None else old for new, old in zip(state, stored)
        )

    async def _delete_state(self, state_id):
        self.writes += 1
        self.states.pop(state_id, None)

    async def _purge(self, remove_peers):
        self.session = None
        self.states.clear()

        if remove_peers:
            self.peers.clear()
            self.usernames.clear()

    def touch_peer(self, peer_id: int, last_update_on: int) -> None:
        stored = self.peers[peer_id]
        self.peers[peer_id] = (*stored[:4], last_update_on)


def make_sqlite(tmp_path: Path):
    return SQLiteStorage("contract", workdir=tmp_path, in_memory=True)


def make_remote(tmp_path: Path):
    return FakeRemote("contract")


def make_hybrid(tmp_path: Path):
    return HybridStorage("contract", backend=FakeRemote("contract"), workdir=tmp_path)


ENGINES = {
    "sqlite": make_sqlite,
    "remote": make_remote,
    "hybrid": make_hybrid,
}


@pytest.fixture(params=list(ENGINES), ids=list(ENGINES))
async def storage(request, tmp_path):
    engine = ENGINES[request.param](tmp_path)

    await engine.open()

    try:
        yield engine
    finally:
        await engine.close()


class TestSessionAttributes:
    async def test_round_trip(self, storage):
        await storage.dc_id(4)
        await storage.api_id(12345)
        await storage.server_address("149.154.167.91")
        await storage.port(443)
        await storage.test_mode(False)
        await storage.auth_key(b"k" * 256)
        await storage.user_id(777000)
        await storage.is_bot(False)

        assert await storage.dc_id() == 4
        assert await storage.api_id() == 12345
        assert await storage.server_address() == "149.154.167.91"
        assert await storage.port() == 443
        assert await storage.test_mode() is False or await storage.test_mode() == 0
        assert await storage.auth_key() == b"k" * 256
        assert await storage.user_id() == 777000

    async def test_unset_attribute_is_none(self, storage):
        assert await storage.user_id() is None

    async def test_save_stamps_date(self, storage):
        await storage.date(0)
        await storage.save()

        assert await storage.date() > 0


class TestPeers:
    async def test_round_trip_user(self, storage):
        await storage.update_peers([(123, 456, "user", None)])

        peer = await storage.get_peer_by_id(123)

        assert isinstance(peer, raw.types.InputPeerUser)
        assert peer.user_id == 123
        assert peer.access_hash == 456

    async def test_group_and_channel(self, storage):
        await storage.update_peers(
            [(-100, 0, "group", None), (-1001234567890, 99, "channel", None)]
        )

        group = await storage.get_peer_by_id(-100)
        channel = await storage.get_peer_by_id(-1001234567890)

        assert isinstance(group, raw.types.InputPeerChat)
        assert isinstance(channel, raw.types.InputPeerChannel)

    async def test_unknown_peer_raises_key_error(self, storage):
        with pytest.raises(KeyError):
            await storage.get_peer_by_id(999)

    async def test_by_phone_number(self, storage):
        await storage.update_peers([(123, 456, "user", "15551234567")])

        peer = await storage.get_peer_by_phone_number("15551234567")

        assert peer.user_id == 123

        with pytest.raises(KeyError):
            await storage.get_peer_by_phone_number("15550000000")

    async def test_by_username(self, storage):
        await storage.update_peers([(123, 456, "user", None)])
        await storage.update_usernames([(123, ["alice"])])

        peer = await storage.get_peer_by_username("alice")

        assert peer.user_id == 123

        with pytest.raises(KeyError):
            await storage.get_peer_by_username("nobody")

    async def test_username_reassignment(self, storage):
        await storage.update_peers([(1, 11, "user", None), (2, 22, "user", None)])
        await storage.update_usernames([(1, ["shared"])])
        await storage.update_usernames([(1, []), (2, ["shared"])])

        peer = await storage.get_peer_by_username("shared")

        assert peer.user_id == 2

    async def test_changed_access_hash_is_written(self, storage):
        await storage.update_peers([(123, 456, "user", None)])
        await storage.update_peers([(123, 789, "user", None)])

        peer = await storage.get_peer_by_id(123)

        assert peer.access_hash == 789

    async def test_empty_batch_is_a_no_op(self, storage):
        await storage.update_peers([])
        await storage.update_usernames([])


class TestUpdateState:
    async def test_upsert_and_read(self, storage):
        await storage.update_state((1, 100, 0, 1600000000, 5))

        states = await storage.update_state()

        assert [tuple(s) for s in states] == [(1, 100, 0, 1600000000, 5)]

    async def test_overwrite_same_id(self, storage):
        await storage.update_state((1, 100, 0, 1600000000, 5))
        await storage.update_state((1, 200, 0, 1600000001, 6))

        states = await storage.update_state()

        assert len(states) == 1
        assert tuple(states[0])[1] == 200

    async def test_a_field_left_out_is_kept(self, storage):
        await storage.update_state((0, 100, 50, 1600000000, 5))
        await storage.update_state((0, 120, None, 1600000001, None))
        await storage.update_state((0, None, 60, None, None))

        assert [tuple(s) for s in await storage.update_state()] == [(0, 120, 60, 1600000001, 5)]

    async def test_delete_by_id(self, storage):
        await storage.update_state((1, 100, 0, 1600000000, 5))
        await storage.update_state(1)

        assert list(await storage.update_state()) == []


class TestSessionString:
    async def test_export_then_load_round_trips(self, storage, tmp_path):
        await storage.dc_id(2)
        await storage.api_id(12345)
        await storage.test_mode(False)
        await storage.auth_key(b"a" * 256)
        await storage.user_id(777000)
        await storage.is_bot(False)
        await storage.server_address("149.154.167.51")
        await storage.port(443)

        exported = await storage.export_session_string()

        target = FakeRemote("target")
        await target.open()

        try:
            await target.load_session_string(exported)

            assert await target.dc_id() == 2
            assert await target.api_id() == 12345
            assert await target.auth_key() == b"a" * 256
            assert await target.user_id() == 777000
            assert await target.server_address() == "149.154.167.51"
        finally:
            await target.close()


class TestClientSelection:
    """An explicit storage_engine used to be silently replaced by SQLite whenever
    a session string was also given, because session_string was checked first."""

    def test_explicit_engine_wins_over_session_string(self, tmp_path):
        import pyrogram

        engine = FakeRemote("explicit")

        client = pyrogram.Client(
            "explicit",
            api_id=12345,
            api_hash="0123456789abcdef0123456789abcdef",
            session_string="WZ_whatever",
            storage_engine=engine,
            workdir=tmp_path,
        )

        assert client.storage is engine
        assert engine.session_string == "WZ_whatever"

    def test_explicit_engine_wins_over_in_memory(self, tmp_path):
        import pyrogram

        engine = FakeRemote("explicit")

        client = pyrogram.Client(
            "explicit",
            api_id=12345,
            api_hash="0123456789abcdef0123456789abcdef",
            in_memory=True,
            storage_engine=engine,
            workdir=tmp_path,
        )

        assert client.storage is engine

    def test_default_is_still_sqlite(self, tmp_path):
        import pyrogram

        client = pyrogram.Client("plain", workdir=tmp_path)

        assert isinstance(client.storage, SQLiteStorage)
