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

from pyrogram import raw

from ..object import Object


class ShareThemeBackdrop(Object):
    """A backdrop that can be used in a :obj:`~pyrogram.types.ShareTheme`.

    Parameters:
        id (``int``):
            Identifier of the backdrop.

        name (``str``):
            Name of the backdrop.

        center_color (``int``):
            Color of the center of the backdrop, in RGB format.

        edge_color (``int``):
            Color of the edges of the backdrop, in RGB format.

        pattern_color (``int``):
            Color of the pattern, in RGB format.

        text_color (``int``):
            Color of the text, in RGB format.
    """

    def __init__(
        self,
        *,
        id: int,
        name: str,
        center_color: int,
        edge_color: int,
        pattern_color: int,
        text_color: int
    ):
        super().__init__()

        self.id = id
        self.name = name
        self.center_color = center_color
        self.edge_color = edge_color
        self.pattern_color = pattern_color
        self.text_color = text_color

    @staticmethod
    def _parse(backdrop: "raw.types.ShareThemeBackdropOption") -> "ShareThemeBackdrop":
        return ShareThemeBackdrop(
            id=backdrop.backdrop_id,
            name=backdrop.name,
            center_color=backdrop.center_color,
            edge_color=backdrop.edge_color,
            pattern_color=backdrop.pattern_color,
            text_color=backdrop.text_color
        )
