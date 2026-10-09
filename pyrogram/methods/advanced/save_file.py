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
import contextlib
import functools
import inspect
import io
import logging
import math
import os
import time
from hashlib import md5
from typing import Union, BinaryIO, Callable, Optional

import pyrogram
from pyrogram import StopTransmission
from pyrogram import raw
from pyrogram import utils
from pyrogram.errors import RPCError, Flood
from pyrogram.methods.rate_limiter import AdaptiveBucket
from pyrogram.session import Session

log = logging.getLogger(__name__)

PART_SIZE = 512 * 1024
POOL_SIZE = 20
MAX_RETRIES = 16
STALL_TIMEOUT = 900
READ_BUFFER = 4 * 1024 * 1024
MAX_BATCH = 4 * 1024 * 1024
PACER_BURST = 16


async def _stop_workers(queue: asyncio.Queue, workers: list) -> list:
    """Retire the upload workers and collect what they ended with.

    The sentinels are what the workers exit on, so the happy path must deliver
    one to each. But ``queue`` is bounded by the worker count, so once the
    workers are gone there is nobody to make room and an unconditional ``put``
    waits for a consumer that will never run - with ``save_file_semaphore``
    still held, which wedges every other upload on the client.
    """
    delivered = 0

    for _ in workers:
        if all(t.done() for t in workers):
            break

        try:
            await asyncio.wait_for(queue.put(None), Session.MEDIA_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            break

        delivered += 1

    if delivered < len(workers):
        for t in workers:
            if not t.done():
                t.cancel()

    return await asyncio.gather(*workers, return_exceptions=True)


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
        from pyrogram.client import ReadAhead

        async with self.save_file_semaphore:
            if path is None:
                return None

            async def worker(session):
                while True:
                    data = await queue.get()

                    if data is None:
                        return

                    try:
                        await _send_part(session, data)
                        _acked[0] += 1
                        _pacer.on_success()
                    finally:
                        data = None
                        budget.release()

            async def _send_part(session, data):
                for attempt in range(MAX_RETRIES):
                    try:
                        if not await session.invoke(
                            data, timeout=Session.MEDIA_WAIT_TIMEOUT, sleep_threshold=0
                        ):
                            raise OSError("part not accepted by the server")
                        break
                    except StopTransmission:
                        raise
                    except (OSError, TimeoutError, RPCError, asyncio.TimeoutError) as e:
                        if (
                            isinstance(e, RPCError)
                            and not isinstance(e, Flood)
                            and not 500 <= (e.CODE or 0) < 600
                        ):
                            raise
                        if attempt == MAX_RETRIES - 1:
                            log.exception(
                                "Upload part failed after %d attempts",
                                MAX_RETRIES,
                            )
                            raise
                        delay = min(2 ** attempt, 30)
                        err_str = str(e)
                        if isinstance(e, Flood):
                            if isinstance(e.value, int):
                                delay = min(e.value, 300)
                            _pacer.on_flood()
                        log.warning(
                            "Retrying upload part (attempt %d/%d): %s",
                            attempt + 1, MAX_RETRIES, err_str[:120],
                        )
                        await asyncio.sleep(delay)

            async def read_batch():
                batch_size = min(PART_SIZE * n_workers, MAX_BATCH)
                return await self.loop.run_in_executor(
                    self.executor, fp.read, batch_size
                )

            part_size = PART_SIZE

            if isinstance(path, (str, os.PathLike)):
                fp = open(path, "rb", buffering=READ_BUFFER)
            elif isinstance(path, io.IOBase) and not isinstance(path, io.TextIOBase):
                fp = path
            else:
                raise ValueError(
                    "Invalid file. Expected a file path as string "
                    "or a binary (not text) file pointer"
                )

            file_name = utils.get_file_name(fp, fallback="file.jpg")

            fp.seek(0, os.SEEK_END)
            file_size = fp.tell()
            fp.seek(0)

            if file_size == 0:
                raise ValueError("File size equals to 0 B")

            is_bot = self.me.is_bot if hasattr(self.me, 'is_bot') else False
            is_premium = self.me.is_premium if hasattr(self.me, 'is_premium') else False

            file_size_limit_mib = 4000 if is_premium else 2000

            if file_size > file_size_limit_mib * 1024 * 1024:
                raise ValueError(
                    f"Can't upload files bigger than {file_size_limit_mib} MiB"
                )

            file_total_parts = int(math.ceil(file_size / part_size))
            is_big = file_size > 10 * 1024 * 1024
            pool_cap = max(1, math.ceil((file_total_parts - file_part) / 2))
            if is_bot:
                rate_limit = int(os.environ.get("WZGRAM_UPLOAD_RATE_BOT", 32))
                pool_size = min(int(os.environ.get("WZGRAM_UPLOAD_POOL_BOT", 8)), POOL_SIZE, pool_cap)
            elif is_premium:
                rate_limit = int(os.environ.get("WZGRAM_UPLOAD_RATE_PREMIUM", 300))
                pool_size = min(int(os.environ.get("WZGRAM_UPLOAD_POOL_PREMIUM", 14)), POOL_SIZE, pool_cap)
            else:
                rate_limit = int(os.environ.get("WZGRAM_UPLOAD_RATE_USER", 32))
                pool_size = min(int(os.environ.get("WZGRAM_UPLOAD_POOL_USER", 12)), POOL_SIZE, pool_cap)

            is_missing_part = file_id is not None
            file_id = file_id or self.rnd_id()
            md5_sum = md5() if not is_big and not is_missing_part else None

            dc_id = await self.storage.dc_id()
            pool_lease = contextlib.AsyncExitStack()

            try:
                pool_task = await pool_lease.enter_async_context(
                    self._media_pool(dc_id, pool_size)
                )
                pool = await pool_task

                if not pool:
                    raise OSError(f"No media session available for DC {dc_id}")

                _acked = [0]

                n_workers = len(pool) * 2
                queue = asyncio.Queue(n_workers)
                budget = ReadAhead(self.read_ahead_slots)
                workers = [
                    self.loop.create_task(worker(pool[i % len(pool)]))
                    for i in range(n_workers)
                ]
            except BaseException:
                await pool_lease.aclose()
                raise

            next_batch_task = None
            _pacer = AdaptiveBucket(
                rate=rate_limit, ceiling=max(rate_limit, 300), burst=PACER_BURST, step=1.0,
                backoff=1.0 if is_premium and not is_bot else 0.85,
            )
            _stalled_since = 0.0
            _last_reported = -1

            async def _report(parts: int) -> None:
                nonlocal _last_reported

                if not progress or parts == _last_reported:
                    return

                _last_reported = parts

                func = functools.partial(
                    progress, min(parts * part_size, file_size), file_size, *progress_args
                )

                try:
                    if inspect.iscoroutinefunction(progress):
                        await func()
                    else:
                        await self.loop.run_in_executor(self.executor, func)
                except StopTransmission:
                    raise
                except Exception as e:
                    log.warning(f"Upload progress callback error: {e}")

            try:
                fp.seek(part_size * file_part)
                next_batch_task = self.loop.create_task(read_batch())

                while True:
                    batch = await next_batch_task
                    next_batch_task = self.loop.create_task(read_batch())

                    if not batch:
                        next_batch_task.cancel()
                        if not is_big and not is_missing_part:
                            md5_sum = md5_sum.hexdigest()
                        break

                    async def _check_workers():
                        for t in workers:
                            # asking a cancelled task for its exception re-raises
                            if t.done() and not t.cancelled():
                                exc = t.exception()
                                if exc is not None:
                                    raise exc

                    await _check_workers()

                    for start in range(0, len(batch), part_size):
                        chunk = batch[start:start + part_size]

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

                        await _pacer.acquire()

                        await budget.acquire()

                        while True:
                            try:
                                await asyncio.wait_for(queue.put(rpc), timeout=30)
                                _stalled_since = 0.0
                                break
                            except asyncio.TimeoutError:
                                await _check_workers()
                                _now = time.monotonic()
                                if _stalled_since == 0.0:
                                    _stalled_since = _now
                                    log.warning(
                                        "Upload queue full: workers throttled (flood/connection churn), "
                                        "waiting up to %ss",
                                        STALL_TIMEOUT,
                                    )
                                elif _now - _stalled_since > STALL_TIMEOUT:
                                    raise TimeoutError(
                                        "Upload stalled: no part completed for "
                                        f"{STALL_TIMEOUT}s while workers are alive "
                                        "(flood or network throttling)"
                                    )
                                await asyncio.sleep(1)

                        if is_missing_part:
                            next_batch_task.cancel()
                            results = await _stop_workers(queue, workers)
                            for r in results:
                                if isinstance(r, BaseException) and not isinstance(
                                    r, asyncio.CancelledError
                                ):
                                    raise r
                            return None

                        if not is_big and not is_missing_part:
                            md5_sum.update(chunk)

                        rpc = None
                        chunk = None
                        file_part += 1

                        await _report(_acked[0])

                    batch = None

            except StopTransmission:
                raise
            except Exception as e:
                log.exception(e)
                raise
            else:
                results = await _stop_workers(queue, workers)

                for r in results:
                    if isinstance(r, BaseException) and not isinstance(
                        r, asyncio.CancelledError
                    ):
                        raise r

                await _report(file_total_parts)

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
                if next_batch_task is not None and not next_batch_task.done():
                    next_batch_task.cancel()

                await _stop_workers(queue, workers)
                budget.release_all()
                await pool_lease.aclose()

                if isinstance(path, (str, os.PathLike)):
                    fp.close()
