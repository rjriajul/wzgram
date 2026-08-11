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

from pyrogram import raw

from ..object import Object


class InputRichMessageMedia(Object):
    """Describes media referenced in a rich message.

    When constructing a rich message using blocks (e.g., :class:`InputRichBlockPhoto`,
    :class:`InputRichBlockVideo`, :class:`InputRichBlockAudio`), the actual
    media payloads (photos, documents, users) must be provided separately.
    This object groups them together so they can be attached to an
    :class:`InputRichMessage` via the *media* parameter.

    .. note::

        Media objects in these lists are referenced by their ``id`` field
        from the corresponding block objects (e.g., the ``photo_id`` of an
        :class:`InputRichBlockPhoto` must match the ``id`` attribute of the
        :class:`~pyrogram.raw.types.InputPhoto` in this list).

    Parameters:
        photos (List of :obj:`~pyrogram.raw.base.InputPhoto`, *optional*):
            Photos referenced by blocks.

        documents (List of :obj:`~pyrogram.raw.base.InputDocument`, *optional*):
            Documents referenced by blocks.

        users (List of :obj:`~pyrogram.raw.base.InputUser`, *optional*):
            Users referenced by blocks.
    """

    def __init__(
        self,
        photos: Optional[List["raw.base.InputPhoto"]] = None,
        documents: Optional[List["raw.base.InputDocument"]] = None,
        users: Optional[List["raw.base.InputUser"]] = None,
    ):
        super().__init__()

        self.photos = photos
        self.documents = documents
        self.users = users

    def write(self) -> tuple:
        return (self.photos, self.documents, self.users)
