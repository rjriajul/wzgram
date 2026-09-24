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
from pyrogram import types

from ..messages.edit_message_media import resolve_input_media
from .edit_ephemeral_message import edit_ephemeral


class EditEphemeralMessageMedia:
    async def edit_ephemeral_message_media(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        receiver_id: Union[int, str],
        message_id: int,
        media: "types.InputMedia",
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        welcome: Optional[bool] = None,
    ) -> Optional["types.Message"]:
        """Edit the media of an ephemeral message.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            receiver_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user the ephemeral
                message was sent to.

            message_id (``int``):
                Identifier of the ephemeral message to edit.

            media (:obj:`~pyrogram.types.InputMedia`):
                The new media. A local file is uploaded first.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An inline keyboard.
                Pass None to remove the existing reply markup.

            welcome (``bool``, *optional*):
                Pass True when editing a stored welcome message rather than one that was
                delivered once.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the edited message is returned.

        Example:
            .. code-block:: python

                from wzgram.types import InputMediaPhoto

                await app.edit_ephemeral_message_media(
                    chat_id, receiver_id, message_id, InputMediaPhoto("new.jpg")
                )
        """
        raw_media, message, entities = await resolve_input_media(self, chat_id, media)

        return await edit_ephemeral(
            self, chat_id, receiver_id, message_id,
            media=raw_media,
            message=message,
            entities=entities,
            reply_markup=reply_markup,
            welcome=welcome,
        )
