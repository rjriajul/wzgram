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

from .create_user_wallet import CreateUserWallet
from .delete_ton_wallet import DeleteTonWallet
from .get_address_ton_wallet import GetAddressTonWallet
from .get_ton_wallet_ownership_proof_challenge import GetTonWalletOwnershipProofChallenge
from .get_user_ton_wallet_addresses import GetUserTonWalletAddresses
from .replace_ton_wallet import ReplaceTonWallet


class Wallet(
    CreateUserWallet,
    DeleteTonWallet,
    GetAddressTonWallet,
    GetTonWalletOwnershipProofChallenge,
    GetUserTonWalletAddresses,
    ReplaceTonWallet
):
    pass
