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
from pyrogram import raw, utils

from .inline_session import invoke_inline


class EditMessageWidgetData:
    async def edit_message_widget_data(
        self: "pyrogram.Client",
        chat_id: Optional[Union[int, str]] = None,
        message_id: Optional[int] = None,
        inline_message_id: Optional[str] = None,
        public_data: Optional[str] = None,
        chat_data: Optional[str] = None,
    ) -> bool:
        """Edit data of a widget in a message sent by the bot or via the bot (for inline bots).
        Public data of a shared widget can be changed at most once per second.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``, *optional*):
                Unique identifier (int) or username (str) of the target chat.
                Required if *inline_message_id* is not specified.

            message_id (``int``, *optional*):
                Identifier of the message with the widget.
                Required if *inline_message_id* is not specified.

            inline_message_id (``str``, *optional*):
                Identifier of the inline message.
                Required if *chat_id* and *message_id* are not specified.

            public_data (``str``, *optional*):
                New public data of the widget, 0-1024 bytes; pass an empty string to remove the public data.
                If omitted, then the public data isn't changed.

            chat_data (``str``, *optional*):
                New data of the widget, which is specific to the message, 0-1024 bytes;
                pass an empty string to remove the data. If omitted, then the data isn't changed.

        Returns:
            ``bool``: True on success.

        Example:
            .. code-block:: python

                await app.edit_message_widget_data(chat_id, message_id, chat_data="new")
        """
        if inline_message_id is not None:
            unpacked = utils.unpack_inline_message_id(inline_message_id)

            return await invoke_inline(
                self, unpacked.dc_id,
                raw.functions.messages.EditInlineBotMessageWidgetData(
                    id=unpacked, public_data=public_data, chat_data=chat_data
                ),
            )

        if chat_id is None or message_id is None:
            raise ValueError("pass chat_id and message_id, or inline_message_id")

        await self.invoke(
            raw.functions.messages.EditMessageWidgetData(
                peer=await self.resolve_peer(chat_id),
                id=message_id,
                public_data=public_data,
                chat_data=chat_data,
            )
        )

        return True
