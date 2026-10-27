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

from typing import Dict, Optional

from pyrogram import raw, types

from ..object import Object


class UserTonWalletAddress(Object):
    """TON wallet address of a user.

    Parameters:
        wallet_address (``str``):
            Address of the wallet in the TON blockchain.

        public_key (``bytes``):
            Public key of the wallet.

        user (:obj:`~pyrogram.types.User`, *optional*):
            The user the wallet belongs to.
    """

    def __init__(self, *, wallet_address: str, public_key: bytes, user: Optional["types.User"] = None):
        super().__init__()

        self.wallet_address = wallet_address
        self.public_key = public_key
        self.user = user

    @staticmethod
    def _parse(
        client,
        address: "raw.types.WalletUserAddress",
        users: Dict[int, "raw.base.User"]
    ) -> "UserTonWalletAddress":
        return UserTonWalletAddress(
            wallet_address=address.address,
            public_key=address.public_key,
            user=types.User._parse(client, users.get(address.user_id))
        )
