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
from typing import Optional

from pyrogram import raw, utils

from ..object import Object


class TonConnectRequest(Object):
    """A request from a dApp received through TON Connect.

    Parameters:
        session_id (``int``):
            Unique identifier of the TON Connect session.

        expiration_date (:py:obj:`~datetime.datetime`):
            Date the request expires.

        is_accepted (``bool``, *optional*):
            True, if the request was accepted.

        is_declined (``bool``, *optional*):
            True, if the request was declined.

        dapp_name (``str``, *optional*):
            Name of the dApp.

        topic (``str``, *optional*):
            Topic of the request.

        trace_id (``str``, *optional*):
            Identifier to trace the request.
    """

    def __init__(
        self,
        *,
        session_id: int,
        expiration_date: datetime,
        is_accepted: Optional[bool] = None,
        is_declined: Optional[bool] = None,
        dapp_name: Optional[str] = None,
        topic: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        super().__init__()

        self.session_id = session_id
        self.expiration_date = expiration_date
        self.is_accepted = is_accepted
        self.is_declined = is_declined
        self.dapp_name = dapp_name
        self.topic = topic
        self.trace_id = trace_id

    @staticmethod
    def _parse(action: "raw.types.MessageActionWalletTonConnectRequest") -> "TonConnectRequest":
        return TonConnectRequest(
            session_id=action.session_id,
            expiration_date=utils.timestamp_to_datetime(action.expires),
            is_accepted=action.accepted,
            is_declined=action.declined,
            dapp_name=action.dapp_name,
            topic=action.topic,
            trace_id=action.trace_id
        )
