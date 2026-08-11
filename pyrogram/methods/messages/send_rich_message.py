from datetime import datetime
from typing import Union, Optional

import pyrogram
from pyrogram import raw, utils, enums
from pyrogram import types


class SendRichMessage:
    async def send_rich_message(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        rich_text: str,
        parse_mode: Optional["enums.ParseMode"] = None,
        disable_web_page_preview: Optional[bool] = None,
        disable_notification: Optional[bool] = None,
        effect_id: Optional[int] = None,
        protect_content: Optional[bool] = None,
        reply_parameters: Optional["types.ReplyParameters"] = None,
        reply_markup: Optional[Union[
            "types.InlineKeyboardMarkup",
            "types.ReplyKeyboardMarkup",
            "types.ReplyKeyboardRemove",
            "types.ForceReply"
        ]] = None,
        message_thread_id: Optional[int] = None,
        schedule_date: Optional[datetime] = None,
        business_connection_id: Optional[str] = None,
    ) -> "types.Message":
        """Send a rich formatted message.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            rich_text (``str``):
                Rich text (Markdown or HTML) to render a styled message.
                See `rich message formatting options <https://core.telegram.org/bots/api#rich-message-formatting-options>`__ for details.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes together.

            disable_web_page_preview (``bool``, *optional*):
                Disables link previews for links in this message.

            disable_notification (``bool``, *optional*):
                Sends the message silently. Users will receive a notification with no sound.

            effect_id (``int``, *optional*):
                Unique identifier of the effect to apply to the message.

            protect_content (``bool``, *optional*):
                Pass True to protect the message content from being forwarded.

            reply_parameters (:obj:`~pyrogram.types.ReplyParameters`, *optional*):
                Description of the reply-to message.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardRemove` | :obj:`~pyrogram.types.ForceReply`, *optional*):
                Additional interface options.

            message_thread_id (``int``, *optional*):
                Unique identifier for a message thread in a forum topic.

            schedule_date (:py:obj:`~datetime.datetime`, *optional*):
                Date when the message will be automatically sent.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the sent rich message is returned.

        Example:
            .. code-block:: python

                # Send a rich formatted message
                await app.send_rich_message(chat_id, "<b>Hello</b> <i>world</i>!")
        """
        if parse_mode == enums.ParseMode.HTML or parse_mode is None:
            rich_message = raw.types.InputRichMessageHTML(
                html=rich_text,
            )
        else:
            rich_message = raw.types.InputRichMessageMarkdown(
                markdown=rich_text,
            )

        r = await self.invoke(
            raw.functions.messages.SendMessage(
                peer=await self.resolve_peer(chat_id),
                message="",
                random_id=self.rnd_id(),
                no_webpage=disable_web_page_preview if disable_web_page_preview is not None else None,
                silent=disable_notification if disable_notification is not None else None,
                noforwards=protect_content,
                effect=effect_id,
                reply_to=await utils.get_reply_to(
                    self,
                    reply_parameters,
                    message_thread_id,
                ),
                reply_markup=await reply_markup.write(self) if reply_markup else None,
                schedule_date=utils.datetime_to_timestamp(schedule_date),
                rich_message=rich_message,
            ),
            sleep_threshold=60,
            business_connection_id=business_connection_id,
        )

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateNewMessage,
                              raw.types.UpdateNewChannelMessage,
                              raw.types.UpdateNewScheduledMessage)):
                return await types.Message._parse(
                    self, i.message,
                    {i.id: i for i in r.users},
                    {i.id: i for i in r.chats},
                    is_scheduled=isinstance(i, raw.types.UpdateNewScheduledMessage)
                )
