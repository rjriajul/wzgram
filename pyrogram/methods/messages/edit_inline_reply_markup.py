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
from pyrogram import raw
from pyrogram import types
from pyrogram import utils
from .inline_session import invoke_inline


class EditInlineReplyMarkup:
    async def edit_inline_reply_markup(
        self: "pyrogram.Client",
        inline_message_id: str,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        business_connection_id: Optional[str] = None,
    ) -> bool:
        """Edit only the reply markup of inline messages sent via the bot (for inline bots).

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            inline_message_id (``str``):
                Identifier of the inline message.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An InlineKeyboardMarkup object.
                Pass None to remove the existing reply markup.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

        Returns:
            ``bool``: On success, True is returned.

        Example:
            .. code-block:: python

                from wzgram.types import InlineKeyboardMarkup, InlineKeyboardButton

                # Bots only
                await app.edit_inline_reply_markup(
                    inline_message_id,
                    InlineKeyboardMarkup([[
                        InlineKeyboardButton("New button", callback_data="new_data")]]))
        """

        unpacked = utils.unpack_inline_message_id(inline_message_id)
        dc_id = unpacked.dc_id

        return await invoke_inline(
            self, dc_id,
            raw.functions.messages.EditInlineBotMessage(
                id=unpacked,
                reply_markup=await utils.write_edit_reply_markup(self, reply_markup=reply_markup),
            ),
            business_connection_id
        )
