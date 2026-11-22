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
from pyrogram import enums, raw, types, utils


async def _send_widget_media(
    client: "pyrogram.Client",
    chat_id: Union[int, str],
    media: "raw.base.InputMedia",
    caption: Optional[str],
    parse_mode: Optional["enums.ParseMode"],
    caption_entities: Optional[List["types.MessageEntity"]],
    show_caption_above_media: Optional[bool],
    disable_notification: Optional[bool],
    protect_content: Optional[bool],
    allow_paid_broadcast: Optional[bool],
    effect_id: Optional[int],
    reply_parameters: Optional["types.ReplyParameters"],
    message_thread_id: Optional[int],
    reply_markup,
) -> Optional["types.Message"]:
    message, entities = (await utils.parse_text_entities(client, caption, parse_mode, caption_entities)).values()

    r = await client.invoke(
        raw.functions.messages.SendMedia(
            peer=await client.resolve_peer(chat_id),
            media=media,
            silent=disable_notification or None,
            reply_to=await utils.get_reply_to(client, reply_parameters, message_thread_id),
            random_id=client.rnd_id(),
            noforwards=protect_content,
            allow_paid_floodskip=allow_paid_broadcast,
            effect=effect_id,
            invert_media=show_caption_above_media,
            reply_markup=await reply_markup.write(client) if reply_markup else None,
            message=message or "",
            entities=entities,
        )
    )

    for i in r.updates:
        if isinstance(i, (raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage)):
            return await types.Message._parse(
                client, i.message,
                {i.id: i for i in r.users},
                {i.id: i for i in r.chats},
            )


class SendWidget:
    async def send_widget(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        html: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        public_data: Optional[str] = None,
        chat_data: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        show_caption_above_media: Optional[bool] = None,
        allow_queries: Optional[bool] = None,
        is_shared: Optional[bool] = None,
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
        """Send a message with an HTML widget.

        Currently, in the production environment, widgets can be sent only to private chats,
        and sent widgets automatically have protected content and therefore can't be forwarded.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            html (``str``):
                HTML code of the widget, 1-32768 bytes.
                The code must not exceed 4096 bytes when compressed by zlib with the maximum compression level.

            width (``int``, *optional*):
                Width of the widget in logical pixels; omit if the widget must occupy the whole width of the message bubble.
                The width is clamped by the app to the range from 200 to the maximum width of the message bubble.

            height (``int``, *optional*):
                Height of the widget in logical pixels; omit if the height of the widget isn't fixed.
                The height is clamped by the app to the range 50-600.

            public_data (``str``, *optional*):
                Public data of the widget, 0-1024 bytes, which will be available wherever the widget is shown.
                If the widget is shared, then all messages with it will have the same public data.

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

            allow_queries (``bool``, *optional*):
                Pass True to allow the widget to send queries to the bot.

            is_shared (``bool``, *optional*):
                Pass True to create a shared widget, which can be sent again using :meth:`~pyrogram.Client.send_shared_widget`.

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

                await app.send_widget(chat_id, "<b>Hello</b>", height=120, allow_queries=True)
        """
        return await _send_widget_media(
            self, chat_id,
            raw.types.InputMediaWidget(
                allow_queries=allow_queries,
                shared_widget=is_shared,
                width=width or 0,
                height=height or 0,
                html=html,
                public_data=public_data,
                chat_data=chat_data,
            ),
            caption, parse_mode, caption_entities, show_caption_above_media, disable_notification,
            protect_content, allow_paid_broadcast, effect_id, reply_parameters, message_thread_id, reply_markup,
        )
