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

import zlib
from typing import Optional

from pyrogram import raw
from ..object import Object


class Widget(Object):
    """An HTML widget.

    Parameters:
        html (``str``):
            HTML code of the widget.

        id (``str``, *optional*):
            Unique identifier of the shared widget; None if the widget isn't shared.

        width (``int``, *optional*):
            Width of the widget in logical pixels; None if the widget must occupy the whole width of the message bubble.

        height (``int``, *optional*):
            Height of the widget in logical pixels; None if the height of the widget isn't fixed.

        public_data (``str``, *optional*):
            Public data of the widget, which is available wherever the widget is shown.
            All messages with a shared widget have the same public data.

        chat_data (``str``, *optional*):
            Data of the widget, which is specific to the message.

        is_copy (``bool``, *optional*):
            True, if the widget is a copy of a shared widget.

        can_query (``bool``, *optional*):
            True, if the widget can send queries to the bot.
    """

    def __init__(
        self,
        *,
        html: str,
        id: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        public_data: Optional[str] = None,
        chat_data: Optional[str] = None,
        is_copy: Optional[bool] = None,
        can_query: Optional[bool] = None,
    ):
        super().__init__()

        self.html = html
        self.id = id
        self.width = width
        self.height = height
        self.public_data = public_data
        self.chat_data = chat_data
        self.is_copy = is_copy
        self.can_query = can_query

    @staticmethod
    def _parse(media: "raw.types.MessageMediaWidget") -> Optional["Widget"]:
        try:
            html = zlib.decompress(media.payload, 47).decode()
        except (zlib.error, UnicodeDecodeError):
            return None

        return Widget(
            html=html,
            id=str(media.widget_id) if media.widget_id is not None else None,
            width=media.width or None,
            height=media.height or None,
            public_data=media.public_data,
            chat_data=media.chat_data,
            is_copy=media.is_copy,
            can_query=media.can_query,
        )
