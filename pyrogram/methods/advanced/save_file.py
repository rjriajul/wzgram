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

import asyncio
import functools
import inspect
import io
import logging
import math
import os
import time
from hashlib import md5
from pathlib import PurePath
from typing import Union, BinaryIO, Callable, Optional

import pyrogram
from pyrogram import StopTransmission
from pyrogram import raw
from pyrogram.errors import RPCError
from pyrogram.session import Session

log = logging.getLogger(__name__)

PART_SIZE = 512 * 1024
POOL_SIZE = 20
MAX_RETRIES = 16
READ_BUFFER = 4 * 1024 * 1024
PROGRESS_INTERVAL = 0.2


class SaveFile:
    async def save_file(
        self: "pyrogram.Client",
        path: Union[str, BinaryIO],
        file_id: Optional[int] = None,
        file_part: int = 0,
        progress: Optional[Callable] = None,
        progress_args: tuple = (),
    ):
        """Upload a file onto Telegram servers, without sending the message to anyone.

        Useful whenever an InputFile type is required for raw API functions.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            path (``str`` | ``BinaryIO``):
                File path or binary file-like object.

            file_id (``int``, *optional*):
                File ID to resume an interrupted upload.

            file_part (``int``, *optional*):
                Part number to resume from.

            progress (``Callable``, *optional*):
                Callback — takes *(current, total)* as positional arguments.

            progress_args (``tuple``, *optional*):
                Extra arguments for the progress callback.

        Returns:
            ``InputFile | InputFileBig``: On success.

        Raises:
            RPCError: In case of a Telegram RPC error.
        """
        async with self.save_file_semaphore:
            if path is None:
                return None

            async def worker(session):
                while True:
                    data = await queue.get()

                    if data is None:
                        return

                    for attempt in range(MAX_RETRIES):
                        try:
                            await session.invoke(data, timeout=Session.MEDIA_TIMEOUT)
                            break
                        except StopTransmission:
                            raise
                        except (OSError, TimeoutError, RPCError, asyncio.TimeoutError) as e:
                            if attempt == MAX_RETRIES - 1:
                                log.exception(
                                    "Upload part failed after %d attempts",
                                    MAX_RETRIES,
                                )
                                raise
                            delay = min(2 ** attempt, 30)
                            err_str = str(e)
                            if "FLOOD_WAIT" in err_str or "FLOOD" in err_str:
                                for part in err_str.split():
                                    if part.isdigit():
                                        delay = min(int(part), 30)
                                        break
                            log.warning(
                                "Retrying upload part (attempt %d/%d): %s",
                                attempt + 1, MAX_RETRIES, err_str[:120],
                            )
                            await asyncio.sleep(delay)

            async def read_batch():
                batch_size = PART_SIZE * n_workers
                data = await self.loop.run_in_executor(
                    self.executor, fp.read, batch_size
                )
                return [data[i:i+PART_SIZE] for i in range(0, len(data), PART_SIZE)]

            part_size = PART_SIZE

            if isinstance(path, (str, PurePath)):
                fp = open(path, "rb", buffering=READ_BUFFER)
            elif isinstance(path, io.IOBase):
                fp = path
            else:
                raise ValueError(
                    "Invalid file. Expected a file path as string "
                    "or a binary (not text) file pointer"
                )

            file_name = getattr(fp, "name", "file.jpg")

            fp.seek(0, os.SEEK_END)
            file_size = fp.tell()
            fp.seek(0)

            if file_size == 0:
                raise ValueError("File size equals to 0 B")

            file_size_limit_mib = 4000 if self.me.is_premium else 2000

            if file_size > file_size_limit_mib * 1024 * 1024:
                raise ValueError(
                    f"Can't upload files bigger than {file_size_limit_mib} MiB"
                )

            file_total_parts = int(math.ceil(file_size / part_size))
            is_big = file_size > 10 * 1024 * 1024
            is_bot = self.me.is_bot if hasattr(self.me, 'is_bot') else False
            is_premium = self.me.is_premium if hasattr(self.me, 'is_premium') else False
            if is_bot:
                rate_limit = 40  # ~20 MiB/s
                pool_size = min(8, POOL_SIZE) if is_big else 1
            elif is_premium:
                rate_limit = 300
                pool_size = min(14, POOL_SIZE) if is_big else 1
            else:
                rate_limit = 50  # ~25 MiB/s
                pool_size = min(12, POOL_SIZE) if is_big else 1

            is_missing_part = file_id is not None
            file_id = file_id or self.rnd_id()
            md5_sum = md5() if not is_big and not is_missing_part else None

            dc_id = await self.storage.dc_id()
            pool = await self._get_media_session_pool(dc_id, pool_size)

            n_workers = len(pool) * 2
            queue = asyncio.Queue(n_workers * 4)
            workers = [
                self.loop.create_task(worker(pool[i % len(pool)]))
                for i in range(n_workers)
            ]
            next_batch_task = None
            _last_progress_time = 0.0
            _next_dispatch = 0.0
            _dispatch_interval = 1.0 / rate_limit
            _stalled_since = 0.0
            failed = False

            _progress_task = None
            if progress:
                async def _progress_reporter():
                    nonlocal _last_progress_time
                    try:
                        _prev_part = 0
                        while True:
                            await asyncio.sleep(0.5)
                            p = file_part
                            if p == 0 or p == _prev_part:
                                continue
                            _prev_part = p
                            now = time.monotonic()
                            if now - _last_progress_time >= PROGRESS_INTERVAL:
                                _last_progress_time = now
                                s = min(p * part_size, file_size)
                                try:
                                    if inspect.iscoroutinefunction(progress):
                                        await progress(s, file_size, *progress_args)
                                    else:
                                        await self.loop.run_in_executor(
                                            self.executor,
                                            functools.partial(progress, s, file_size, *progress_args),
                                        )
                                except Exception as e:
                                    log.warning(f"Progress callback error: {e}")
                    except asyncio.CancelledError:
                        pass
                _progress_task = asyncio.ensure_future(_progress_reporter())

            try:

                fp.seek(part_size * file_part)
                next_batch_task = self.loop.create_task(read_batch())

                while True:
                    chunks = await next_batch_task
                    next_batch_task = self.loop.create_task(read_batch())

                    if not chunks:
                        next_batch_task.cancel()
                        if not is_big and not is_missing_part:
                            md5_sum = md5_sum.hexdigest()
                        break

                    async def _check_workers():
                        for t in workers:
                            if t.done() and not t.cancelled():
                                exc = t.exception()
                                if exc is not None:
                                    raise exc

                    await _check_workers()

                    for chunk in chunks:
                        if is_big:
                            rpc = raw.functions.upload.SaveBigFilePart(
                                file_id=file_id,
                                file_part=file_part,
                                file_total_parts=file_total_parts,
                                bytes=chunk,
                            )
                        else:
                            rpc = raw.functions.upload.SaveFilePart(
                                file_id=file_id, file_part=file_part, bytes=chunk
                            )

                        _now = time.monotonic()
                        if _now < _next_dispatch:
                            await asyncio.sleep(_next_dispatch - _now)
                        _next_dispatch = max(time.monotonic(), _next_dispatch) + _dispatch_interval

                        while True:
                            try:
                                await asyncio.wait_for(queue.put(rpc), timeout=30)
                                _stalled_since = 0.0
                                break
                            except asyncio.TimeoutError:
                                await _check_workers()
                                if _stalled_since == 0.0:
                                    _stalled_since = time.monotonic()
                                elif time.monotonic() - _stalled_since > 180:
                                    raise TimeoutError("Upload timed out — workers may have stopped")
                                await asyncio.sleep(1)

                        if is_missing_part:
                            next_batch_task.cancel()
                            for _ in range(n_workers):
                                await queue.put(None)
                            results = await asyncio.gather(*workers, return_exceptions=True)
                            for r in results:
                                if isinstance(r, BaseException) and not isinstance(
                                    r, asyncio.CancelledError
                                ):
                                    raise r
                            return None

                        if not is_big and not is_missing_part:
                            md5_sum.update(chunk)

                        file_part += 1


            except (StopTransmission, asyncio.CancelledError):
                failed = True
                raise
            except Exception as e:
                failed = True
                log.exception(e)
                raise
            else:
                if is_big:
                    return raw.types.InputFileBig(
                        id=file_id,
                        parts=file_total_parts,
                        name=file_name,
                    )
                else:
                    return raw.types.InputFile(
                        id=file_id,
                        parts=file_total_parts,
                        name=file_name,
                        md5_checksum=md5_sum,
                    )
            finally:
                if _progress_task and not _progress_task.done():
                    _progress_task.cancel()
                if next_batch_task is not None and not next_batch_task.done():
                    next_batch_task.cancel()

                if failed:
                    for w in workers:
                        w.cancel()
                else:
                    for _ in workers:
                        await queue.put(None)

                await asyncio.gather(*workers, return_exceptions=True)

                if isinstance(path, (str, PurePath)):
                    fp.close()
