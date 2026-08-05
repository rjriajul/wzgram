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
import ipaddress
import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import socks

from pyrogram.crypto.executor import get_crypto_executor

log = logging.getLogger(__name__)


class TCP:
    TIMEOUT = int(os.environ.get("WZGRAM_TCP_TIMEOUT", 10))
    CONNECT_TIMEOUT = int(os.environ.get("WZGRAM_TCP_CONNECT_TIMEOUT", 600))

    def __init__(self, ipv6: bool, proxy: dict, crypto_executor: Optional[ThreadPoolExecutor] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.socket = None

        self.reader = None
        self.writer = None

        self.lock = asyncio.Lock()
        if loop:
            self.loop = loop
        else:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = asyncio.get_event_loop_policy().get_event_loop()

        self.proxy = proxy

        self.crypto_executor = crypto_executor or get_crypto_executor()

        if proxy:
            hostname = proxy.get("hostname")

            try:
                ip_address = ipaddress.ip_address(hostname)
            except ValueError:
                self.socket = socks.socksocket(socket.AF_INET)
            else:
                if isinstance(ip_address, ipaddress.IPv6Address):
                    self.socket = socks.socksocket(socket.AF_INET6)
                else:
                    self.socket = socks.socksocket(socket.AF_INET)

            proxy_type_str = (proxy.get("scheme") or "socks5").upper()
            self.socket.set_proxy(
                proxy_type=getattr(socks, proxy_type_str, socks.SOCKS5),
                addr=hostname,
                port=proxy.get("port", None),
                username=proxy.get("username", None),
                password=proxy.get("password", None)
            )

            self.socket.settimeout(TCP.CONNECT_TIMEOUT)

            log.info("Using proxy %s", hostname)
        else:
            self.socket = socket.socket(
                socket.AF_INET6 if ipv6
                else socket.AF_INET
            )

            self.socket.setblocking(False)

    async def connect(self, address: tuple):
        if self.proxy:
            try:
                await asyncio.wait_for(
                    self.loop.run_in_executor(None, self.socket.connect, address),
                    TCP.CONNECT_TIMEOUT
                )
            except asyncio.TimeoutError:
                raise TimeoutError("Proxy connection timed out")
        else:
            try:
                await asyncio.wait_for(self.loop.sock_connect(self.socket, address), TCP.CONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                raise TimeoutError("Connection timed out")

        self.reader, self.writer = await asyncio.open_connection(sock=self.socket)

        try:
            sock = self.writer.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except OSError:
            pass

    async def close(self):
        try:
            if self.writer is not None:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), TCP.TIMEOUT)
        except Exception as e:
            log.info("Close exception: %s %s", type(e).__name__, e)

    async def send(self, data: bytes):
        async with self.lock:
            try:
                if self.writer is not None:
                    self.writer.write(data)
                    await self.writer.drain()
            except Exception as e:
                log.info("Send exception: %s %s", type(e).__name__, e)
                raise OSError(e)

    async def recv(self, length: int = 0):
        data = b""

        while len(data) < length:
            try:
                chunk = await asyncio.wait_for(
                    self.reader.read(length - len(data)),
                    TCP.TIMEOUT
                )
            except asyncio.TimeoutError:
                raise TimeoutError("Socket read timed out")
            except OSError:
                return None
            else:
                if chunk:
                    data += chunk
                else:
                    return None

        return data
