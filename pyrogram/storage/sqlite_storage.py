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

import aiosqlite
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .caching import PEER_CACHE_SIZE, PeerRowCache, SessionAttrCache, get_input_peer
from .storage import PROD, TEST, Storage

try:
    import fcntl
except ImportError:
    fcntl = None

log = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE sessions
(
    dc_id          INTEGER PRIMARY KEY,
    server_address TEXT,
    port           INTEGER,
    api_id         INTEGER,
    test_mode      INTEGER,
    auth_key       BLOB,
    date           INTEGER NOT NULL,
    user_id        INTEGER,
    is_bot         INTEGER
);

CREATE TABLE peers
(
    id             INTEGER PRIMARY KEY,
    access_hash    INTEGER,
    type           INTEGER NOT NULL,
    phone_number   TEXT,
    last_update_on INTEGER NOT NULL DEFAULT (CAST(STRFTIME('%s', 'now') AS INTEGER))
);

CREATE TABLE usernames
(
    id       INTEGER,
    username TEXT,
    FOREIGN KEY (id) REFERENCES peers(id)
);

CREATE TABLE update_state
(
    id   INTEGER PRIMARY KEY,
    pts  INTEGER,
    qts  INTEGER,
    date INTEGER,
    seq  INTEGER
);

CREATE TABLE version
(
    number INTEGER PRIMARY KEY
);

CREATE INDEX idx_peers_id ON peers (id);
CREATE INDEX idx_peers_phone_number ON peers (phone_number);
CREATE INDEX idx_usernames_id ON usernames (id);
CREATE INDEX idx_usernames_username ON usernames (username);

CREATE TRIGGER trg_peers_last_update_on
    AFTER UPDATE
    ON peers
BEGIN
    UPDATE peers
    SET last_update_on = CAST(STRFTIME('%s', 'now') AS INTEGER)
    WHERE id = NEW.id;
END;
"""

USERNAMES_SCHEMA = """
CREATE TABLE usernames
(
    id       INTEGER,
    username TEXT,
    FOREIGN KEY (id) REFERENCES peers(id)
);

CREATE INDEX idx_usernames_username ON usernames (username);
"""

UPDATE_STATE_SCHEMA = """
CREATE TABLE update_state
(
    id   INTEGER PRIMARY KEY,
    pts  INTEGER,
    qts  INTEGER,
    date INTEGER,
    seq  INTEGER
);
"""

def _try_lock(path: Path) -> Optional[object]:
    if fcntl is None:
        return None

    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
    except OSError:
        return None

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None

    return fd


def _unlock(fd: object):
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except OSError:
            pass


class SQLiteStorage(Storage):
    VERSION = 8
    USERNAME_TTL = 8 * 60 * 60
    FILE_EXTENSION = ".session"
    _AUTO_COMMIT_INTERVAL = 20
    _AUTO_COMMIT_SECONDS = 5
    _PEER_CACHE_SIZE = PEER_CACHE_SIZE

    def __init__(
        self,
        name: str,
        workdir: Path,
        session_string: Optional[str] = None,
        in_memory: Optional[bool] = False,
        use_wal: Optional[bool] = True,
    ):
        super().__init__(name)

        self.conn: Optional[aiosqlite.Connection] = None

        self.session_string = session_string
        self.in_memory = in_memory
        self.use_wal = use_wal

        self._cache = SessionAttrCache()
        self._peer_cache = PeerRowCache(self._PEER_CACHE_SIZE, self.USERNAME_TTL / 2)
        self._dirty: bool = False
        self._write_count: int = 0
        self._flush_task: Optional[asyncio.Task] = None
        self._lock_fd: Optional[object] = None

        if self.in_memory:
            self.database = ":memory:"
        else:
            self.database = workdir / (self.name + self.FILE_EXTENSION)

    async def _ensure_committed(self):
        if self._dirty and self.conn is not None:
            await self.conn.commit()
            self._dirty = False

    async def _maybe_commit(self):
        self._dirty = True
        self._write_count += 1

        if self._write_count >= self._AUTO_COMMIT_INTERVAL:
            self._write_count = 0
            await self._ensure_committed()
            return

        self._schedule_flush()

    def _schedule_flush(self):
        """Bound how long a batch that never fills can stay uncommitted.

        Batching by count alone leaves the last writes below the batch size in an
        open write transaction for as long as the process runs: a kill loses them
        - the update state among them, so gap recovery restarts from a stale pts -
        and an open write transaction is also what stops the WAL being
        checkpointed.
        """
        if self._flush_task is not None and not self._flush_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        self._flush_task = loop.create_task(self._flush_later())

    async def _flush_later(self):
        try:
            await asyncio.sleep(self._AUTO_COMMIT_SECONDS)

            if self.conn is not None:
                self._write_count = 0
                await self._ensure_committed()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Deferred session commit failed")

    async def update(self):
        version = await self.version()

        if version == 1:
            await self.conn.execute("DELETE FROM peers;")
            self._peer_cache.clear()
            await self.conn.commit()
            version += 1

        if version == 2:
            await self.conn.execute("ALTER TABLE sessions ADD api_id INTEGER;")
            await self.conn.commit()
            version += 1

        if version == 3:
            await self.conn.executescript(USERNAMES_SCHEMA)
            version += 1

        if version == 4:
            await self.conn.executescript(UPDATE_STATE_SCHEMA)
            version += 1

        if version == 5:
            await self.conn.execute("CREATE INDEX idx_usernames_id ON usernames (id);")
            await self.conn.commit()
            version += 1

        if version == 6:
            await self.conn.execute("ALTER TABLE sessions ADD server_address TEXT;")
            await self.conn.execute("ALTER TABLE sessions ADD port INTEGER;")
            await self.conn.commit()
            version += 1

        if version == 7:
            test_mode = await self.test_mode()
            address = (TEST if test_mode else PROD).get(await self.dc_id())

            if address is not None:
                await self.conn.execute(
                    "UPDATE sessions SET server_address = ?, port = ?;",
                    (address, 80 if test_mode else 443)
                )
                await self.conn.commit()

            version += 1

        await self.version(version)

    async def create(self):
        await self.conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.execute("INSERT INTO version VALUES (?)", (self.VERSION,))
        row = (2, "149.154.167.51", 443, None, None, None, 0, None, None)
        await self.conn.execute(
            "INSERT INTO sessions (dc_id, server_address, port, api_id, test_mode, auth_key, date, user_id, is_bot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row
        )
        await self.conn.commit()

    async def open(self):
        if self.in_memory:
            self.conn = await aiosqlite.connect(":memory:", timeout=5)
            await self.create()

            if self.session_string:
                await self.load_session_string(self.session_string)

            await self._ensure_committed()
            return

        path = self.database
        file_exists = isinstance(path, Path) and path.is_file()

        lock_path = path.with_suffix(".session.lock")
        self._lock_fd = _try_lock(lock_path)
        if self._lock_fd is None and fcntl is not None and file_exists:
            log.warning("Could not acquire lock on %s — another client may be using the same session", lock_path)

        self.conn = await aiosqlite.connect(str(path), timeout=5)

        if self.use_wal:
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA synchronous=NORMAL")
        else:
            await self.conn.execute("PRAGMA journal_mode=DELETE")

        if file_exists:
            await self.update()
        else:
            await self.create()

            if self.session_string:
                await self.load_session_string(self.session_string)

        await self._load_cache()
        await self._ensure_committed()

    async def _load_cache(self):
        cursor = await self.conn.execute(
            "SELECT dc_id, server_address, port, api_id, test_mode, "
            "       auth_key, date, user_id, is_bot "
            "FROM sessions LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            keys = ["dc_id", "server_address", "port", "api_id",
                    "test_mode", "auth_key", "date", "user_id", "is_bot"]
            self._cache.load(dict(zip(keys, row)))

    async def save(self):
        await self._write_attr("date", int(time.time()))
        await self._ensure_committed()

    async def close(self):
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None

        await self._ensure_committed()

        if self.conn:
            await self.conn.close()
            self.conn = None

        if self._lock_fd is not None:
            _unlock(self._lock_fd)
            self._lock_fd = None

        self._cache.clear()

    async def delete(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

        if self._lock_fd is not None:
            _unlock(self._lock_fd)
            self._lock_fd = None

        if not self.in_memory:
            path = Path(self.database)
            lock_path = path.with_suffix(".session.lock")
            if path.exists():
                path.unlink()
            if lock_path.exists():
                lock_path.unlink()

    async def update_peers(self, peers: List[Tuple[int, int, str, str]]):
        if not peers or self.conn is None:
            return

        fresh = [p for p in peers if not self._peer_cache.matches(*p)]

        if not fresh:
            return

        await self.conn.executemany(
            "REPLACE INTO peers (id, access_hash, type, phone_number) VALUES (?, ?, ?, ?)", fresh
        )

        for peer_id, access_hash, peer_type, phone_number in fresh:
            self._peer_cache.remember(
                (peer_id, access_hash, peer_type), phone_number, written=True
            )

        await self._maybe_commit()

    async def update_usernames(self, usernames: List[Tuple[int, List[str]]]):
        if not usernames or self.conn is None:
            return
        await self.conn.executemany("DELETE FROM usernames WHERE id = ?", [(id,) for id, _ in usernames])

        await self.conn.executemany(
            "REPLACE INTO usernames (id, username) VALUES (?, ?)",
            [(id, username) for id, usernames in usernames for username in usernames],
        )
        await self._maybe_commit()

    async def update_state(self, value: Tuple[int, int, int, int, int] = object):
        if self.conn is None:
            return [] if value is object else None

        if value is object:
            cursor = await self.conn.execute(
                "SELECT id, pts, qts, date, seq FROM update_state ORDER BY date ASC"
            )
            return await cursor.fetchall()
        else:
            if isinstance(value, int):
                await self.conn.execute("DELETE FROM update_state WHERE id = ?", (value,))
            else:
                await self.conn.execute(
                    "INSERT INTO update_state (id, pts, qts, date, seq) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "  pts   = excluded.pts,"
                    "  qts   = excluded.qts,"
                    "  date  = excluded.date,"
                    "  seq   = excluded.seq",
                    value,
                )

            await self._maybe_commit()

    async def get_peer_by_id(self, peer_id: int):
        row = self._peer_cache.get(peer_id)

        if row is not None:
            return get_input_peer(*row)

        if self.conn is None:
            raise ConnectionError("Database is not open")

        cursor = await self.conn.execute(
            "SELECT id, access_hash, type FROM peers WHERE id = ?", (peer_id,)
        )
        r = await cursor.fetchone()

        if r is None:
            raise KeyError(f"ID not found: {peer_id}")

        self._peer_cache.remember(tuple(r))

        return get_input_peer(*r)

    async def get_peer_by_username(self, username: str):
        if self.conn is None:
            raise ConnectionError("Database is not open")

        cursor = await self.conn.execute(
            "SELECT p.id, p.access_hash, p.type, p.last_update_on FROM peers p "
            "JOIN usernames u ON p.id = u.id "
            "WHERE u.username = ? "
            "ORDER BY p.last_update_on DESC",
            (username,),
        )
        r = await cursor.fetchone()

        if r is None:
            raise KeyError(f"Username not found: {username}")

        if abs(time.time() - r[3]) > self.USERNAME_TTL:
            raise KeyError(f"Username expired: {username}")

        return get_input_peer(*r[:3])

    async def get_peer_by_phone_number(self, phone_number: str):
        if self.conn is None:
            raise ConnectionError("Database is not open")

        cursor = await self.conn.execute(
            "SELECT id, access_hash, type FROM peers WHERE phone_number = ?", (phone_number,)
        )
        r = await cursor.fetchone()

        if r is None:
            raise KeyError(f"Phone number not found: {phone_number}")

        return get_input_peer(*r)

    async def _read_attr(self, attr: str):
        if self.conn is None:
            raise ConnectionError("Database is not open")
        if attr in self._cache:
            return self._cache.get(attr)
        cursor = await self.conn.execute(f"SELECT {attr} FROM sessions LIMIT 1")
        row = await cursor.fetchone()
        self._cache.remember(attr, row[0] if row else None)
        return self._cache.get(attr)

    async def _write_attr(self, attr: str, value: Any):
        if self.conn is None:
            raise ConnectionError("Database is not open")
        await self.conn.execute(f"UPDATE sessions SET {attr} = ?", (value,))
        self._cache.set(attr, value)
        await self._maybe_commit()

    async def dc_id(self, value: int = object):
        if value is object:
            return await self._read_attr("dc_id")
        await self._write_attr("dc_id", value)
        return value

    async def server_address(self, value: str = object):
        if value is object:
            return await self._read_attr("server_address")
        await self._write_attr("server_address", value)
        return value

    async def port(self, value: int = object):
        if value is object:
            return await self._read_attr("port")
        await self._write_attr("port", value)
        return value

    async def api_id(self, value: int = object):
        if value is object:
            return await self._read_attr("api_id")
        await self._write_attr("api_id", value)
        return value

    async def test_mode(self, value: bool = object):
        if value is object:
            return await self._read_attr("test_mode")
        await self._write_attr("test_mode", value)
        return value

    async def auth_key(self, value: bytes = object):
        if value is object:
            return await self._read_attr("auth_key")
        await self._write_attr("auth_key", value)
        return value

    async def date(self, value: int = object):
        if value is object:
            return await self._read_attr("date")
        await self._write_attr("date", value)
        return value

    async def user_id(self, value: int = object):
        if value is object:
            return await self._read_attr("user_id")
        await self._write_attr("user_id", value)
        return value

    async def is_bot(self, value: bool = object):
        if value is object:
            return await self._read_attr("is_bot")
        await self._write_attr("is_bot", value)
        return value

    async def version(self, value: int = object):
        if self.conn is None:
            raise ConnectionError("Database is not open")
        if value is object:
            cursor = await self.conn.execute("SELECT number FROM version")
            row = await cursor.fetchone()
            return row[0] if row else None
        else:
            await self.conn.execute("UPDATE version SET number = ?", (value,))
            await self.conn.commit()
