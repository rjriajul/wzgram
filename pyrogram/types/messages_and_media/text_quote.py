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

from typing import Dict, List, Optional, Union

import pyrogram
from pyrogram import raw, types

from ..messages_and_media.message import Str
from .rich_text import _plain_text
from ..object import Object


class TextQuote(Object):
    """Describes manually or automatically chosen quote from another message.

    Parameters:
        text (``str``):
            Text of the quoted part of a message that is replied to by the given message.

        entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
            Special entities that appear in the quote.
            Currently, only bold, italic, underline, strikethrough, spoiler, and custom_emoji entities are kept in quotes.

        position (``int``):
            Approximate quote position in the original message in UTF-16 code units as specified by the sender.

        is_manual (``bool``, *optional*):
            True, if the quote was chosen manually by the message sender.
            Otherwise, the quote was added automatically by the server.

        rich_text (:obj:`~pyrogram.types.RichText`, *optional*):
            The quote as rich text, when it was taken from a rich message.

    """
    def __init__(
        self, *,
        text: Optional[str] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        position: Optional[int] = None,
        is_manual: Optional[bool] = None,
        rich_text: Optional[Union[str, List["types.RichText"], "types.RichText"]] = None
    ):
        super().__init__()

        self.text = text
        self.entities = entities
        self.position = position
        self.is_manual = is_manual
        self.rich_text = rich_text

    @staticmethod
    async def _parse(
        client: "pyrogram.Client",
        users: Dict[int, "raw.types.User"],
        chats: Dict[int, "raw.types.Chat"],
        reply_to: "raw.types.MessageReplyHeader"
    ) -> "TextQuote":
        if isinstance(reply_to, raw.types.MessageReplyHeader):
            entities = types.List(
                filter(
                    lambda x: x is not None,
                    [
                        types.MessageEntity._parse(client, entity, users)
                        for entity in getattr(reply_to, "quote_entities", [])
                    ]
                )
            )

            rich_text = None

            if reply_to.quote_rich:
                rich_text = await types.RichText._parse(
                    client, raw.types.TextConcat(texts=reply_to.quote_rich), users, chats
                )

            text = reply_to.quote_text or _plain_text(rich_text)

            return TextQuote(
                text=Str(text).init(entities) if text else None,
                entities=entities or None,
                position=reply_to.quote_offset or 0,
                is_manual=reply_to.quote,
                rich_text=rich_text
            )

