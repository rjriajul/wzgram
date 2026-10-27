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

import asyncio
from typing import Iterable, List, Union

import pyrogram
from pyrogram import raw, types


class GetUserTonWalletAddresses:
    async def get_user_ton_wallet_addresses(
        self: "pyrogram.Client",
        user_ids: Union[int, str, Iterable[Union[int, str]]]
    ) -> List["types.UserTonWalletAddress"]:
        """Get TON wallet addresses of users.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            user_ids (``int`` | ``str`` | Iterable of ``int`` or ``str``):
                Unique identifiers (int) or usernames (str) of the target users.
                Users without a TON wallet are skipped.

        Returns:
            List of :obj:`~pyrogram.types.UserTonWalletAddress`: The wallet addresses found.

        Example:
            .. code-block:: python

                addresses = await app.get_user_ton_wallet_addresses(["me", "username"])
        """
        if isinstance(user_ids, (int, str)):
            user_ids = [user_ids]

        peers = await asyncio.gather(*[self.resolve_peer(i) for i in user_ids])

        r = await self.invoke(raw.functions.wallet.GetUserAddresses(id=list(peers), addresses=[]))

        users = {i.id: i for i in r.users}

        return types.List([types.UserTonWalletAddress._parse(self, a, users) for a in r.addresses])
