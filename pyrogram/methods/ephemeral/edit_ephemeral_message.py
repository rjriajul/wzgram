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

from typing import List, Optional, Union

import pyrogram
from pyrogram import raw, types, utils


async def edit_ephemeral(
    client: "pyrogram.Client",
    chat_id: Union[int, str],
    receiver_id: Union[int, str],
    message_id: int,
    *,
    message: Optional[str] = None,
    entities: Optional[List["raw.base.MessageEntity"]] = None,
    media: Optional["raw.base.InputMedia"] = None,
    rich_message: Optional["raw.base.InputRichMessage"] = None,
    reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
    show_caption_above_media: Optional[bool] = None,
    welcome: Optional[bool] = None,
) -> Optional["types.Message"]:
    """One ephemeral.editMessage for the four methods that edit one.

    They differ only in which of its optional fields they fill, and the update the
    answer carries is UpdateEditEphemeralMessage rather than UpdateEditMessage.
    """

    r = await client.invoke(
        raw.functions.ephemeral.EditMessage(
            peer=await client.resolve_peer(chat_id),
            receiver_id=await client.resolve_peer(receiver_id),
            id=message_id,
            message=message,
            entities=entities or None,
            media=media,
            rich_message=rich_message,
            reply_markup=await utils.write_edit_reply_markup(client, reply_markup=reply_markup),
            invert_media=show_caption_above_media,
            welcome=welcome,
        )
    )

    for update in getattr(r, "updates", []):
        if isinstance(update, raw.types.UpdateEditEphemeralMessage):
            return await types.Message._parse(
                client=client,
                message=update.message,
                users={i.id: i for i in getattr(r, "users", [])},
                chats={i.id: i for i in getattr(r, "chats", [])},
            )

    return None
