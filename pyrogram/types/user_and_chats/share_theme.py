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

from typing import Dict, List, Optional

import pyrogram
from pyrogram import raw, types

from ..object import Object


class ShareTheme(Object):
    """The theme of the page shown when a user or a channel is shared.

    Parameters:
        backdrop_id (``int``, *optional*):
            Identifier of the backdrop, see :meth:`~pyrogram.Client.get_share_theme_backdrops`.

        emojis (List of :obj:`~pyrogram.types.Reaction`, *optional*):
            Emojis shown on the backdrop.

        gift (:obj:`~pyrogram.types.Gift`, *optional*):
            The gift the theme is taken from.
    """

    def __init__(
        self,
        *,
        backdrop_id: Optional[int] = None,
        emojis: Optional[List["types.Reaction"]] = None,
        gift: Optional["types.Gift"] = None
    ):
        super().__init__()

        self.backdrop_id = backdrop_id
        self.emojis = emojis
        self.gift = gift

    @staticmethod
    async def _parse(
        client: "pyrogram.Client",
        theme: Optional["raw.base.ShareTheme"],
        users: Dict[int, "raw.base.User"],
        chats: Dict[int, "raw.base.Chat"]
    ) -> Optional["ShareTheme"]:
        if isinstance(theme, raw.types.ShareThemeEmojiBackdrop):
            return ShareTheme(
                backdrop_id=theme.backdrop_id,
                emojis=types.List([types.Reaction._parse(client, e) for e in theme.emojis or []]) or None
            )

        if isinstance(theme, raw.types.ShareThemeGift):
            return ShareTheme(gift=await types.Gift._parse(client, theme.stargift, users=users, chats=chats))
