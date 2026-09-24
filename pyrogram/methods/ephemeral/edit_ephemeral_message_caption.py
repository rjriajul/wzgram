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

from typing import List, Optional, Union

import pyrogram
from pyrogram import enums, types, utils

from .edit_ephemeral_message import edit_ephemeral


class EditEphemeralMessageCaption:
    async def edit_ephemeral_message_caption(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        receiver_id: Union[int, str],
        message_id: int,
        caption: str,
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        show_caption_above_media: Optional[bool] = None,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        welcome: Optional[bool] = None,
    ) -> Optional["types.Message"]:
        """Edit the caption of an ephemeral media message.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            receiver_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user the ephemeral
                message was sent to.

            message_id (``int``):
                Identifier of the ephemeral message to edit.

            caption (``str``):
                New caption of the message.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes.

            caption_entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in the caption, which can be
                specified instead of *parse_mode*.

            show_caption_above_media (``bool``, *optional*):
                Pass True if the caption must be shown above the message media.

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

                await app.edit_ephemeral_message_caption(
                    chat_id, receiver_id, message_id, "New caption"
                )
        """
        message, entities = (
            await utils.parse_text_entities(self, caption, parse_mode, caption_entities)
        ).values()

        return await edit_ephemeral(
            self, chat_id, receiver_id, message_id,
            message=message,
            entities=entities,
            show_caption_above_media=show_caption_above_media,
            reply_markup=reply_markup,
            welcome=welcome,
        )
