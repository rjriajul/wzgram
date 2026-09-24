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
from pyrogram import raw, enums
from pyrogram import types
from pyrogram import utils
from .inline_session import invoke_inline


class EditInlineText:
    async def edit_inline_text(
        self: "pyrogram.Client",
        inline_message_id: str,
        text: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        link_preview_options: Optional["types.LinkPreviewOptions"] = None,
        disable_web_page_preview: Optional[bool] = None,
        show_caption_above_media: Optional[bool] = None,
        rich_text: Optional[Union[str, "types.InputRichMessage"]] = None,
        rich_text_parse_mode: "enums.ParseMode" = enums.ParseMode.MARKDOWN,
        rich_text_media: Optional[List["types.InputRichMessageMedia"]] = None,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        business_connection_id: Optional[str] = None,
    ) -> bool:
        """Edit the text of inline messages.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            inline_message_id (``str``):
                Identifier of the inline message.

            text (``str``, *optional*):
                New text of the message. Required if *rich_text* is not given,
                and ignored when it is.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes together.

            entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in the new text, which can be specified instead of
                *parse_mode*.

            link_preview_options (:obj:`~pyrogram.types.LinkPreviewOptions`, *optional*):
                Link preview generation options for the message.

            disable_web_page_preview (``bool``, *optional*):
                Disables link previews for links in this message.

            rich_text (``str`` | :obj:`~pyrogram.types.InputRichMessage`, *optional*):
                New rich content of the message, as Markdown or HTML text or as a whole
                :obj:`~pyrogram.types.InputRichMessage`. Replaces *text*.

            rich_text_parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                Parse mode for *rich_text*. Defaults to Markdown.
                Ignored when *rich_text* is an :obj:`~pyrogram.types.InputRichMessage`.

            rich_text_media (List of :obj:`~pyrogram.types.InputRichMessageMedia`, *optional*):
                Media *rich_text* refers to through ``tg://photo?id=``, ``tg://video?id=``
                or ``tg://audio?id=`` links.
                Ignored when *rich_text* is an :obj:`~pyrogram.types.InputRichMessage`.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An InlineKeyboardMarkup object.
                Pass None to remove the existing reply markup.

            show_caption_above_media (``bool``, *optional*):
                Pass True, if the caption must be shown above the message media.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

        Returns:
            ``bool``: On success, True is returned.

        Example:
            .. code-block:: python

                # Bots only

                # Simple edit text
                await app.edit_inline_text(inline_message_id, "new text")

                # Take the same text message, remove the web page preview only
                await app.edit_inline_text(
                    inline_message_id, message.text,
                    disable_web_page_preview=True)
        """

        if text is None and rich_text is None:
            raise ValueError("Either text or rich_text must be given")

        unpacked = utils.unpack_inline_message_id(inline_message_id)
        dc_id = unpacked.dc_id

        if link_preview_options is None:
            link_preview_options = self.link_preview_options

        no_webpage = None
        invert_media = None

        if link_preview_options is not None:
            if link_preview_options.is_disabled:
                no_webpage = True
            if link_preview_options.show_above_text:
                invert_media = True

        if disable_web_page_preview is not None:
            no_webpage = disable_web_page_preview

        if invert_media is None and show_caption_above_media is not None:
            invert_media = show_caption_above_media

        if rich_text is not None:
            text_params = {
                "message": "",
                "rich_message": await utils.build_input_rich_message(
                    self, rich_text, rich_text_parse_mode, rich_text_media
                )
            }
        else:
            text_params = await utils.parse_text_entities(self, text, parse_mode, entities)

        return await invoke_inline(
            self, dc_id,
            raw.functions.messages.EditInlineBotMessage(
                id=unpacked,
                no_webpage=no_webpage,
                invert_media=invert_media,
                media=raw.types.InputMediaWebPage(
                    url=link_preview_options.url,
                    force_large_media=link_preview_options.prefer_large_media,
                    force_small_media=link_preview_options.prefer_small_media,
                    optional=True
                ) if link_preview_options is not None and link_preview_options.url else None,
                reply_markup=await utils.write_edit_reply_markup(self, reply_markup=reply_markup),
                **text_params
            ),
            business_connection_id
        )
