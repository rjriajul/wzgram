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
from pyrogram import enums, raw, types, utils
from ..object import Object
from ..update import Update

CHAT_TYPES = {
    "sender": enums.ChatType.BOT,
    "private": enums.ChatType.PRIVATE,
    "group": enums.ChatType.GROUP,
    "supergroup": enums.ChatType.SUPERGROUP,
    "channel": enums.ChatType.CHANNEL,
}


def _decode(data: bytes) -> Union[str, bytes]:
    try:
        return data.decode()
    except (UnicodeDecodeError, AttributeError):
        return data


class WidgetQuery(Object, Update):
    """An incoming query from a widget in a message sent by the bot or via the bot.
    Use :meth:`~pyrogram.Client.answer_widget_query` to answer the query.

    Parameters:
        id (``str``):
            Unique identifier for this query.

        from_user (:obj:`~pyrogram.types.User`):
            Sender.

        chat_instance (``str``):
            Global identifier, uniquely corresponding to the chat to which the message with the widget was sent.

        type (:obj:`~pyrogram.types.WidgetQueryType`):
            Type of the query.

        data (``str`` | ``bytes``):
            Data of the query, 1-64 bytes.

        chat (:obj:`~pyrogram.types.Chat`, *optional*):
            Chat with the message containing the widget; None if the widget is in an inline message.

        message_id (``int``, *optional*):
            Identifier of the message containing the widget; None if the widget is in an inline message.

        inline_message_id (``str``, *optional*):
            Identifier of the inline message containing the widget.

        chat_type (:obj:`~pyrogram.enums.ChatType`, *optional*):
            Type of the chat to which the message with the widget was sent.

        widget_id (``str``, *optional*):
            Unique identifier of the shared widget, which sent the query; None if the widget isn't shared.
    """

    def __init__(
        self,
        *,
        client: "pyrogram.Client" = None,
        id: str,
        from_user: "types.User",
        chat_instance: str,
        type: "types.WidgetQueryType",
        data: Union[str, bytes],
        chat: Optional["types.Chat"] = None,
        message_id: Optional[int] = None,
        inline_message_id: Optional[str] = None,
        chat_type: Optional["enums.ChatType"] = None,
        widget_id: Optional[str] = None,
    ):
        super().__init__(client)

        self.id = id
        self.from_user = from_user
        self.chat_instance = chat_instance
        self.type = type
        self.data = data
        self.chat = chat
        self.message_id = message_id
        self.inline_message_id = inline_message_id
        self.chat_type = chat_type
        self.widget_id = widget_id

    @staticmethod
    async def _parse(
        client: "pyrogram.Client",
        update: Union["raw.types.UpdateBotWidgetQuery", "raw.types.UpdateInlineBotWidgetQuery"],
        users: dict,
        chats: dict,
    ) -> "WidgetQuery":
        chat = None
        message_id = None
        inline_message_id = None

        if isinstance(update, raw.types.UpdateBotWidgetQuery):
            raw_id = utils.get_raw_peer_id(update.peer)
            raw_chat = users.get(raw_id) if isinstance(update.peer, raw.types.PeerUser) else chats.get(raw_id)
            chat = types.Chat._parse_chat(client, raw_chat) if raw_chat else None
            message_id = update.msg_id
        else:
            inline_message_id = utils.pack_inline_message_id(update.inline_message_id)

        return WidgetQuery(
            client=client,
            id=str(update.query_id),
            from_user=types.User._parse(client, users.get(update.user_id)),
            chat_instance=str(update.chat_instance),
            type=await types.WidgetQueryType._parse(client, update.query_type, update.wallet_card, users, chats),
            data=_decode(update.data),
            chat=chat,
            message_id=message_id,
            inline_message_id=inline_message_id,
            chat_type=CHAT_TYPES.get(update.chat_type),
            widget_id=str(update.widget_id) if update.widget_id is not None else None,
        )

    async def answer(self, data: Optional[str] = None) -> bool:
        """Bound method *answer* of :obj:`~pyrogram.types.WidgetQuery`.

        Use as a shortcut for:

        .. code-block:: python

            await client.answer_widget_query(widget_query.id, data)

        Example:
            .. code-block:: python

                await widget_query.answer("ok")

        Parameters:
            data (``str``, *optional*):
                Data to be returned to the widget, 0-1024 bytes.

        Returns:
            ``bool``: True on success.
        """
        return await self._client.answer_widget_query(self.id, data)
