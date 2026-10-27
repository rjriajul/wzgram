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
from pyrogram import raw, types, utils


class DeleteTonWallet:
    async def delete_ton_wallet(
        self: "pyrogram.Client",
        password: Optional[str] = None
    ) -> "types.TonWalletState":
        """Delete the current TON wallet of the user and create a new one.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            password (``str``, *optional*):
                Two-step verification password of the current user.

        Returns:
            :obj:`~pyrogram.types.TonWalletState`: On success, the state of the new wallet is returned.

        Example:
            .. code-block:: python

                state = await app.delete_ton_wallet(password="password")
        """
        return types.TonWalletState._parse(
            await self.invoke(
                raw.functions.wallet.ReplaceWallet(
                    wallet=raw.types.InputWalletNew(),
                    password=utils.compute_password_check(
                        await self.invoke(raw.functions.account.GetPassword()), password
                    ) if password is not None else None
                )
            )
        )
