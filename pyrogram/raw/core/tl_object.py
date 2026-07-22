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

import importlib
from io import BytesIO
from json import dumps
from typing import cast, List, Any, Union, Dict

from ..all import objects

_legacy_objects: Dict[int, str] = {
    0xf2355507: "pyrogram.raw.types.ChannelFull",
    0xc9d31138: "pyrogram.raw.types.ChatFull",
    0x31774388: "pyrogram.raw.types.User",
}


class TLObject:
    __slots__: List[str] = []

    QUALNAME = "Base"

    @classmethod
    def read(cls, b: BytesIO, *args: Any) -> Any:
        constructor_id = int.from_bytes(b.read(4), "little")

        try:
            obj_class = objects[constructor_id]
        except KeyError as e:
            path = _legacy_objects.get(constructor_id)

            if path is None:
                raise KeyError(constructor_id) from e

            module_path, class_name = path.rsplit(".", 1)
            obj_class = getattr(importlib.import_module(module_path), class_name)

        return cast(TLObject, obj_class).read(b, *args)

    def write(self, *args: Any) -> bytes:
        pass

    @staticmethod
    def default(obj: "TLObject") -> Union[str, Dict[str, str]]:
        if isinstance(obj, bytes):
            return repr(obj)

        return {
            "_": obj.QUALNAME,
            **{
                attr: getattr(obj, attr)
                for attr in obj.__slots__
                if getattr(obj, attr) is not None
            }
        }

    def __str__(self) -> str:
        return dumps(self, indent=4, default=TLObject.default, ensure_ascii=False)

    def __repr__(self) -> str:
        if not hasattr(self, "QUALNAME"):
            return repr(self)

        return "pyrogram.raw.{}({})".format(
            self.QUALNAME,
            ", ".join(
                f"{attr}={repr(getattr(self, attr))}"
                for attr in self.__slots__
                if getattr(self, attr) is not None
            )
        )

    def __eq__(self, other: Any) -> bool:
        for attr in self.__slots__:
            try:
                if getattr(self, attr) != getattr(other, attr):
                    return False
            except AttributeError:
                return False

        return True

    def __len__(self) -> int:
        return len(self.write())

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        pass
