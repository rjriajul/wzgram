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

from typing import Iterable, Union

import pyrogram
from pyrogram import raw


class InviteUsersToBot:
    async def invite_users_to_bot(
        self: "pyrogram.Client",
        bot_id: Union[int, str],
        user_ids: Union[int, str, Iterable[Union[int, str]]],
    ) -> bool:
        """Invite users to the private chat with a bot owned by the current user.
        The bot will be able to send messages to the invited users.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            bot_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the bot.
                The bot must be owned by the current user.

            user_ids (``int`` | ``str`` | Iterable of ``int`` or ``str``):
                Unique identifiers (int) or usernames (str) of up to 10 users to invite.

        Returns:
            ``bool``: True on success.

        Example:
            .. code-block:: python

                await app.invite_users_to_bot("my_bot", ["alice", 123456789])
        """
        if isinstance(user_ids, (int, str)):
            user_ids = [user_ids]

        users = [await self.resolve_peer(i) for i in user_ids]

        if not users:
            raise ValueError("user_ids must not be empty")

        return await self.invoke(
            raw.functions.messages.InviteUsersToBot(
                bot=await self.resolve_peer(bot_id),
                users=users,
            )
        )
