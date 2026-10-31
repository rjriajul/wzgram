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
import logging

import pyrogram

log = logging.getLogger(__name__)


class Initialize:
    async def initialize(
        self: "pyrogram.Client",
    ):
        """Initialize the client by starting up workers.

        This method will start updates and download workers.
        It will also load plugins and start the internal dispatcher.

        Returns:
            ``None``: The workers are running when it returns.

        Raises:
            ConnectionError: In case you try to initialize a disconnected client or in case you try to initialize an
                already initialized client.
        """
        if not self.is_connected:
            raise ConnectionError("Can't initialize a disconnected client")

        if self.is_initialized:
            raise ConnectionError("Client is already initialized")

        self.listeners.reopen()

        if self.rate_limiter is not None:
            self.rate_limiter.reopen()

        self.load_plugins()

        try:
            await self.dispatcher.start()

            if not self.no_updates:
                self.updates_watchdog_task = asyncio.create_task(self.updates_watchdog())
            self.media_pool_reaper_task = asyncio.create_task(self.media_pool_reaper())
        except BaseException:
            # is_initialized is still False, so terminate() would refuse to run and
            # the handler workers would sit on the update queue for the life of the
            # process. Whatever got started here has to be taken back down.
            for name in ("updates_watchdog_task", "media_pool_reaper_task"):
                task = getattr(self, name)

                if task is not None:
                    task.cancel()

                    try:
                        await task
                    except (Exception, asyncio.CancelledError):
                        pass

                    setattr(self, name, None)

            try:
                await self.dispatcher.stop()
            except Exception:
                log.exception("Error stopping the dispatcher after a failed initialize")

            raise

        self.is_initialized = True
