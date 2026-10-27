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

from typing import Optional

import pyrogram
from pyrogram import raw, types


class GetAddressTonWallet:
    async def get_address_ton_wallet(
        self: "pyrogram.Client",
        address: str
    ) -> Optional["types.UserTonWalletAddress"]:
        """Get information about a TON wallet by its address.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            address (``str``):
                Address of the wallet in the TON blockchain.

        Returns:
            :obj:`~pyrogram.types.UserTonWalletAddress`: Information about the wallet.
            None if the address is not known to Telegram.

        Example:
            .. code-block:: python

                wallet = await app.get_address_ton_wallet("UQ...")
        """
        r = await self.invoke(raw.functions.wallet.GetUserAddresses(id=[], addresses=[address]))

        if not r.addresses:
            return None

        return types.UserTonWalletAddress._parse(self, r.addresses[0], {i.id: i for i in r.users})
