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
from pyrogram import raw, utils


class SetShareTheme:
    async def set_share_theme(
        self: "pyrogram.Client",
        backdrop_id: Optional[int] = None,
        emojis: Optional[List[Union[int, str]]] = None,
        gift_id: Optional[str] = None,
        chat_id: Optional[Union[int, str]] = None
    ) -> bool:
        """Set the theme of the page shown when the current user or a channel is shared.

        Pass nothing to go back to the default theme.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            backdrop_id (``int``, *optional*):
                Identifier of the backdrop, see :meth:`~pyrogram.Client.get_share_theme_backdrops`.

            emojis (List of ``int`` | ``str``, *optional*):
                Emojis to show on the backdrop: emoji (str) or custom emoji identifiers (int).

            gift_id (``str``, *optional*):
                Unique identifier of an owned gift to take the theme from.
                Can't be used together with *backdrop_id* or *emojis*.

            chat_id (``int`` | ``str``, *optional*):
                Unique identifier (int) or username (str) of a channel to set the theme of.
                Defaults to the current user.

        Returns:
            ``bool``: On success, True is returned.

        Example:
            .. code-block:: python

                await app.set_share_theme(backdrop_id=49, emojis=["🔥", 5875309033427620643])

                await app.set_share_theme(gift_id="123456")

                await app.set_share_theme()
        """
        if gift_id is not None:
            if backdrop_id is not None or emojis:
                raise ValueError("gift_id can't be used together with backdrop_id or emojis")

            theme = raw.types.InputShareThemeGift(stargift=await utils.get_input_stargift(self, gift_id))
        elif backdrop_id is not None or emojis:
            theme = raw.types.ShareThemeEmojiBackdrop(
                backdrop_id=backdrop_id,
                emojis=[
                    raw.types.ReactionCustomEmoji(document_id=i)
                    if isinstance(i, int)
                    else raw.types.ReactionEmoji(emoticon=i)
                    for i in emojis or []
                ] or None
            )
        else:
            theme = raw.types.ShareThemeDefault()

        return await self.invoke(
            raw.functions.messages.SetShareTheme(
                peer=await self.resolve_peer(chat_id if chat_id is not None else "me"),
                theme=theme
            )
        )
