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
from pyrogram import raw, types


class CreateUserWallet:
    async def create_user_wallet(
        self: "pyrogram.Client",
        user_id: Union[int, str]
    ) -> Optional["types.UserTonWalletAddress"]:
        """Create a TON wallet for a regular user.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            user_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target user.
                For a contact that exists in your Telegram address book you can use his phone number (str).

        Returns:
            :obj:`~pyrogram.types.UserTonWalletAddress`: On success, the address of the created wallet is returned.
            None if no address was returned.

        Example:
            .. code-block:: python

                address = await app.create_user_wallet("username")
        """
        r = await self.invoke(
            raw.functions.wallet.GetUserAddresses(
                force=True,
                id=[await self.resolve_peer(user_id)],
                addresses=[]
            )
        )

        if not r.addresses:
            return None

        return types.UserTonWalletAddress._parse(self, r.addresses[0], {i.id: i for i in r.users})
