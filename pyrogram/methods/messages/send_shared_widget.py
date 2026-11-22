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
from pyrogram import enums, raw, types

from .send_widget import _send_widget_media


class SendSharedWidget:
    async def send_shared_widget(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        widget_id: str,
        chat_data: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        show_caption_above_media: Optional[bool] = None,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = None,
        allow_paid_broadcast: Optional[bool] = None,
        effect_id: Optional[int] = None,
        reply_parameters: Optional["types.ReplyParameters"] = None,
        message_thread_id: Optional[int] = None,
        reply_markup: Optional[Union[
            "types.InlineKeyboardMarkup",
            "types.ReplyKeyboardMarkup",
            "types.ReplyKeyboardRemove",
            "types.ForceReply"
        ]] = None,
    ) -> Optional["types.Message"]:
        """Send again a shared widget created by the bot.

        Currently, in the production environment, widgets can be sent only to private chats,
        and sent widgets automatically have protected content and therefore can't be forwarded.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            widget_id (``str``):
                Unique identifier of the shared widget.

            chat_data (``str``, *optional*):
                Data of the widget, which is specific to the message, 0-1024 bytes.

            caption (``str``, *optional*):
                Widget caption, 0-1024 characters after entities parsing.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes together.

            caption_entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in the caption, which can be specified instead of *parse_mode*.

            show_caption_above_media (``bool``, *optional*):
                Pass True if the caption must be shown above the widget.

            disable_notification (``bool``, *optional*):
                Sends the message silently. Users will receive a notification with no sound.

            protect_content (``bool``, *optional*):
                Protects the contents of the sent message from forwarding and saving.

            allow_paid_broadcast (``bool``, *optional*):
                Pass True to allow up to 1000 messages per second, ignoring broadcasting limits
                for a fee of 0.1 Telegram Stars per message.

            effect_id (``int``, *optional*):
                Unique identifier of the message effect to be added to the message; for private chats only.

            reply_parameters (:obj:`~pyrogram.types.ReplyParameters`, *optional*):
                Description of the message to reply to.

            message_thread_id (``int``, *optional*):
                Unique identifier for the target message thread (topic) of a forum.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardRemove` | :obj:`~pyrogram.types.ForceReply`, *optional*):
                Additional interface options.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the sent message is returned.

        Example:
            .. code-block:: python

                await app.send_shared_widget(chat_id, message.widget.id)
        """
        return await _send_widget_media(
            self, chat_id,
            raw.types.InputMediaWidgetId(widget_id=int(widget_id), chat_data=chat_data),
            caption, parse_mode, caption_entities, show_caption_above_media, disable_notification,
            protect_content, allow_paid_broadcast, effect_id, reply_parameters, message_thread_id, reply_markup,
        )
