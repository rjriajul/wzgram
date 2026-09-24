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
from typing import List, Optional, Union

import pyrogram
from pyrogram import enums, raw, types, utils

from .edit_ephemeral_message import edit_ephemeral

log = logging.getLogger(__name__)


class EditEphemeralMessageText:
    async def edit_ephemeral_message_text(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        receiver_id: Union[int, str],
        message_id: int,
        text: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        rich_text: Optional[Union[str, "types.InputRichMessage"]] = None,
        rich_text_parse_mode: "enums.ParseMode" = enums.ParseMode.MARKDOWN,
        rich_text_media: Optional[List["types.InputRichMessageMedia"]] = None,
        rich_message: Optional["types.InputRichMessage"] = None,
        link_preview_options: Optional["types.LinkPreviewOptions"] = None,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        welcome: Optional[bool] = None,
    ) -> Optional["types.Message"]:
        """Edit the text of an ephemeral message.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            receiver_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the user the ephemeral
                message was sent to.

            message_id (``int``):
                Identifier of the ephemeral message to edit.

            text (``str``, *optional*):
                New text of the message. Required if *rich_text* is not given.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes.

            entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in message text, which can be
                specified instead of *parse_mode*.

            rich_text (``str`` | :obj:`~pyrogram.types.InputRichMessage`, *optional*):
                Rich content to send, as Markdown or HTML text or as a whole
                :obj:`~pyrogram.types.InputRichMessage`.

            rich_text_parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                Parse mode for *rich_text*. Defaults to Markdown.
                Ignored when *rich_text* is an :obj:`~pyrogram.types.InputRichMessage`.

            rich_text_media (List of :obj:`~pyrogram.types.InputRichMessageMedia`, *optional*):
                Media *rich_text* refers to through ``tg://photo?id=``, ``tg://video?id=``
                or ``tg://audio?id=`` links.
                Ignored when *rich_text* is an :obj:`~pyrogram.types.InputRichMessage`.

            rich_message (:obj:`~pyrogram.types.InputRichMessage`, *optional*):
                Deprecated alias of *rich_text*.

            link_preview_options (:obj:`~pyrogram.types.LinkPreviewOptions`, *optional*):
                Options used for link preview generation for the message.
                ``ephemeral.editMessage`` has no flag to turn a preview off, so
                *is_disabled* has no effect here.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An inline keyboard.
                Pass None to remove the existing reply markup.

            welcome (``bool``, *optional*):
                Pass True when editing a stored welcome message rather than one that was
                delivered once.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the edited message is returned.

        Example:
            .. code-block:: python

                await app.edit_ephemeral_message_text(
                    chat_id, receiver_id, message_id, "New text"
                )
        """
        if rich_message is not None:
            log.warning(
                "`rich_message` is deprecated and will be removed in future updates. "
                "Use `rich_text` instead."
            )

            if rich_text is None:
                rich_text = rich_message

        if rich_text is not None:
            return await edit_ephemeral(
                self, chat_id, receiver_id, message_id,
                rich_message=await utils.build_input_rich_message(
                    self, rich_text, rich_text_parse_mode, rich_text_media, chat_id
                ),
                reply_markup=reply_markup,
                welcome=welcome,
            )

        message, parsed_entities = (
            await utils.parse_text_entities(self, text, parse_mode, entities)
        ).values()

        return await edit_ephemeral(
            self, chat_id, receiver_id, message_id,
            message=message,
            entities=parsed_entities,
            media=raw.types.InputMediaWebPage(
                url=link_preview_options.url,
                force_large_media=link_preview_options.prefer_large_media,
                force_small_media=link_preview_options.prefer_small_media,
                optional=True
            ) if link_preview_options is not None and link_preview_options.url else None,
            reply_markup=reply_markup,
            welcome=welcome,
        )
