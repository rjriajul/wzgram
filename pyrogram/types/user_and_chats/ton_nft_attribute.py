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

from pyrogram import raw
from ..object import Object


class TonNftAttribute(Object):
    """An attribute of an NFT in the TON blockchain.

    Parameters:
        trait_type (``str``):
            Trait type of the attribute.

        value (``str``):
            Value of the attribute.
    """

    def __init__(self, *, trait_type: str, value: str):
        super().__init__()

        self.trait_type = trait_type
        self.value = value

    @staticmethod
    def _parse(attribute: "raw.types.wallet.NftAttribute") -> "TonNftAttribute":
        return TonNftAttribute(trait_type=attribute.trait_type, value=attribute.value)
