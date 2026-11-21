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

# ***************************
# GENERATED FILE - DO NOT EDIT
# Source: tl:messages.sendScheduledMessages
# ***************************

from typing import Union, List, Iterable

import pyrogram
from pyrogram import raw
from pyrogram import types


class SendScheduledMessages:
    async def send_scheduled_messages(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        id: Union[int, Iterable[int]],
    ) -> Union["types.Message", List["types.Message"]]:
        """Send scheduled messages immediately.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            id (``int`` | Iterable of ``int``):
                A scheduled message identifier or a list of scheduled message identifiers to send now.

        Returns:
            :obj:`~pyrogram.types.Message` | List of :obj:`~pyrogram.types.Message`: In case *id* was not
            a list, a single message is returned, otherwise a list of messages is returned.

        Example:
            .. code-block:: python

                await app.send_scheduled_messages(chat_id, message_id)
                await app.send_scheduled_messages(chat_id, [message_id1, message_id2])
        """
        is_iterable = not isinstance(id, int)
        ids = list(id) if is_iterable else [id]

        r = await self.invoke(
            raw.functions.messages.SendScheduledMessages(
                peer=await self.resolve_peer(chat_id),
                id=ids,
            )
        )

        users = {i.id: i for i in r.users}
        chats = {i.id: i for i in r.chats}
        messages = types.List()

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateNewMessage,
                              raw.types.UpdateNewChannelMessage)):
                messages.append(await types.Message._parse(self, i.message, users, chats))

        return messages if is_iterable else messages[0] if messages else None
