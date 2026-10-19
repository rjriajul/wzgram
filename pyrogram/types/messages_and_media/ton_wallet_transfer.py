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

from pyrogram import raw, types

from ..object import Object


class TonWalletTransfer(Object):
    """A transfer with the TON wallet of the current user.

    Parameters:
        sender (:obj:`~pyrogram.types.User`, *optional*):
            Sender of the transfer.

        transaction_id (``str``):
            Unique identifier of the transaction.

        peer_address (``str``):
            Address of the transaction peer in the TON blockchain.

        amount (``int``):
            The transferred amount, in the smallest units of the cryptocurrency.

        comment (``str``, *optional*):
            Comment added to the transaction.

        is_comment_encrypted (``bool``, *optional*):
            True, if the comment is encrypted and must be decrypted with the receiver's or sender's private key.
    """

    def __init__(
        self,
        *,
        sender: Optional["types.User"] = None,
        transaction_id: str,
        peer_address: str,
        amount: int,
        comment: Optional[str] = None,
        is_comment_encrypted: Optional[bool] = None
    ):
        super().__init__()

        self.sender = sender
        self.transaction_id = transaction_id
        self.peer_address = peer_address
        self.amount = amount
        self.comment = comment
        self.is_comment_encrypted = is_comment_encrypted

    @staticmethod
    def _parse(
        client,
        action: "raw.types.MessageActionGramTransfer",
        sender: Optional["raw.base.User"] = None
    ) -> "TonWalletTransfer":
        return TonWalletTransfer(
            sender=types.User._parse(client, sender),
            transaction_id=action.transaction_id,
            peer_address=action.peer_address,
            amount=action.amount,
            comment=action.comment,
            is_comment_encrypted=action.comment_encrypted
        )

    @property
    def link(self) -> str:
        return f"https://tonviewer.com/transaction/{self.transaction_id}"
