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

from typing import Union
from urllib.parse import parse_qs, urlparse

import pyrogram
from pyrogram import raw, types


class ImportNoPaidMessagesToken:
    async def import_no_paid_messages_token(
        self: "pyrogram.Client",
        user_id: Union[int, str],
        token: str
    ) -> "types.User":
        """Use a link that lets the current user message another user without paying Telegram Stars.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            user_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user who made the link.

            token (``str``):
                The token, or the whole link (``https://t.me/username?free=...``).

        Returns:
            :obj:`~pyrogram.types.User`: The user who made the link.

        Example:
            .. code-block:: python

                await app.import_no_paid_messages_token("username", "https://t.me/username?free=abc")
        """
        token = parse_qs(urlparse(token).query).get("free", [token])[0]

        r = await self.invoke(
            raw.functions.contacts.ImportNoPaidMessagesToken(
                user_id=await self.resolve_peer(user_id),
                token=token
            )
        )

        return types.User._parse(self, r)
