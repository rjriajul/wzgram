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

import logging
from typing import Union, List, Optional

import pyrogram
from pyrogram import raw, types, utils, enums

log = logging.getLogger(__name__)


class SendEphemeralMessage:
    async def send_ephemeral_message(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        receiver_id: Union[int, str],
        text: str,
        parse_mode: Optional["enums.ParseMode"] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        reply_parameters: Optional["types.ReplyParameters"] = None,
        reply_markup: Optional[Union[
            "types.InlineKeyboardMarkup",
            "types.ReplyKeyboardMarkup",
            "types.ReplyKeyboardRemove",
            "types.ForceReply"
        ]] = None,
        query_id: Optional[int] = None,
        rich_text: Optional[str] = None,
        rich_text_parse_mode: "enums.ParseMode" = enums.ParseMode.MARKDOWN,
        disable_web_page_preview: Optional[bool] = None,
    ) -> "types.Message":
        """Send an ephemeral message visible only to a specific user and the bot in a group.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            receiver_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user who will receive the ephemeral message.

            text (``str``):
                Text of the message to be sent. If ``rich_text`` is provided, this is ignored.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes.

            entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in message text, which can be specified
                instead of *parse_mode*.

            reply_parameters (:obj:`~pyrogram.types.ReplyParameters`, *optional*):
                Description of the reply-to message.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardRemove` | :obj:`~pyrogram.types.ForceReply`, *optional*):
                Additional interface options. An object for an inline keyboard, custom reply keyboard,
                instructions to remove reply keyboard or to force a reply from the user.

            query_id (``int``, *optional*):
                Identifier of the guest query to respond to, if this message is a reply to a guest bot query.

            rich_text (``str``, *optional*):
                Rich text (Markdown or HTML) to render a styled message. Overrides ``text``.

            rich_text_parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                Parse mode for ``rich_text``. Defaults to Markdown.

            disable_web_page_preview (``bool``, *optional*):
                Ignored. The ephemeral message RPC has no link preview field,
                so this cannot be honoured. Kept only for backwards compatibility.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the sent ephemeral message is returned.

        Example:
            .. code-block:: python

                # Send an ephemeral message to a specific user
                await app.send_ephemeral_message(chat_id, user_id, "Hello!")
        """
        if rich_text is not None:
            if rich_text_parse_mode == enums.ParseMode.HTML:
                rich_message = raw.types.InputRichMessageHTML(
                    html=rich_text,
                )
            else:
                rich_message = raw.types.InputRichMessageMarkdown(
                    markdown=rich_text,
                )

            r = await self.invoke(
                raw.functions.ephemeral.SendMessage(
                    peer=await self.resolve_peer(chat_id),
                    receiver_id=await self.resolve_peer(receiver_id),
                    message="",
                    random_id=self.rnd_id(),
                    reply_to=await utils.get_reply_to(self, reply_parameters),
                    reply_markup=await reply_markup.write(self) if reply_markup else None,
                    rich_message=rich_message,
                    query_id=query_id,
                )
            )
        else:
            plain_text, entities = (await utils.parse_text_entities(self, text, parse_mode, entities)).values()

            r = await self.invoke(
                raw.functions.ephemeral.SendMessage(
                    peer=await self.resolve_peer(chat_id),
                    receiver_id=await self.resolve_peer(receiver_id),
                    message=plain_text,
                    random_id=self.rnd_id(),
                    entities=entities or None,
                    reply_to=await utils.get_reply_to(self, reply_parameters),
                    reply_markup=await reply_markup.write(self) if reply_markup else None,
                    query_id=query_id,
                )
            )

        for u in getattr(r, "updates", []):
            if isinstance(u, raw.types.UpdateNewEphemeralMessage):
                return await types.Message._parse(
                    client=self,
                    message=u.message,
                    users={i.id: i for i in getattr(r, "users", [])},
                    chats={i.id: i for i in getattr(r, "chats", [])},
                )

        return None
