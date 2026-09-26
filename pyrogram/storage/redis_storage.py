#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .remote_storage import PeerRow, RemoteStorage, StoredPeer

log = logging.getLogger(__name__)

DRIVER_MISSING = (
    "RedisStorage needs the redis package. Install it with "
    '`pip install "wzgram[redis]"`, or pass an already-created '
    "redis.asyncio client as the connection argument."
)

INT_FIELDS = ("dc_id", "port", "api_id", "date", "user_id")
BOOL_FIELDS = ("test_mode", "is_bot")


def _client_from_uri(uri: str):
    try:
        from redis.asyncio import Redis
    except ImportError as e:
        raise ImportError(DRIVER_MISSING) from e

    return Redis.from_url(uri)


def _decode(value: Any) -> Any:
    return value.decode() if isinstance(value, bytes) else value


class RedisStorage(RemoteStorage):
    """Keep the session in Redis.

    .. warning::

        An evicted session key is a lost login. Peers are a cache and can be
        evicted safely, but the session hash cannot - run the database with
        ``maxmemory-policy noeviction``, or give wzgram a database of its own.
        Opening this storage logs a warning when the server reports any other
        policy.

    Parameters:
        name (``str``):
            Session name, used to build the key prefix.

        connection (``str`` | ``object``):
            A connection URI, or an already-created ``redis.asyncio`` client.

        prefix (``str``, *optional*):
            Key prefix. Defaults to ``wzgram:<name>``.

        session_string (``str``, *optional*):
            Load this session string into the store when opening.
    """

    VERSION = 1

    def __init__(
        self,
        name: str,
        connection: Any,
        prefix: Optional[str] = None,
        session_string: Optional[str] = None,
    ):
        super().__init__(name, session_string=session_string)

        self._connection = connection
        self._prefix = prefix or f"wzgram:{name}"
        self._owns_client = isinstance(connection, str)

        self._redis = None

    def _key(self, *parts: Any) -> str:
        return ":".join([self._prefix, *(str(part) for part in parts)])

    async def _connect(self) -> None:
        self._redis = _client_from_uri(self._connection) if self._owns_client else self._connection

        try:
            config = await self._redis.config_get("maxmemory-policy")
            policy = _decode(config.get("maxmemory-policy") or config.get(b"maxmemory-policy"))
        except Exception:
            return

        if policy and policy != "noeviction":
            log.warning(
                "Redis eviction policy is %s: an evicted session key is a lost login. "
                "Use noeviction, or a database wzgram has to itself.",
                policy,
            )

    async def _disconnect(self) -> None:
        if self._owns_client and self._redis is not None:
            await self._redis.aclose()

        self._redis = None

    async def _load_session(self) -> Optional[Dict[str, Any]]:
        stored = await self._redis.hgetall(self._key("session"))

        if not stored:
            return None

        session = {}

        for key, value in stored.items():
            key = _decode(key)

            if value in (b"", ""):
                session[key] = None
            elif key == "auth_key":
                session[key] = bytes(value)
            elif key in INT_FIELDS:
                session[key] = int(value)
            elif key in BOOL_FIELDS:
                session[key] = bool(int(value))
            else:
                session[key] = _decode(value)

        return session

    async def _save_session(self, fields: Dict[str, Any]) -> None:
        mapping = {}

        for key, value in fields.items():
            if value is None:
                mapping[key] = ""
            elif isinstance(value, bool):
                mapping[key] = int(value)
            elif isinstance(value, (bytes, bytearray)):
                mapping[key] = bytes(value)
            else:
                mapping[key] = value

        await self._redis.hset(self._key("session"), mapping=mapping)

    async def _load_version(self) -> Optional[int]:
        stored = await self._redis.get(self._key("version"))

        return int(stored) if stored is not None else None

    async def _save_version(self, version: int) -> None:
        await self._redis.set(self._key("version"), version)

    async def _upsert_peers(self, rows: List[PeerRow]) -> None:
        now = int(time.time())
        pipe = self._redis.pipeline()

        for peer_id, access_hash, peer_type, phone_number in rows:
            pipe.hset(
                self._key("peer", peer_id),
                mapping={
                    "access_hash": access_hash if access_hash is not None else "",
                    "type": peer_type,
                    "phone_number": phone_number or "",
                    "last_update_on": now,
                },
            )
            pipe.sadd(self._key("peers"), peer_id)

            if phone_number:
                pipe.set(self._key("phone", phone_number), peer_id)

        await pipe.execute()

    async def _peer_row(self, peer_id: int) -> Optional[StoredPeer]:
        stored = await self._redis.hgetall(self._key("peer", peer_id))

        if not stored:
            return None

        stored = {_decode(k): _decode(v) for k, v in stored.items()}
        access_hash = stored.get("access_hash")

        return (
            int(peer_id),
            int(access_hash) if access_hash not in (None, "") else None,
            stored.get("type"),
            int(stored.get("last_update_on") or 0),
        )

    async def _fetch_peer(self, peer_id: int) -> Optional[StoredPeer]:
        return await self._peer_row(peer_id)

    async def _fetch_peer_by_username(self, username: str) -> Optional[StoredPeer]:
        peer_id = await self._redis.get(self._key("username", username))

        if peer_id is None:
            return None

        return await self._peer_row(int(peer_id))

    async def _fetch_peer_by_phone(self, phone_number: str) -> Optional[StoredPeer]:
        peer_id = await self._redis.get(self._key("phone", phone_number))

        if peer_id is None:
            return None

        return await self._peer_row(int(peer_id))

    async def _iter_peers(self, limit: Optional[int] = None) -> List[PeerRow]:
        rows = []

        for raw_id in await self._redis.smembers(self._key("peers")):
            peer_id = int(_decode(raw_id))
            stored = await self._redis.hgetall(self._key("peer", peer_id))

            if not stored:
                continue

            stored = {_decode(k): _decode(v) for k, v in stored.items()}
            access_hash = stored.get("access_hash")

            rows.append(
                (
                    peer_id,
                    int(access_hash) if access_hash not in (None, "") else None,
                    stored.get("type"),
                    stored.get("phone_number") or None,
                )
            )

            if limit is not None and len(rows) >= limit:
                break

        return rows

    async def _replace_usernames(self, usernames: List[Tuple[int, List[str]]]) -> None:
        pipe = self._redis.pipeline()

        for peer_id, names in usernames:
            known = await self._redis.smembers(self._key("peer", peer_id, "usernames"))

            for username in known:
                pipe.delete(self._key("username", _decode(username)))

            pipe.delete(self._key("peer", peer_id, "usernames"))

            for username in names:
                pipe.set(self._key("username", username), peer_id)
                pipe.sadd(self._key("peer", peer_id, "usernames"), username)

        await pipe.execute()

    async def _load_states(self) -> List[Tuple[int, int, int, int, int]]:
        states = []

        for raw_id in await self._redis.smembers(self._key("states")):
            state_id = int(_decode(raw_id))
            stored = await self._redis.hgetall(self._key("state", state_id))

            if not stored:
                continue

            stored = {_decode(k): _decode(v) for k, v in stored.items()}

            states.append(
                (state_id,) + tuple(
                    int(stored[field]) if stored.get(field) not in (None, "") else None
                    for field in ("pts", "qts", "date", "seq")
                )
            )

        states.sort(key=lambda state: state[3] or 0)

        return states

    async def _save_state(self, state: Tuple[int, int, int, int, int]) -> None:
        state_id, pts, qts, date, seq = state
        mapping = {
            field: value
            for field, value in zip(("pts", "qts", "date", "seq"), (pts, qts, date, seq))
            if value is not None
        }

        if not mapping:
            return

        pipe = self._redis.pipeline()
        pipe.hset(self._key("state", state_id), mapping=mapping)
        pipe.sadd(self._key("states"), state_id)

        await pipe.execute()

    async def _delete_state(self, state_id: int) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._key("state", state_id))
        pipe.srem(self._key("states"), state_id)

        await pipe.execute()

    async def _purge(self, remove_peers: bool) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._key("session"))
        pipe.delete(self._key("version"))

        for raw_id in await self._redis.smembers(self._key("states")):
            pipe.delete(self._key("state", _decode(raw_id)))

        pipe.delete(self._key("states"))

        if remove_peers:
            for raw_id in await self._redis.smembers(self._key("peers")):
                peer_id = _decode(raw_id)

                for username in await self._redis.smembers(self._key("peer", peer_id, "usernames")):
                    pipe.delete(self._key("username", _decode(username)))

                pipe.delete(self._key("peer", peer_id, "usernames"))
                pipe.delete(self._key("peer", peer_id))

            pipe.delete(self._key("peers"))

        await pipe.execute()
