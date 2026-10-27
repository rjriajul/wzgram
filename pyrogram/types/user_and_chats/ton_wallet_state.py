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

from pyrogram import raw

from ..object import Object


class TonWalletState(Object):
    """State of the current user's wallet in the TON blockchain.

    Parameters:
        wallet_address (``str``, *optional*):
            Address of the wallet.

        public_key (``bytes``, *optional*):
            Public key of the wallet.

        gram_amount (``int``, *optional*):
            Balance of the wallet, in the smallest units of the cryptocurrency.

        is_being_created (``bool``, *optional*):
            True, if the wallet is being created.

        is_backup_enabled (``bool``, *optional*):
            True, if backup of the wallet key is enabled.

        can_enable_backup (``bool``, *optional*):
            True, if backup of the wallet key can be enabled.

        can_export_phrase (``bool``, *optional*):
            True, if the wallet key can be exported.
    """

    def __init__(
        self,
        *,
        wallet_address: Optional[str] = None,
        public_key: Optional[bytes] = None,
        gram_amount: Optional[int] = None,
        is_being_created: Optional[bool] = None,
        is_backup_enabled: Optional[bool] = None,
        can_enable_backup: Optional[bool] = None,
        can_export_phrase: Optional[bool] = None
    ):
        super().__init__()

        self.wallet_address = wallet_address
        self.public_key = public_key
        self.gram_amount = gram_amount
        self.is_being_created = is_being_created
        self.is_backup_enabled = is_backup_enabled
        self.can_enable_backup = can_enable_backup
        self.can_export_phrase = can_export_phrase

    @staticmethod
    def _parse(state: "raw.base.WalletState") -> "TonWalletState":
        if isinstance(state, raw.types.WalletStateEmpty):
            return TonWalletState(is_being_created=state.creating)

        return TonWalletState(
            wallet_address=state.address,
            public_key=state.public_key,
            gram_amount=state.balance,
            is_backup_enabled=state.backup_enabled,
            can_enable_backup=state.can_enable_backup,
            can_export_phrase=state.can_export_phrase
        )
