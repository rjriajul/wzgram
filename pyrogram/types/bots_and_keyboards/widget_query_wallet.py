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

import base64
from typing import Optional

from pyrogram import raw
from ..object import Object


class WidgetQueryWallet(Object):
    """A TON wallet of the user, which is used in a query from a widget.

    Parameters:
        address (``str``):
            Address of the wallet.

        amount (``str``):
            Balance of the wallet, in the smallest units of the cryptocurrency, as a decimal number.

        public_key (``str``, *optional*):
            Hex-encoded public key of the wallet; None if unknown.

        state_init (``str``, *optional*):
            Base64-encoded serialized StateInit of the wallet contract; None if and only if *public_key* is None.
    """

    def __init__(
        self,
        *,
        address: str,
        amount: str,
        public_key: Optional[str] = None,
        state_init: Optional[str] = None,
    ):
        super().__init__()

        self.address = address
        self.amount = amount
        self.public_key = public_key
        self.state_init = state_init

    @staticmethod
    def _parse(wallet: "raw.types.UserWallet") -> "WidgetQueryWallet":
        return WidgetQueryWallet(
            address=wallet.address,
            amount=str(wallet.balance),
            public_key=wallet.public_key.hex() if wallet.public_key is not None else None,
            state_init=base64.b64encode(wallet.state_init).decode() if wallet.state_init is not None else None,
        )
