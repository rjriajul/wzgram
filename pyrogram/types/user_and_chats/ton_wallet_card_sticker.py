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

import pyrogram
from pyrogram import raw, types
from ..object import Object


class TonWalletCardSticker(Object):
    """A sticker on a TON wallet card.

    Parameters:
        position (:obj:`~pyrogram.types.AreaPosition`):
            Position of the sticker on the card.

        nft (:obj:`~pyrogram.types.TonNft`):
            The NFT shown as the sticker.
    """

    def __init__(self, *, position: "types.AreaPosition", nft: "types.TonNft"):
        super().__init__()

        self.position = position
        self.nft = nft

    @staticmethod
    async def _parse(client: "pyrogram.Client", sticker: "raw.types.wallet.CardSticker", users: dict = {}, chats: dict = {}) -> "TonWalletCardSticker":
        return TonWalletCardSticker(
            position=types.AreaPosition._parse(sticker.coordinates),
            nft=await types.TonNft._parse(client, sticker.nft, users, chats),
        )
