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


class InputWidgetMessageContent(InputMessageContent):
    """Content of a message with an HTML widget to be sent as the result of an inline query.
    Currently, widgets can't be sent in response to inline queries in the production environment.

    Parameters:
        html (``str``):
            HTML code of the widget, 1-32768 bytes.
            The code must not exceed 4096 bytes when compressed by zlib with the maximum compression level.

        width (``int``, *optional*):
            Width of the widget in logical pixels; omit if the widget must occupy the whole width of the message bubble.

        height (``int``, *optional*):
            Height of the widget in logical pixels; omit if the height of the widget isn't fixed.

        public_data (``str``, *optional*):
            Public data of the widget, 0-1024 bytes, which will be available wherever the widget is shown.

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

        allow_queries (``bool``, *optional*):
            Pass True to allow the widget to send queries to the bot.

        is_shared (``bool``, *optional*):
            Pass True to create a shared widget.
            Each message sent from the result creates a separate shared widget.
    """

    def __init__(
        self,
        html: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        public_data: Optional[str] = None,
        chat_data: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        show_caption_above_media: Optional[bool] = None,
        allow_queries: Optional[bool] = None,
        is_shared: Optional[bool] = None,
    ):
        super().__init__()

        self.html = html
        self.width = width
        self.height = height
        self.public_data = public_data
        self.chat_data = chat_data
        self.caption = caption
        self.parse_mode = parse_mode
        self.caption_entities = caption_entities
        self.show_caption_above_media = show_caption_above_media
        self.allow_queries = allow_queries
        self.is_shared = is_shared

    async def write(self, client: "pyrogram.Client", reply_markup):
        message, entities = (await utils.parse_text_entities(
            client, self.caption, self.parse_mode, self.caption_entities
        )).values()

        return raw.types.InputBotInlineMessageWidget(
            allow_queries=self.allow_queries,
            shared_widget=self.is_shared,
            invert_media=self.show_caption_above_media,
            width=self.width or 0,
            height=self.height or 0,
            html=self.html,
            public_data=self.public_data,
            chat_data=self.chat_data,
            reply_markup=await reply_markup.write(client) if reply_markup else None,
            message=message,
            entities=entities,
        )
