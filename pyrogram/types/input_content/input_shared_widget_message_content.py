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

from typing import List, Optional

import pyrogram
from pyrogram import enums, raw, types, utils

from .input_message_content import InputMessageContent


class InputSharedWidgetMessageContent(InputMessageContent):
    """Content of a message with a shared widget to be sent as the result of an inline query.
    Currently, widgets can't be sent in response to inline queries in the production environment.

    Parameters:
        widget_id (``str``):
            Unique identifier of the shared widget created by the bot.

        chat_data (``str``, *optional*):
            Data of the widget, which is specific to the message, 0-1024 bytes.

        caption (``str``, *optional*):
            Widget caption, 0-1024 characters after entities parsing.

        parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
            By default, texts are parsed using both Markdown and HTML styles.
            You can combine both syntaxes together.

        caption_entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
            List of special entities that appear in the caption, which can be specified instead of *parse_mode*.

        show_caption_above_media (``bool``, *optional*):
            Pass True if the caption must be shown above the widget.
    """

    def __init__(
        self,
        widget_id: str,
        chat_data: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        show_caption_above_media: Optional[bool] = None,
    ):
        super().__init__()

        self.widget_id = widget_id
        self.chat_data = chat_data
        self.caption = caption
        self.parse_mode = parse_mode
        self.caption_entities = caption_entities
        self.show_caption_above_media = show_caption_above_media

    async def write(self, client: "pyrogram.Client", reply_markup):
        message, entities = (await utils.parse_text_entities(
            client, self.caption, self.parse_mode, self.caption_entities
        )).values()

        return raw.types.InputBotInlineMessageWidgetId(
            invert_media=self.show_caption_above_media,
            widget_id=int(self.widget_id),
            chat_data=self.chat_data,
            reply_markup=await reply_markup.write(client) if reply_markup else None,
            message=message,
            entities=entities,
        )
