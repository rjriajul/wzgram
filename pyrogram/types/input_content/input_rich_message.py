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

from typing import List, Optional, TYPE_CHECKING

from pyrogram import raw

from ..object import Object

if TYPE_CHECKING:
    from .input_rich_block import InputRichBlock
    from .input_rich_message_media import InputRichMessageMedia


class InputRichMessage(Object):
    """Describes a rich message to create.

    Parameters:
        html (``str``, *optional*):
            Content of the rich message to send described using HTML formatting.
            See `rich message formatting options <https://core.telegram.org/bots/api#rich-message-formatting-options>`__ for more details.

        markdown (``str``, *optional*):
            Content of the rich message to send described using Markdown formatting.
            See `rich message formatting options <https://core.telegram.org/bots/api#rich-message-formatting-options>`__ for more details.

        is_rtl (``bool``, *optional*):
            Pass *True* if the rich message must be shown right-to-left.

        skip_entity_detection (``bool``, *optional*):
            Pass *True* to skip automatic detection of entities
            (e.g., URLs, email addresses, username mentions, hashtags, cashtags, bot commands, or phone numbers) in the text.

        blocks (List of :obj:`InputRichBlock`, *optional*):
            List of blocks that define the rich message content.
            See `rich message formatting options <https://core.telegram.org/bots/api#rich-message-formatting-options>`__ for more details.

        media (:obj:`InputRichMessageMedia`, *optional*):
            Media referenced by the blocks.
    """

    def __init__(
        self,
        html: Optional[str] = None,
        markdown: Optional[str] = None,
        is_rtl: Optional[bool] = None,
        skip_entity_detection: Optional[bool] = None,
        blocks: Optional[List["InputRichBlock"]] = None,
        media: Optional["InputRichMessageMedia"] = None,
    ):
        super().__init__()

        self.html = html
        self.markdown = markdown
        self.is_rtl = is_rtl
        self.skip_entity_detection = skip_entity_detection
        self.blocks = blocks
        self.media = media

    def write(self) -> "raw.base.InputRichMessage":
        if self.html:
            input_rich_message = raw.types.InputRichMessageHTML(
                html=self.html,
                rtl=self.is_rtl,
                noautolink=self.skip_entity_detection
            )
        elif self.markdown:
            input_rich_message = raw.types.InputRichMessageMarkdown(
                markdown=self.markdown,
                rtl=self.is_rtl,
                noautolink=self.skip_entity_detection
            )
        elif self.blocks:
            photos, documents, users = self.media.write() if self.media else (None, None, None)
            input_rich_message = raw.types.InputRichMessage(
                blocks=[block.write() for block in self.blocks],
                rtl=self.is_rtl,
                noautolink=self.skip_entity_detection,
                photos=photos,
                documents=documents,
                users=users,
            )
        else:
            raise ValueError(
                "You must provide html, markdown or blocks in the rich message"
            )

        return input_rich_message

