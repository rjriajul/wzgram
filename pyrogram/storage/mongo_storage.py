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
    "MongoStorage needs an async MongoDB driver. Install one with "
    '`pip install "wzgram[mongo]"`, or pass an already-created client '
    "(motor or async_pymongo) as the connection argument."
)


def _client_from_uri(uri: str):
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        pass
    else:
        return AsyncIOMotorClient(uri)

    try:
        from async_pymongo import AsyncClient
    except ImportError as e:
        raise ImportError(DRIVER_MISSING) from e

    return AsyncClient(uri)


class MongoStorage(RemoteStorage):
    """Keep the session in MongoDB.

    Every read that matters is served from the caches in
    :obj:`~pyrogram.storage.RemoteStorage`, so Mongo is touched on open, on a peer
    the client has never seen, and on writes.

    Parameters:
        name (``str``):
            Session name. Also the default database name.

        connection (``str`` | ``object``):
            A connection URI, or an already-created ``motor`` / ``async_pymongo``
            client to reuse.

        database (``str``, *optional*):
            Database to use. Defaults to *name*.

        session_string (``str``, *optional*):
            Load this session string into the store when opening.
    """

    VERSION = 1

    def __init__(
        self,
        name: str,
        connection: Any,
        database: Optional[str] = None,
        session_string: Optional[str] = None,
    ):
        super().__init__(name, session_string=session_string)

        self._connection = connection
        self._database_name = database or name
        self._owns_client = isinstance(connection, str)

        self._client = None
        self._db = None
        self._session = None
        self._peers = None
        self._usernames = None
        self._states = None
        self._version = None

    async def _connect(self) -> None:
        self._client = _client_from_uri(self._connection) if self._owns_client else self._connection

        self._db = self._client[self._database_name]
        self._session = self._db["session"]
        self._peers = self._db["peers"]
        self._usernames = self._db["usernames"]
        self._states = self._db["update_state"]
        self._version = self._db["version"]

        await self._peers.create_index("phone_number")
        await self._usernames.create_index("peer_id")

    async def _disconnect(self) -> None:
        if self._owns_client and self._client is not None:
            close = getattr(self._client, "close", None)

            if close is not None:
                result = close()

                if hasattr(result, "__await__"):
                    await result

        self._client = None
        self._db = None

    async def _load_session(self) -> Optional[Dict[str, Any]]:
        document = await self._session.find_one({"_id": 0})

        if document is None:
            return None

        document = dict(document)
        document.pop("_id", None)

        auth_key = document.get("auth_key")

        if auth_key is not None and not isinstance(auth_key, bytes):
            document["auth_key"] = bytes(auth_key)

        return document

    async def _save_session(self, fields: Dict[str, Any]) -> None:
        await self._session.update_one({"_id": 0}, {"$set": dict(fields)}, upsert=True)

    async def _load_version(self) -> Optional[int]:
        document = await self._version.find_one({"_id": 0})

        return document.get("number") if document else None

    async def _save_version(self, version: int) -> None:
        await self._version.update_one({"_id": 0}, {"$set": {"number": version}}, upsert=True)

    async def _upsert_peers(self, rows: List[PeerRow]) -> None:
        now = int(time.time())

        for peer_id, access_hash, peer_type, phone_number in rows:
            await self._peers.update_one(
                {"_id": peer_id},
                {
                    "$set": {
                        "access_hash": access_hash,
                        "type": peer_type,
                        "phone_number": phone_number,
                        "last_update_on": now,
                    }
                },
                upsert=True,
            )

    @staticmethod
    def _peer_row(document: Optional[Dict[str, Any]]) -> Optional[StoredPeer]:
        if document is None:
            return None

        return (
            document["_id"],
            document.get("access_hash"),
            document.get("type"),
            document.get("last_update_on", 0),
        )

    async def _fetch_peer(self, peer_id: int) -> Optional[StoredPeer]:
        return self._peer_row(await self._peers.find_one({"_id": peer_id}))

    async def _fetch_peer_by_username(self, username: str) -> Optional[StoredPeer]:
        mapping = await self._usernames.find_one({"_id": username})

        if mapping is None:
            return None

        return self._peer_row(await self._peers.find_one({"_id": mapping["peer_id"]}))

    async def _fetch_peer_by_phone(self, phone_number: str) -> Optional[StoredPeer]:
        return self._peer_row(await self._peers.find_one({"phone_number": phone_number}))

    async def _iter_peers(self, limit: Optional[int] = None) -> List[PeerRow]:
        rows = []

        cursor = self._peers.find({})

        async for document in cursor:
            rows.append(
                (
                    document["_id"],
                    document.get("access_hash"),
                    document.get("type"),
                    document.get("phone_number"),
                )
            )

            if limit is not None and len(rows) >= limit:
                break

        return rows

    async def _replace_usernames(self, usernames: List[Tuple[int, List[str]]]) -> None:
        peer_ids = [peer_id for peer_id, _ in usernames]

        await self._usernames.delete_many({"peer_id": {"$in": peer_ids}})

        for peer_id, names in usernames:
            for username in names:
                await self._usernames.update_one(
                    {"_id": username}, {"$set": {"peer_id": peer_id}}, upsert=True
                )

    async def _load_states(self) -> List[Tuple[int, int, int, int, int]]:
        states = []

        cursor = self._states.find({})

        async for document in cursor:
            states.append(
                (
                    document["_id"],
                    document.get("pts"),
                    document.get("qts"),
                    document.get("date"),
                    document.get("seq"),
                )
            )

        states.sort(key=lambda state: state[3] or 0)

        return states

    async def _save_state(self, state: Tuple[int, int, int, int, int]) -> None:
        state_id, pts, qts, date, seq = state
        fields = {
            field: value
            for field, value in zip(("pts", "qts", "date", "seq"), (pts, qts, date, seq))
            if value is not None
        }

        if not fields:
            return

        await self._states.update_one({"_id": state_id}, {"$set": fields}, upsert=True)

    async def _delete_state(self, state_id: int) -> None:
        await self._states.delete_one({"_id": state_id})

    async def _purge(self, remove_peers: bool) -> None:
        await self._session.delete_many({})
        await self._states.delete_many({})

        if remove_peers:
            await self._peers.delete_many({})
            await self._usernames.delete_many({})

    async def import_pyrofork(self) -> int:
        """Read a session written by pyrofork's MongoStorage into this one.

        Their layout carries no ``server_address`` or ``port``; the address is
        resolved from the datacenter id the way a session string with none is.
        Returns the number of peers imported.
        """
        from .storage import PROD, TEST

        document = await self._session.find_one({"_id": 0})

        if document is None:
            return 0

        test_mode = document.get("test_mode")

        if not document.get("server_address"):
            address = (TEST if test_mode else PROD).get(document.get("dc_id"))

            if address is not None:
                await self._save_session(
                    {"server_address": address, "port": 80 if test_mode else 443}
                )

        migrated = 0
        cursor = self._usernames.find({})

        async for entry in cursor:
            if "username" in entry and "id" in entry:
                await self._usernames.update_one(
                    {"_id": entry["username"]}, {"$set": {"peer_id": entry["id"]}}, upsert=True
                )
                await self._usernames.delete_one({"_id": entry["_id"]})

        cursor = self._peers.find({})

        async for entry in cursor:
            if "id" in entry and entry["_id"] != entry["id"]:
                entry = dict(entry)
                peer_id = entry.pop("id")
                entry.pop("_id", None)

                await self._peers.update_one({"_id": peer_id}, {"$set": entry}, upsert=True)
                migrated += 1

        await self._save_version(self.VERSION)

        return migrated
