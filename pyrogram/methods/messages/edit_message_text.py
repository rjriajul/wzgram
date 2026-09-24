from datetime import datetime
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
        text: Optional[str] = None,
        parse_mode: Optional["enums.ParseMode"] = None,
        entities: Optional[List["types.MessageEntity"]] = None,
        link_preview_options: Optional["types.LinkPreviewOptions"] = None,
        show_caption_above_media: Optional[bool] = None,
        disable_web_page_preview: Optional[bool] = None,
        business_connection_id: Optional[str] = None,
        rich_text: Optional[Union[str, "types.InputRichMessage"]] = None,
        rich_text_parse_mode: "enums.ParseMode" = enums.ParseMode.MARKDOWN,
        rich_text_media: Optional[List["types.InputRichMessageMedia"]] = None,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        schedule_date: Optional[datetime] = None,
        repeat_period: Optional[int] = None,
        quick_reply_shortcut: Optional[int] = None,
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

            rich_text (``str`` | :obj:`~pyrogram.types.InputRichMessage`, *optional*):
                Rich text (Markdown or HTML) to render a styled message. Overrides ``text``.

            rich_text_parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                Parse mode for ``rich_text``. Defaults to Markdown.
                Ignored when ``rich_text`` is an :obj:`~pyrogram.types.InputRichMessage`.

            rich_text_media (List of :obj:`~pyrogram.types.InputRichMessageMedia`, *optional*):
                Media ``rich_text`` refers to through ``tg://photo?id=``,
                ``tg://video?id=`` or ``tg://audio?id=`` links.
                Ignored when ``rich_text`` is an :obj:`~pyrogram.types.InputRichMessage`.


            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An inline keyboard for the message.
                Pass None to remove the existing reply markup.

            schedule_date (:py:obj:`~datetime.datetime`, *optional*):
                New date when the scheduled message will be sent.

            repeat_period (``int``, *optional*):
                New period in seconds for the message to be sent repeatedly.

            quick_reply_shortcut (``int``, *optional*):
                Unique identifier of the quick reply shortcut the message belongs to.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the edited message is returned.

        Example:
            .. code-block:: python

                # Edit a message text
                await app.edit_message_text(chat_id, message_id, "New text")
        """
        if text is None and rich_text is None:
            raise ValueError("Either text or rich_text must be given")

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
            text_params = {
                "message": "",
                "rich_message": await utils.build_input_rich_message(
                    self, rich_text, rich_text_parse_mode, rich_text_media, chat_id
                )
            }
        else:
            text_params = await utils.parse_text_entities(self, text, parse_mode, entities)

        r = await self.invoke(
            raw.functions.messages.EditMessage(
                schedule_date=utils.datetime_to_timestamp(schedule_date),
                schedule_repeat_period=repeat_period,
                quick_reply_shortcut_id=quick_reply_shortcut,
                peer=await self.resolve_peer(chat_id),
                id=message_id,
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
