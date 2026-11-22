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

from typing import Optional, Union

import pyrogram
from pyrogram import raw, types
from ..object import Object
from ..update import Update
from .widget_query import _decode


class SharedWidgetQuery(Object, Update):
    """An incoming query from a forwarded message with a shared widget created by the bot.
    Use :meth:`~pyrogram.Client.answer_widget_query` to answer the query.

    Parameters:
        id (``str``):
            Unique identifier for this query.

        from_user (:obj:`~pyrogram.types.User`):
            Sender.

        type (:obj:`~pyrogram.types.WidgetQueryType`):
            Type of the query.

        data (``str`` | ``bytes``):
            Data of the query, 1-64 bytes.

        widget_id (``str``):
            Unique identifier of the shared widget, which sent the query.
    """

    def __init__(
        self,
        *,
        client: "pyrogram.Client" = None,
        id: str,
        from_user: "types.User",
        type: "types.WidgetQueryType",
        data: Union[str, bytes],
        widget_id: str,
    ):
        super().__init__(client)

        self.id = id
        self.from_user = from_user
        self.type = type
        self.data = data
        self.widget_id = widget_id

    @staticmethod
    async def _parse(
        client: "pyrogram.Client",
        update: "raw.types.UpdateBotWidgetCopyQuery",
        users: dict,
        chats: dict,
    ) -> "SharedWidgetQuery":
        return SharedWidgetQuery(
            client=client,
            id=str(update.query_id),
            from_user=types.User._parse(client, users.get(update.user_id)),
            type=await types.WidgetQueryType._parse(client, update.query_type, update.wallet_card, users, chats),
            data=_decode(update.data),
            widget_id=str(update.widget_id),
        )

    async def answer(self, data: Optional[str] = None) -> bool:
        """Bound method *answer* of :obj:`~pyrogram.types.SharedWidgetQuery`.

        Use as a shortcut for:

        .. code-block:: python

            await client.answer_widget_query(shared_widget_query.id, data)

        Example:
            .. code-block:: python

                await shared_widget_query.answer("ok")

        Parameters:
            data (``str``, *optional*):
                Data to be returned to the widget, 0-1024 bytes.

        Returns:
            ``bool``: True on success.
        """
        return await self._client.answer_widget_query(self.id, data)
