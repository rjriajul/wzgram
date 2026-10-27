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

from datetime import datetime

from pyrogram import raw, utils

from ..object import Object


class TonWalletOwnershipProofChallenge(Object):
    """A challenge to sign to prove ownership of a TON wallet.

    Parameters:
        payload (``str``):
            Payload of the challenge.

        domain (``str``):
            Domain of the proof requester.

        expiration_date (:py:obj:`~datetime.datetime`):
            Date the challenge expires.
    """

    def __init__(self, *, payload: str, domain: str, expiration_date: datetime):
        super().__init__()

        self.payload = payload
        self.domain = domain
        self.expiration_date = expiration_date

    @staticmethod
    def _parse(challenge: "raw.types.wallet.ProofChallenge") -> "TonWalletOwnershipProofChallenge":
        return TonWalletOwnershipProofChallenge(
            payload=challenge.payload,
            domain=challenge.domain,
            expiration_date=utils.timestamp_to_datetime(challenge.expires)
        )
