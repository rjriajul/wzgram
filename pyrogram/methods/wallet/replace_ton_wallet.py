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
from pyrogram import raw, types, utils


class ReplaceTonWallet:
    async def replace_ton_wallet(
        self: "pyrogram.Client",
        proof: "types.TonWalletOwnershipProof",
        password: Optional[str] = None,
        anchor_public_key: Optional[bytes] = None
    ) -> "types.TonWalletState":
        """Replace the current TON wallet with another existing v6r2 wallet, or change the private key of the current one.

        .. include:: /_includes/usable-by/users.rst

        Parameters:
            proof (:obj:`~pyrogram.types.TonWalletOwnershipProof`):
                Proof of ownership of the new private key.
                Use :meth:`~pyrogram.Client.get_ton_wallet_ownership_proof_challenge` to get the challenge to sign.

            password (``str``, *optional*):
                Two-step verification password of the current user.

            anchor_public_key (``bytes``, *optional*):
                Original public key of the new wallet.

        Returns:
            :obj:`~pyrogram.types.TonWalletState`: On success, the state of the new wallet is returned.

        Example:
            .. code-block:: python

                state = await app.replace_ton_wallet(
                    types.TonWalletOwnershipProof(public_key=key, timestamp=ts, signature=sig),
                    password="password"
                )
        """
        return types.TonWalletState._parse(
            await self.invoke(
                raw.functions.wallet.ReplaceWallet(
                    wallet=raw.types.InputWalletImported(
                        public_key=proof.public_key,
                        proof=raw.types.WalletOwnershipProof(
                            timestamp=proof.timestamp,
                            signature=proof.signature
                        ),
                        anchor_public_key=anchor_public_key
                    ),
                    password=utils.compute_password_check(
                        await self.invoke(raw.functions.account.GetPassword()), password
                    ) if password is not None else None
                )
            )
        )
