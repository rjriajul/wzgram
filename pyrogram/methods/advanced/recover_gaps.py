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
from typing import Iterable, Optional, Tuple, Union

import pyrogram
from pyrogram import raw
from pyrogram.errors import ChannelInvalid, ChannelPrivate, PeerIdInvalid, PersistentTimestampInvalid, PersistentTimestampOutdated
from pyrogram.utils import ZERO_CHANNEL_ID

log = logging.getLogger(__name__)


class RecoverGaps:
    MAX_STALE_TIMESTAMP_RETRIES = 3

    async def recover_gaps(
        self: "pyrogram.Client",
        ids: Optional[Union[int, Iterable[int]]] = None
    ) -> Tuple[int, int]:
        """Restores updates for the time while the client was offline.

        .. note::

            To use this method, you must set the ``Client.skip_updates`` and ``Client.in_memory`` parameter to False, otherwise updates state saving and recovery will not work.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            ids (``int`` | Iterable of ``int``, *optional*):
                Identifiers of the chats to recover, 0 for private chats and other updates.
                By default, every known chat is recovered.

        Returns:
            ``tuple``: The number of messages and updates recovered is returned.
        """
        message_updates_counter = 0
        other_updates_counter = 0

        if self.skip_updates:
            log.debug("Recover gaps disabled in client params. Skipping recovery")
            return (message_updates_counter, other_updates_counter)

        states = await self.storage.update_state()

        if ids is not None:
            wanted = {ids} if isinstance(ids, int) else set(ids)
            states = [state for state in states or () if state[0] in wanted]

        if not states:
            log.info("No states found, skipping recovery")
            return (message_updates_counter, other_updates_counter)

        log.info("Started gaps recovering...")

        for local_state in states:
            id, local_pts, local_qts, local_date, local_seq = local_state

            if local_pts is None and (id != 0 or local_qts is None):
                continue

            stale_attempts = 0
            unusable = False
            failed = False

            while True:
                try:
                    if local_pts is None:
                        state = await self.invoke(raw.functions.updates.GetState())
                        local_pts, local_date, local_seq = state.pts, state.date, state.seq

                    request = (local_pts, local_qts)

                    diff = await self.invoke(
                        raw.functions.updates.GetChannelDifference(
                            channel=await self.resolve_peer(id),
                            filter=raw.types.ChannelMessagesFilterEmpty(),
                            pts=local_pts,
                            limit=10000,
                            force=False
                        ) if id < ZERO_CHANNEL_ID else
                        raw.functions.updates.GetDifference(
                            pts=local_pts,
                            date=local_date,
                            qts=local_qts or 0
                        )
                    )
                except (ChannelPrivate, ChannelInvalid, PeerIdInvalid):
                    unusable = True
                    break
                except (PersistentTimestampOutdated, PersistentTimestampInvalid) as e:
                    stale_attempts += 1

                    if stale_attempts >= RecoverGaps.MAX_STALE_TIMESTAMP_RETRIES:
                        log.info(
                            "Dropping the stored state of %s: %s after %s attempts",
                            id, e.ID, stale_attempts
                        )
                        unusable = True
                        break

                    await asyncio.sleep(stale_attempts)
                    continue
                except Exception:
                    # this runs inside dispatcher.start(): one peer that cannot be
                    # fetched must not stop every peer after it, nor the client
                    # from coming up at all. The state is kept, so the next start
                    # tries again.
                    log.exception("Gap recovery failed for %s", id)
                    failed = True
                    break

                if isinstance(diff, raw.types.updates.DifferenceEmpty):
                    await self._save_update_state(
                        (
                            id,
                            local_pts,
                            local_qts,
                            diff.date,
                            diff.seq
                        )
                    )
                    break
                elif isinstance(diff, raw.types.updates.DifferenceTooLong):
                    local_pts = diff.pts
                    await self._save_update_state(
                        (
                            id,
                            local_pts,
                            local_qts,
                            local_date,
                            local_seq
                        )
                    )
                    continue
                elif isinstance(diff, raw.types.updates.Difference):
                    local_pts = diff.state.pts
                    local_qts = diff.state.qts
                    local_date = diff.state.date
                    local_seq = diff.state.seq
                elif isinstance(diff, raw.types.updates.DifferenceSlice):
                    local_pts = diff.intermediate_state.pts
                    local_qts = diff.intermediate_state.qts
                    local_date = diff.intermediate_state.date
                    local_seq = diff.intermediate_state.seq
                elif isinstance(diff, raw.types.updates.ChannelDifferenceEmpty):
                    await self._save_update_state(
                        (
                            id,
                            diff.pts,
                            local_qts,
                            local_date,
                            local_seq
                        )
                    )
                    break
                elif isinstance(diff, raw.types.updates.ChannelDifferenceTooLong):
                    local_pts = diff.dialog.pts
                    await self._save_update_state(
                        (
                            id,
                            local_pts,
                            local_qts,
                            local_date,
                            local_seq
                        )
                    )
                    continue
                elif isinstance(diff, raw.types.updates.ChannelDifference):
                    local_pts = diff.pts

                users = {i.id: i for i in diff.users}
                chats = {i.id: i for i in diff.chats}

                for message in diff.new_messages:
                    message_updates_counter += 1
                    await self.dispatcher.enqueue_update(
                        raw.types.UpdateNewMessage(
                            message=message,
                            pts=local_pts,
                            pts_count=-1
                        ),
                        users,
                        chats
                    )

                for update in diff.other_updates:
                    other_updates_counter += 1
                    await self.dispatcher.enqueue_update(update, users, chats)

                if isinstance(diff, raw.types.updates.Difference):
                    break

                if isinstance(diff, raw.types.updates.ChannelDifference) and diff.final:
                    break

                if (local_pts, local_qts) == request:
                    break

            if failed:
                continue

            if unusable:
                await self._save_update_state(id)
                continue

            await self._save_update_state(
                (
                    id,
                    local_pts,
                    local_qts,
                    local_date,
                    local_seq
                )
            )

        log.info("Recovered %s messages and %s updates", message_updates_counter, other_updates_counter)
        return (message_updates_counter, other_updates_counter)

