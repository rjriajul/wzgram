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
from ..object import Object


class WidgetQueryType(Object):
    """The type of a query from a widget.

    It should be one of:

    - :obj:`~pyrogram.types.WidgetQueryTypeData`
    - :obj:`~pyrogram.types.WidgetQueryTypeSignData`
    - :obj:`~pyrogram.types.WidgetQueryTypeSentTransaction`
    """

    def __init__(self):
        super().__init__()

    @staticmethod
    async def _parse(
        client: "pyrogram.Client",
        query_type: "raw.base.WidgetQueryType",
        wallet_card: Optional["raw.types.wallet.Card"] = None,
        users: dict = {},
        chats: dict = {},
    ) -> Optional["WidgetQueryType"]:
        if isinstance(query_type, raw.types.WidgetQueryTypeData):
            return WidgetQueryTypeData(
                wallet_card=await types.TonWalletCard._parse(client, wallet_card, users, chats)
            )

        if isinstance(query_type, raw.types.WidgetQueryTypeSignData):
            return WidgetQueryTypeSignData(
                wallet=types.WidgetQueryWallet._parse(query_type.wallet),
                sign_data=query_type.sign_data.data,
            )

        if isinstance(query_type, raw.types.WidgetQueryTypeSentTransaction):
            return WidgetQueryTypeSentTransaction(
                wallet=types.WidgetQueryWallet._parse(query_type.wallet),
                msg_hash=query_type.msg_hash,
            )

        return None


class WidgetQueryTypeData(WidgetQueryType):
    """The query contains data for the bot.

    Parameters:
        wallet_card (:obj:`~pyrogram.types.TonWalletCard`, *optional*):
            TON wallet card of the user who sent the query, if it was sent to the bot along with the query.
    """

    def __init__(self, *, wallet_card: Optional["types.TonWalletCard"] = None):
        super().__init__()

        self.wallet_card = wallet_card


class WidgetQueryTypeSignData(WidgetQueryType):
    """The query contains data signed by a TON wallet of the user who sent the query.
    The data is signed for the domain bot<bot_id>, where <bot_id> is the identifier of the bot.

    Parameters:
        wallet (:obj:`~pyrogram.types.WidgetQueryWallet`):
            The wallet that signed the data.

        sign_data (``str``):
            JSON-serialized signed data.
    """

    def __init__(self, *, wallet: "types.WidgetQueryWallet", sign_data: str):
        super().__init__()

        self.wallet = wallet
        self.sign_data = sign_data


class WidgetQueryTypeSentTransaction(WidgetQueryType):
    """The query notifies the bot about a transaction sent from a TON wallet of the user who sent the query.

    Parameters:
        wallet (:obj:`~pyrogram.types.WidgetQueryWallet`):
            The wallet from which the transaction was sent.

        msg_hash (``str``):
            Value of msg_hash of the transaction.
    """

    def __init__(self, *, wallet: "types.WidgetQueryWallet", msg_hash: str):
        super().__init__()

        self.wallet = wallet
        self.msg_hash = msg_hash
