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


class TonNft(Object):
    """An NFT in the TON blockchain.

    Parameters:
        address (``str``):
            Address of the NFT.

        index (``str``):
            Index of the NFT among all NFTs from the collection as a decimal number.

        name (``str``):
            Name of the NFT.

        description (``str``):
            Description of the NFT.

        collection_address (``str``, *optional*):
            Address of the collection to which the NFT belongs; None if unknown.

        attributes (List of :obj:`~pyrogram.types.TonNftAttribute`, *optional*):
            Attributes of the NFT.

        gift (:obj:`~pyrogram.types.Gift`, *optional*):
            The unique gift corresponding to the NFT.
    """

    def __init__(
        self,
        *,
        client: Optional["pyrogram.Client"] = None,
        address: str,
        index: str,
        name: str,
        description: str,
        collection_address: Optional[str] = None,
        attributes: Optional[List["types.TonNftAttribute"]] = None,
        gift: Optional["types.Gift"] = None,
    ):
        super().__init__(client)

        self.address = address
        self.index = index
        self.name = name
        self.description = description
        self.collection_address = collection_address
        self.attributes = attributes
        self.gift = gift

    @staticmethod
    async def _parse(client: "pyrogram.Client", nft: "raw.types.wallet.NftItem", users: dict = {}, chats: dict = {}) -> "TonNft":
        return TonNft(
            client=client,
            address=nft.address,
            index=nft.index,
            name=nft.name or "",
            description=nft.description or "",
            collection_address=nft.collection_address,
            attributes=types.List([types.TonNftAttribute._parse(a) for a in nft.attributes]) if nft.attributes else None,
            gift=await types.Gift._parse(client, nft.gift, users=users, chats=chats) if nft.gift else None,
        )
