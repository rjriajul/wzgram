"""MongoStorage and RedisStorage against fake drivers.

The mapping between wzgram's storage contract and a document or a key layout is
where these engines break, and it needs no server to check. Integration against
a real server runs only when WZGRAM_TEST_MONGO_URI / WZGRAM_TEST_REDIS_URI are
set.
"""

import os

import pytest

from pyrogram.storage import MongoStorage, RedisStorage


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []

    async def create_index(self, key):
        self.indexes.append(key)

    async def find_one(self, query):
        if "_id" in query:
            return self.documents.get(query["_id"])

        for document in self.documents.values():
            if all(document.get(k) == v for k, v in query.items()):
                return document

        return None

    async def update_one(self, query, update, upsert=False):
        if not update.get("$set"):
            raise ValueError("'$set' is empty. You must specify a field like so: {$set: {<field>: ...}}")

        key = query["_id"]
        document = self.documents.get(key)

        if document is None:
            if not upsert:
                return
            document = {"_id": key}
            self.documents[key] = document

        document.update(update["$set"])

    async def delete_one(self, query):
        self.documents.pop(query.get("_id"), None)

    async def delete_many(self, query):
        if not query:
            self.documents.clear()
            return

        if "peer_id" in query and "$in" in query["peer_id"]:
            wanted = set(query["peer_id"]["$in"])
            for key in [k for k, d in self.documents.items() if d.get("peer_id") in wanted]:
                del self.documents[key]

    def find(self, query):
        documents = list(self.documents.values())

        class Cursor:
            def __aiter__(self):
                self._it = iter(documents)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration

        return Cursor()


class FakeDatabase(dict):
    def __missing__(self, key):
        self[key] = FakeCollection()
        return self[key]


class FakeMongoClient(dict):
    def __missing__(self, key):
        self[key] = FakeDatabase()
        return self[key]


@pytest.fixture
async def mongo():
    storage = MongoStorage("driver", FakeMongoClient())

    await storage.open()

    try:
        yield storage
    finally:
        await storage.close()


class TestMongoMapping:
    async def test_session_is_one_document(self, mongo):
        await mongo.dc_id(4)
        await mongo.auth_key(b"k" * 256)

        document = mongo._session.documents[0]

        assert document["_id"] == 0
        assert document["dc_id"] == 4
        assert document["auth_key"] == b"k" * 256

    async def test_peers_are_keyed_by_id(self, mongo):
        await mongo.update_peers([(123, 456, "user", "15551234567")])

        document = mongo._peers.documents[123]

        assert document["access_hash"] == 456
        assert document["type"] == "user"
        assert document["last_update_on"] > 0

        peer = await mongo.get_peer_by_phone_number("15551234567")
        assert peer.user_id == 123

    async def test_usernames_are_keyed_by_name(self, mongo):
        await mongo.update_peers([(123, 456, "user", None)])
        await mongo.update_usernames([(123, ["alice", "alice2"])])

        assert mongo._usernames.documents["alice"]["peer_id"] == 123
        assert (await mongo.get_peer_by_username("alice2")).user_id == 123

    async def test_indexes_created_on_open(self, mongo):
        assert "phone_number" in mongo._peers.indexes
        assert "peer_id" in mongo._usernames.indexes

    async def test_a_state_field_left_out_is_kept(self, mongo):
        await mongo.update_state((0, 10, 50, 7, 1))
        await mongo.update_state((0, 11, None, 8, None))

        assert [tuple(s) for s in await mongo.update_state()] == [(0, 11, 50, 8, 1)]

    async def test_a_state_with_nothing_to_store_is_skipped(self, mongo):
        await mongo.update_state((0, None, None, None, None))

        assert list(await mongo.update_state()) == []

    async def test_version_is_recorded(self, mongo):
        assert await mongo.version() == MongoStorage.VERSION

    async def test_pyrofork_import_resolves_the_address(self):
        client = FakeMongoClient()
        session = client["legacy"]["session"]
        session.documents[0] = {"_id": 0, "dc_id": 4, "test_mode": False, "auth_key": b"k" * 256}

        storage = MongoStorage("legacy", client)
        await storage.open()

        try:
            await storage.import_pyrofork()

            assert session.documents[0]["server_address"] == "149.154.167.91"
            assert session.documents[0]["port"] == 443
        finally:
            await storage.close()


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return record

    async def execute(self):
        for name, args, kwargs in self.calls:
            await getattr(self.redis, name)(*args, **kwargs)

        self.calls.clear()


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.strings = {}
        self.sets = {}

    def pipeline(self):
        return FakePipeline(self)

    async def config_get(self, key):
        return {"maxmemory-policy": "noeviction"}

    async def hset(self, key, mapping=None, **kwargs):
        if not mapping:
            raise ValueError("'hset' with no key value pairs")

        for value in mapping.values():
            if value is None:
                raise TypeError("Invalid input of type: 'NoneType'. Convert to a bytes, string, int or float first.")

        self.hashes.setdefault(key, {}).update(mapping)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def set(self, key, value):
        self.strings[key] = value

    async def get(self, key):
        return self.strings.get(key)

    async def delete(self, key):
        self.hashes.pop(key, None)
        self.strings.pop(key, None)
        self.sets.pop(key, None)

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key, member):
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def aclose(self):
        pass


@pytest.fixture
async def redis():
    storage = RedisStorage("driver", FakeRedis())

    await storage.open()

    try:
        yield storage
    finally:
        await storage.close()


class TestRedisMapping:
    async def test_session_is_one_hash(self, redis):
        await redis.dc_id(4)
        await redis.auth_key(b"k" * 256)
        await redis.is_bot(True)

        stored = redis._redis.hashes["wzgram:driver:session"]

        assert stored["dc_id"] == 4
        assert stored["auth_key"] == b"k" * 256

        assert await redis.dc_id() == 4
        assert await redis.auth_key() == b"k" * 256
        assert await redis.is_bot() is True

    async def test_none_round_trips_as_none(self, redis):
        await redis.api_id(None)

        assert await redis.api_id() is None

    async def test_peer_keys_and_indexes(self, redis):
        await redis.update_peers([(123, 456, "user", "15551234567")])

        assert "wzgram:driver:peer:123" in redis._redis.hashes
        assert 123 in redis._redis.sets["wzgram:driver:peers"]
        assert (await redis.get_peer_by_phone_number("15551234567")).user_id == 123

    async def test_username_reassignment_clears_the_old_key(self, redis):
        await redis.update_peers([(1, 11, "user", None), (2, 22, "user", None)])
        await redis.update_usernames([(1, ["shared"])])
        await redis.update_usernames([(1, []), (2, ["shared"])])

        assert (await redis.get_peer_by_username("shared")).user_id == 2

    async def test_state_round_trip(self, redis):
        await redis.update_state((7, 100, 0, 1600000000, 3))

        assert [tuple(s) for s in await redis.update_state()] == [(7, 100, 0, 1600000000, 3)]

        await redis.update_state(7)

        assert list(await redis.update_state()) == []

    async def test_a_state_field_left_out_is_kept(self, redis):
        await redis.update_state((0, 10, 50, 7, 1))
        await redis.update_state((0, 11, None, 8, None))

        assert [tuple(s) for s in await redis.update_state()] == [(0, 11, 50, 8, 1)]

    async def test_a_state_never_given_a_field_reads_it_as_none(self, redis):
        await redis.update_state((0, None, 50, 7, None))

        assert [tuple(s) for s in await redis.update_state()] == [(0, None, 50, 7, None)]

    async def test_a_state_with_nothing_to_store_is_skipped(self, redis):
        await redis.update_state((0, None, None, None, None))

        assert list(await redis.update_state()) == []

    async def test_purge_removes_everything(self, redis):
        await redis.update_peers([(1, 11, "user", None)])
        await redis.update_usernames([(1, ["alice"])])
        await redis.update_state((7, 1, 0, 1, 1))

        await redis.delete()

        assert redis._redis.hashes.get("wzgram:driver:session") in (None, {})
        assert not redis._redis.sets.get("wzgram:driver:peers")

    async def test_delete_works_after_close(self):
        server = FakeRedis()
        storage = RedisStorage("logout", server)

        await storage.open()
        await storage.auth_key(b"k" * 256)
        await storage.close()

        await storage.delete()

        assert not server.hashes.get("wzgram:logout:session"), "the login survived log_out"
        assert storage._redis is None, "delete must not leave the connection open"

    async def test_eviction_policy_warning(self, caplog):
        class Evicting(FakeRedis):
            async def config_get(self, key):
                return {"maxmemory-policy": "allkeys-lru"}

        storage = RedisStorage("warn", Evicting())

        with caplog.at_level("WARNING"):
            await storage.open()

        await storage.close()

        assert any("lost login" in record.message for record in caplog.records)


@pytest.mark.skipif(
    not os.environ.get("WZGRAM_TEST_MONGO_URI"), reason="WZGRAM_TEST_MONGO_URI not set"
)
class TestMongoIntegration:
    async def test_round_trip_against_a_real_server(self):
        storage = MongoStorage("wzgram_test", os.environ["WZGRAM_TEST_MONGO_URI"])

        await storage.open()

        try:
            await storage.auth_key(b"k" * 256)
            await storage.update_peers([(123, 456, "user", None)])

            assert (await storage.get_peer_by_id(123)).access_hash == 456
        finally:
            await storage.delete()
            await storage.close()


@pytest.mark.skipif(
    not os.environ.get("WZGRAM_TEST_REDIS_URI"), reason="WZGRAM_TEST_REDIS_URI not set"
)
class TestRedisIntegration:
    async def test_round_trip_against_a_real_server(self):
        storage = RedisStorage("wzgram_test", os.environ["WZGRAM_TEST_REDIS_URI"])

        await storage.open()

        try:
            await storage.auth_key(b"k" * 256)
            await storage.update_peers([(123, 456, "user", None)])

            assert (await storage.get_peer_by_id(123)).access_hash == 456
        finally:
            await storage.delete()
            await storage.close()
