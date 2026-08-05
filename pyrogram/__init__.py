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

"""wzgram - Elegant, modern and asynchronous Telegram MTProto API framework.

wzgram is a fork of Pyrogram providing support for the latest Telegram features
including Gifts, Stories, Topics, Business Accounts, and more.
"""

__version__ = "3.0.26"
__license__ = "GNU Lesser General Public License v3.0 (LGPL-3.0)"
__copyright__ = "Copyright (C) 2017-present Dan <https://github.com/delivrance>"
__fork__ = "wzgram by rjriajul <https://github.com/rjriajul/wzgram>"
__contributors__ = [
    "SilentDemonSD <https://github.com/SilentDemonSD>",
]


class StopTransmission(Exception):
    pass


class StopPropagation(StopAsyncIteration):
    pass


class ContinuePropagation(StopAsyncIteration):
    pass


from . import raw, types, filters, handlers, enums
from .client import Client
from .methods.utilities.idle import idle
from .methods.utilities.compose import compose
from .methods.rate_limiter import RateLimiter, TokenBucket
