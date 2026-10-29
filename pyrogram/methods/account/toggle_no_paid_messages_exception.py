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

from typing import Optional, Union

import pyrogram
from pyrogram import raw


class ToggleNoPaidMessagesException:
    async def toggle_no_paid_messages_exception(
        self: "pyrogram.Client",
        user_id: Union[int, str],
        require_payment: bool = False,
        refund_charged: bool = False,
        chat_id: Optional[Union[int, str]] = None
    ) -> bool:
        """Let a user message you without paying Telegram Stars, or make them pay again.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            user_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user.

            require_payment (``bool``, *optional*):
                Pass True to make the user pay again.
                By default the user can message for free.

            refund_charged (``bool``, *optional*):
                Pass True to also refund the Stars the user already paid.

            chat_id (``int`` | ``str``, *optional*):
                Unique identifier (int) or username (str) of a channel, to change the exception for the
                direct messages of that channel instead of the current user.

        Returns:
            ``bool``: On success, True is returned.

        Example:
            .. code-block:: python

                await app.toggle_no_paid_messages_exception("username", refund_charged=True)

                await app.toggle_no_paid_messages_exception("username", require_payment=True)
        """
        return await self.invoke(
            raw.functions.account.ToggleNoPaidMessagesException(
                user_id=await self.resolve_peer(user_id),
                require_payment=require_payment,
                refund_charged=refund_charged,
                parent_peer=await self.resolve_peer(chat_id) if chat_id is not None else None
            )
        )
