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

from datetime import datetime
from typing import Optional

from pyrogram import raw, utils

from ..object import Object


class NoPaidMessagesToken(Object):
    """A link that lets other users message the current user without paying Telegram Stars.

    Parameters:
        token (``str``):
            The token, for :meth:`~pyrogram.Client.import_no_paid_messages_token`.

        link (``str``):
            The link to share.

        expiration_date (:py:obj:`~datetime.datetime`, *optional*):
            Date the link expires. None if it never expires.
    """

    def __init__(
        self,
        *,
        token: str,
        link: str,
        expiration_date: Optional[datetime] = None
    ):
        super().__init__()

        self.token = token
        self.link = link
        self.expiration_date = expiration_date

    @staticmethod
    def _parse(token: "raw.types.ExportedNoPaidMessagesToken") -> "NoPaidMessagesToken":
        return NoPaidMessagesToken(
            token=token.token,
            link=token.url,
            expiration_date=utils.timestamp_to_datetime(token.expires)
        )
