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
import bisect
import logging
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1
from io import BytesIO
from typing import Optional

import warpcrypto

import pyrogram
from pyrogram import raw
from pyrogram.connection import Connection
from pyrogram.crypto.executor import get_crypto_executor
from pyrogram.errors import (
    RPCError, InternalServerError, AuthKeyDuplicated, FloodWait, FloodPremiumWait, ServiceUnavailable,
    BadMsgNotification, SecurityCheckMismatch
)
from pyrogram.raw.all import layer
from pyrogram.raw.core import TLObject, Message, MsgContainer, Int, FutureSalts
from .internals import MsgId, MsgFactory

log = logging.getLogger(__name__)


class Result:
    def __init__(self):
        self.value = None
        self.event = asyncio.Event()


class Session:
    START_TIMEOUT = 2
    WAIT_TIMEOUT = 15
    SLEEP_THRESHOLD = 10
    MAX_RETRIES = 10
    ACKS_THRESHOLD = 10
    PING_INTERVAL = 5
    STORED_MSG_IDS_MAX_SIZE = 1000 * 2

    TRANSPORT_ERRORS = {
        404: "auth key not found",
        429: "transport flood",
        444: "invalid DC"
    }

    def __init__(
        self,
        client: "pyrogram.Client",
        dc_id: int,
        auth_key: bytes,
        test_mode: bool,
        is_media: bool = False,
        is_cdn: bool = False,
        server_address: Optional[str] = None,
        port: Optional[int] = None,
        crypto_executor: Optional[ThreadPoolExecutor] = None
    ):
        self.client = client
        self.dc_id = dc_id
        self.auth_key = auth_key
        self.test_mode = test_mode
        self.is_media = is_media
        self.is_cdn = is_cdn
        self.server_address = server_address
        self.port = port
        if crypto_executor is None:
            self.crypto_executor = get_crypto_executor()
        else:
            self.crypto_executor = crypto_executor

        self.connection = None

        self.auth_key_id = sha1(auth_key).digest()[-8:]

        self.session_id = os.urandom(8)
        self.msg_factory = MsgFactory()

        self.salt = 0

        self.pending_acks = set()

        self.results = {}

        self.stored_msg_ids = []

        self._handler_lock = asyncio.Lock()
        self._packet_tasks = set()
        self._update_semaphore = asyncio.Semaphore(32)

        self.ping_task = None
        self.ping_task_event = asyncio.Event()

        self.recv_task = None

        self._restart_lock = asyncio.Lock()
        self._restart_done = asyncio.Event()
        self._restart_done.set()

        self.is_started = asyncio.Event()
        self._stopping = False

        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.get_event_loop_policy().get_event_loop()

        self.flood_history = deque(maxlen=50)
        self._dynamic_backoff = float(Session.SLEEP_THRESHOLD)
        self._last_flood_decay = 0.0

    async def start(self):
        self._stopping = False
        attempt = 0
        while True:
            attempt += 1
            self.connection = Connection(
                self.dc_id,
                self.test_mode,
                self.client.ipv6,
                self.client.proxy,
                self.is_media,
                crypto_executor=self.crypto_executor,
                loop=self.loop,
                server_address=self.server_address,
                port=self.port,
            )

            try:
                await self.connection.connect()

                self.recv_task = self.loop.create_task(self.recv_worker())

                await self.send(raw.functions.Ping(ping_id=0), timeout=self.START_TIMEOUT)

                if not self.is_cdn:
                    await self.send(
                        raw.functions.InvokeWithLayer(
                            layer=layer,
                            query=raw.functions.InitConnection(
                                api_id=await self.client.storage.api_id(),
                                app_version=self.client.app_version,
                                device_model=self.client.device_model,
                                system_version=self.client.system_version,
                                system_lang_code=self.client.lang_code,
                                lang_code=self.client.lang_code,
                                lang_pack="",
                                query=raw.functions.help.GetConfig(),
                            )
                        ),
                        timeout=self.START_TIMEOUT
                    )

                self.ping_task = self.loop.create_task(self.ping_worker())

                log.info("Session initialized: Layer %s", layer)
                log.info("Device: %s - %s", self.client.device_model, self.client.app_version)
                log.info("System: %s (%s)", self.client.system_version, self.client.lang_code)
            except AuthKeyDuplicated as e:
                await self.stop()
                raise e
            except (OSError, RPCError):
                await self.stop()

                # Exponential backoff (capped) so a flaky network doesn't make
                # the session spin in a tight connect/retry loop. Reconnects are
                # especially expensive on low-memory hosts, so slow the loop
                # down instead of thrashing.
                backoff = min(2 ** (attempt - 1), 30)
                log.debug(
                    "Session start attempt %d failed, retrying in %ss",
                    attempt, backoff
                )
                await asyncio.sleep(backoff)
            except (Exception, asyncio.CancelledError) as e:
                await self.stop()
                raise e
            else:
                break

        self.is_started.set()

        log.info("Session started")

    async def stop(self):
        self.is_started.clear()
        self._stopping = True

        self.stored_msg_ids.clear()

        self.ping_task_event.set()

        if self.ping_task is not None:
            try:
                await self.ping_task
            except (Exception, asyncio.CancelledError):
                pass

        self.ping_task_event.clear()

        if self.recv_task:
            self.recv_task.cancel()
            try:
                await self.recv_task
            except (Exception, asyncio.CancelledError):
                pass

        for task in list(self._packet_tasks):
            task.cancel()
        if self._packet_tasks:
            await asyncio.gather(*self._packet_tasks, return_exceptions=True)
            self._packet_tasks.clear()

        if self.connection:
            await self.connection.close()

        # Wake every in-flight request so it re-checks state (and retries via
        # invoke) instead of hanging until its own timeout.
        for result in self.results.values():
            result.event.set()

        if not self.is_media and callable(self.client.disconnect_handler):
            try:
                await self.client.disconnect_handler(self.client)
            except (Exception, asyncio.CancelledError) as e:
                log.exception(e)

        log.info("Session stopped")

    async def restart(self):
        if self._restart_lock.locked():
            await self._restart_done.wait()
            return
        async with self._restart_lock:
            self._restart_done.clear()
            try:
                await self.stop()
                if self.client.storage.conn is None:
                    await self.client.storage.open()
                await self.start()
            finally:
                self._restart_done.set()

    async def handle_packet(self, packet):
        try:
            msg_id, seq_no, length, body_bytes, total_len = await self.loop.run_in_executor(
                self.connection.protocol.crypto_executor,
                warpcrypto.unpack_message,
                packet,
                self.session_id,
                self.auth_key,
                self.auth_key_id
            )
        except Exception as e:
            # A corrupt/undecryptable frame (or a protocol torn down by a
            # concurrent restart) must not kill the background task.
            log.warning("Failed to decrypt packet: %s %s", type(e).__name__, e)
            return

        # https://core.telegram.org/mtproto/security_guidelines#checking-message-length
        padding_len = total_len - 16 - length
        SecurityCheckMismatch.check(12 <= padding_len <= 1024, "12 <= len(padding) <= 1024")
        SecurityCheckMismatch.check(total_len % 4 == 0, "len(data) % 4 == 0")

        # https://core.telegram.org/mtproto/security_guidelines#checking-msg-id
        SecurityCheckMismatch.check(msg_id % 2 != 0, "message.msg_id % 2 != 0")

        body = TLObject.read(BytesIO(body_bytes))
        message = Message(body, msg_id, seq_no, length)

        messages = (
            message.body.messages
            if isinstance(message.body, MsgContainer)
            else [message]
        )

        log.debug("Received: %s", message)

        for msg in messages:
            if msg.seq_no % 2 != 0:
                async with self._handler_lock:
                    if msg.msg_id not in self.pending_acks:
                        self.pending_acks.add(msg.msg_id)

            try:
                if len(self.stored_msg_ids) > Session.STORED_MSG_IDS_MAX_SIZE:
                    del self.stored_msg_ids[:Session.STORED_MSG_IDS_MAX_SIZE // 2]

                if self.stored_msg_ids:
                    if msg.msg_id < self.stored_msg_ids[0]:
                        raise SecurityCheckMismatch("The msg_id is lower than all the stored values")

                    if msg.msg_id in self.stored_msg_ids:
                        raise SecurityCheckMismatch("The msg_id is equal to any of the stored values")

                    time_diff = (msg.msg_id - MsgId()) / 2 ** 32

                    if time_diff > 30:
                        raise SecurityCheckMismatch("The msg_id belongs to over 30 seconds in the future. "
                                                    "Most likely the client time has to be synchronized.")

                    if time_diff < -300:
                        raise SecurityCheckMismatch("The msg_id belongs to over 300 seconds in the past. "
                                                    "Most likely the client time has to be synchronized.")
            except SecurityCheckMismatch as e:
                log.info("Discarding packet: %s", e)
                await self.connection.close()
                return
            else:
                async with self._handler_lock:
                    bisect.insort(self.stored_msg_ids, msg.msg_id)

            if isinstance(msg.body, (raw.types.MsgDetailedInfo, raw.types.MsgNewDetailedInfo)):
                self.pending_acks.add(msg.body.answer_msg_id)
                continue

            if isinstance(msg.body, raw.types.NewSessionCreated):
                continue

            msg_id = None

            if isinstance(msg.body, (raw.types.BadMsgNotification, raw.types.BadServerSalt)):
                msg_id = msg.body.bad_msg_id
            elif isinstance(msg.body, (FutureSalts, raw.types.RpcResult)):
                msg_id = msg.body.req_msg_id
            elif isinstance(msg.body, raw.types.Pong):
                msg_id = msg.body.msg_id
            else:
                if self.client is not None:
                    self.loop.create_task(self._run_update(msg.body))

            if msg_id in self.results:
                self.results[msg_id].value = getattr(msg.body, "result", msg.body)
                self.results[msg_id].event.set()

        async with self._handler_lock:
            ack_ids = None
            if len(self.pending_acks) >= self.ACKS_THRESHOLD:
                ack_ids = list(self.pending_acks)
                self.pending_acks.clear()

        if ack_ids:
            log.debug("Sending %s acks", len(ack_ids))

            try:
                await self.send(raw.types.MsgsAck(msg_ids=ack_ids), False)
            except OSError:
                pass

    async def ping_worker(self):
        log.info("PingTask started")

        while True:
            try:
                await asyncio.wait_for(self.ping_task_event.wait(), self.PING_INTERVAL)
            except asyncio.TimeoutError:
                pass
            else:
                break

            try:
                await self.send(
                    raw.functions.PingDelayDisconnect(
                        ping_id=0, disconnect_delay=self.WAIT_TIMEOUT + 10
                    ), False
                )
            except (OSError, TimeoutError, RPCError):
                pass

        log.info("PingTask stopped")

    async def _run_update(self, body):
        async with self._update_semaphore:
            await self.client.handle_updates(body)

    async def _handle_packet_wrapper(self, packet):
        task = asyncio.current_task()
        self._packet_tasks.add(task)
        try:
            await self.handle_packet(packet)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Error handling packet")
        finally:
            self._packet_tasks.discard(task)

    async def recv_worker(self):
        log.info("NetworkTask started")

        while True:
            try:
                packet = await self.connection.recv()
            except TimeoutError:
                log.debug("Socket read timed out, continuing")
                continue
            except Exception:
                log.exception("Error receiving packet")
                if self.is_started.is_set():
                    await self._safe_restart()
                break

            if packet is None or len(packet) == 4:
                if packet:
                    error_code = -Int.read(BytesIO(packet))

                    log.warning(
                        "Server sent transport error: %s (%s)",
                        error_code, Session.TRANSPORT_ERRORS.get(error_code, "unknown error")
                    )

                if self.is_started.is_set():
                    await self._safe_restart()

                break

            if not self._stopping:
                self.loop.create_task(self._handle_packet_wrapper(packet))

        log.info("NetworkTask stopped")

    async def _safe_restart(self):
        try:
            await self.restart()
        except (Exception, asyncio.CancelledError) as e:
            log.error("Session restart failed: %s", e)

    async def send(self, data: TLObject, wait_response: bool = True, timeout: float = WAIT_TIMEOUT,
                   retry: int = 0):
        if self.connection is None or self.connection.protocol is None:
            raise OSError("Connection is not established")

        message = self.msg_factory(data)
        msg_id = message.msg_id

        if wait_response:
            self.results[msg_id] = Result()

        log.debug("Sent: %s", message)

        try:
            payload = await self.loop.run_in_executor(
                self.connection.protocol.crypto_executor,
                warpcrypto.pack_message,
                message.msg_id,
                message.seq_no,
                message.body.write(),
                self.salt,
                self.session_id,
                self.auth_key,
                self.auth_key_id
            )
        except Exception:
            if wait_response:
                self.results.pop(msg_id, None)
            raise

        try:
            await asyncio.wait_for(self.connection.send(payload), timeout=timeout or self.WAIT_TIMEOUT)
        except OSError as e:
            self.results.pop(msg_id, None)
            raise e

        if wait_response:
            try:
                await asyncio.wait_for(self.results[msg_id].event.wait(), timeout)
            except asyncio.TimeoutError:
                pass
            finally:
                # Always release the pending request so a cancelled caller
                # doesn't leak an entry into self.results.
                result = self.results.pop(msg_id).value

            if result is None:
                raise TimeoutError("Request timed out")

            if isinstance(result, raw.types.RpcError):
                if isinstance(data, (raw.functions.InvokeWithoutUpdates, raw.functions.InvokeWithTakeout)):
                    data = data.query

                RPCError.raise_it(result, type(data))

            if isinstance(result, raw.types.BadMsgNotification):
                if retry > 1:
                    raise BadMsgNotification(result.error_code)
                await self._handle_bad_notification()
                return await self.send(data, wait_response, timeout, retry + 1)

            if isinstance(result, raw.types.BadServerSalt):
                if retry > 3:
                    raise BadMsgNotification(result.error_code)
                self.salt = result.new_server_salt
                return await self.send(data, wait_response, timeout, retry + 1)

            return result

    async def _handle_bad_notification(self):
        async with self._handler_lock:
            if not self.stored_msg_ids:
                return
            new_msg_id = MsgId()
            if self.stored_msg_ids[-1] >= new_msg_id:
                new_msg_id = self.stored_msg_ids[-1] + 4
                log.debug(
                    "Changing msg_id old=%s new=%s",
                    self.stored_msg_ids[-1],
                    new_msg_id,
                )
            self.stored_msg_ids[-1] = new_msg_id

    async def invoke(
        self,
        query: TLObject,
        retries: int = MAX_RETRIES,
        timeout: float = WAIT_TIMEOUT,
        sleep_threshold: float = SLEEP_THRESHOLD
    ):
        while retries > 0:
            if not self.is_started.is_set():
                try:
                    await asyncio.wait_for(self.is_started.wait(), self.WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    retries -= 1
                    if retries == 0:
                        raise TimeoutError("Session failed to start")
                    continue

            if isinstance(query, (raw.functions.InvokeWithoutUpdates, raw.functions.InvokeWithTakeout)):
                inner_query = query.query
            else:
                inner_query = query

            query_name = ".".join(inner_query.QUALNAME.split(".")[1:])

            try:
                return await self.send(query, timeout=timeout)
            except (FloodWait, FloodPremiumWait) as e:
                amount = e.value

                if amount > sleep_threshold >= 0:
                    effective = max(sleep_threshold, self._dynamic_backoff)
                    if amount > effective:
                        raise

                self.flood_history.append((amount, time.monotonic()))
                now = time.monotonic()
                if now - self._last_flood_decay > 60:
                    cutoff = now - 60
                    recent = sum(1 for a, t in self.flood_history if a > 1 and t > cutoff)
                    if recent >= 5:
                        self._dynamic_backoff = min(self._dynamic_backoff * 1.5, 60.0)
                    elif recent == 0:
                        self._dynamic_backoff = max(float(Session.SLEEP_THRESHOLD), self._dynamic_backoff * 0.9)
                    self._last_flood_decay = now

                log.warning('[%s] Waiting for %s seconds before continuing (required by "%s")',
                            self.client.name, amount, query_name)

                await asyncio.sleep(amount)
            except (OSError, InternalServerError, ServiceUnavailable, TimeoutError) as e:
                retries -= 1
                if retries == 0:
                    raise

                (log.warning if retries < 2 else log.info)(
                    '[%s] Retrying "%s" due to: %s',
                    Session.MAX_RETRIES - retries,
                    query_name, str(e) or repr(e)
                )

                if isinstance(e, (OSError, TimeoutError)):
                    await self.restart()
                else:
                    await asyncio.sleep(1)

        raise TimeoutError("Exceeded maximum number of retries")
