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

# ***************************
# GENERATED FILE - DO NOT EDIT
# Source: tl:messages.translateText
# ***************************

from typing import Union, List, Optional

import pyrogram
from pyrogram import raw


class TranslateText:
    async def translate_text(
        self: "pyrogram.Client",
        peer: Optional[Union[int, str]] = None,
        id: Optional[Union[int, List[int]]] = None,
        text: Optional[Union[str, List[raw.types.TextWithEntities]]] = None,
        to_lang: Optional[str] = None,
        tone: Optional[str] = None,
    ) -> List["raw.types.TextWithEntities"]:
        """Translate text or a message to another language.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            peer (Union[int, str], *optional*): Chat from which to translate an existing message
            id (Union[int, List[int]], *optional*): Message ID or list of message IDs to translate
            text (Union[str, List[raw.types.TextWithEntities]], *optional*): Text to translate (plain string or list of TextWithEntities)
            to_lang (str): Target language code (e.g. "en", "es")
            tone (str, *optional*): AI translation tone preset

        Returns:
            List of :obj:`~pyrogram.raw.types.TextWithEntities`

        Example:
            .. code-block:: python

                await app.translate_text(...)
        """

        if to_lang is None:
            raise ValueError("to_lang is required")

        if isinstance(id, int):
            id = [id]

        if isinstance(text, str):
            text = [raw.types.TextWithEntities(text=text, entities=[])]

        r = await self.invoke(
            raw.functions.messages.TranslateText(
                peer=await self.resolve_peer(peer) if peer is not None else None,
                id=id,
                text=text,
                to_lang=to_lang,
                tone=tone,
            )
        )

        return r.result
