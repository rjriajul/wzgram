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

from typing import List, Optional

import pyrogram
from pyrogram import raw, types
from ..object import Object


class TonWalletCard(Object):
    """A TON wallet card, which is shown on the profile page of a user to everyone.

    Parameters:
        address (``str``):
            Address of the wallet.

        amount (``str``):
            Balance of the wallet, in the smallest units of the cryptocurrency, as a decimal number.

        stickers (List of :obj:`~pyrogram.types.TonWalletCardSticker`):
            Stickers placed on the card.

        background_nft_address (``str``, *optional*):
            Address of the NFT of one of the stickers, whose colors must be used for the card background;
            None if the default background must be used.
    """

    def __init__(
        self,
        *,
        address: str,
        amount: str,
        stickers: List["types.TonWalletCardSticker"],
        background_nft_address: Optional[str] = None,
    ):
        super().__init__()

        self.address = address
        self.amount = amount
        self.stickers = stickers
        self.background_nft_address = background_nft_address

    @staticmethod
    async def _parse(client: "pyrogram.Client", card: Optional["raw.types.wallet.Card"], users: dict = {}, chats: dict = {}) -> Optional["TonWalletCard"]:
        if not isinstance(card, raw.types.wallet.Card):
            return None

        return TonWalletCard(
            address=card.address,
            amount=str(card.balance),
            stickers=types.List([await types.TonWalletCardSticker._parse(client, s, users, chats) for s in card.stickers or []]),
            background_nft_address=card.bg_nft_item.address if card.bg_nft_item else None,
        )
