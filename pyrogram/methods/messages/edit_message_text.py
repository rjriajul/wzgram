from typing import Union, List, Optional

import pyrogram
from pyrogram import raw, enums
from pyrogram import types
from pyrogram import utils


class EditMessageText:
    async def edit_message_text(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional["enums.ParseMode"] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        link_preview_options: Optional["types.LinkPreviewOptions"] = None,
        show_caption_above_media: Optional[bool] = None,
        disable_web_page_preview: Optional[bool] = None,
        business_connection_id: Optional[str] = None,
        rich_text: Optional[str] = None,
        rich_text_parse_mode: "enums.ParseMode" = enums.ParseMode.MARKDOWN,
        reply_markup: Optional["types.InlineKeyboardMarkup"] = None,
    ) -> "types.Message":
        """Edit the text of a message.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            message_id (``int``):
                Unique identifier of the message to edit.

            text (``str``):
                New text of the message. If ``rich_text`` is provided, this is ignored.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes.

            entities (List of :obj:`~pyrogram.types.MessageEntity`, *optional*):
                List of special entities that appear in message text, which can be specified
                instead of *parse_mode*.

            link_preview_options (:obj:`~pyrogram.types.LinkPreviewOptions`, *optional*):
                Link preview generation options for the message.

            show_caption_above_media (``bool``, *optional*):
                Pass True to show the caption above the media.

            disable_web_page_preview (``bool``, *optional*):
                Disables link previews for links in this message.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

            rich_text (``str``, *optional*):
                Rich text (Markdown or HTML) to render a styled message. Overrides ``text``.

            rich_text_parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                Parse mode for ``rich_text``. Defaults to Markdown.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An inline keyboard for the message.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the edited message is returned.

        Example:
            .. code-block:: python

                # Edit a message text
                await app.edit_message_text(chat_id, message_id, "New text")
        """
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
            no_webpage = disable_web_page_preview if disable_web_page_preview is not None else None

        invert_media = invert_media if invert_media is not None else (show_caption_above_media if show_caption_above_media is not None else None)

        if rich_text is not None:
            if rich_text_parse_mode == enums.ParseMode.HTML:
                rich_msg = raw.types.InputRichMessageHTML(html=rich_text)
            else:
                rich_msg = raw.types.InputRichMessageMarkdown(markdown=rich_text)
            text_params = {"message": "", "rich_message": rich_msg}
        else:
            text_params = await utils.parse_text_entities(self, text, parse_mode, entities)

        r = await self.invoke(
            raw.functions.messages.EditMessage(
                peer=await self.resolve_peer(chat_id),
                id=message_id,
                no_webpage=no_webpage,
                invert_media=invert_media,
                reply_markup=await reply_markup.write(self) if reply_markup else None,
                **text_params
            ),
            sleep_threshold=60,
            business_connection_id=business_connection_id
        )

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateEditMessage, raw.types.UpdateEditChannelMessage, raw.types.UpdateEditEphemeralMessage)):
                return await types.Message._parse(
                    self, i.message,
                    {i.id: i for i in r.users},
                    {i.id: i for i in r.chats}
                )
