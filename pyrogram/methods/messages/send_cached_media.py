from datetime import datetime
from typing import Union, List, Optional

import pyrogram
from pyrogram import raw, enums
from pyrogram import types
from pyrogram import utils

from ..ephemeral.as_ephemeral import as_ephemeral


class SendCachedMedia:
    async def send_cached_media(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        file_id: str,
        caption: str = "",
        parse_mode: Optional["enums.ParseMode"] = None,
        caption_entities: Optional[List["types.MessageEntity"]] = None,
        disable_notification: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
        reply_to_chat_id: Optional[Union[int, str]] = None,
        schedule_date: Optional[datetime] = None,
        protect_content: Optional[bool] = None,
        has_spoiler: Optional[bool] = None,
        quote_text: Optional[str] = None,
        quote_entities: Optional[List["types.MessageEntity"]] = None,
        reply_markup: Optional[Union[
            "types.InlineKeyboardMarkup",
            "types.ReplyKeyboardMarkup",
            "types.ReplyKeyboardRemove",
            "types.ForceReply"
        ]] = None,
        message_thread_id: Optional[int] = None,
        effect_id: Optional[int] = None,
        show_caption_above_media: Optional[bool] = None,
        reply_parameters: Optional["types.ReplyParameters"] = None,
        repeat_period: Optional[int] = None,
        business_connection_id: Optional[str] = None,
        allow_paid_broadcast: Optional[bool] = None,
        paid_message_star_count: Optional[int] = None,
        suggested_post_parameters: Optional["types.SuggestedPostParameters"] = None,
        direct_messages_topic_id: Optional[int] = None,
        background: Optional[bool] = None,
        clear_draft: Optional[bool] = None,
        update_stickersets_order: Optional[bool] = None,
        send_as: Optional[Union[int, str]] = None,
        quick_reply_shortcut: Optional[int] = None,
        ephemeral_message_parameters: Optional["types.EphemeralMessageParameters"] = None,
    ) -> Optional["types.Message"]:
        """Send any media stored on the Telegram servers using a file_id.

        This convenience method works with any valid file_id only.
        It does the same as calling the relevant method for sending media using a file_id, thus saving you from the
        hassle of using the correct method for the media the file_id is pointing to.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.
                For your personal cloud (Saved Messages) you can simply use "me" or "self".
                For a contact that exists in your Telegram address book you can use his phone number (str).

            file_id (``str``):
                Media to send.
                Pass a file_id as string to send a media that exists on the Telegram servers.

            caption (``str``, *optional*):
                Media caption, 0-1024 characters.

            parse_mode (:obj:`~pyrogram.enums.ParseMode`, *optional*):
                By default, texts are parsed using both Markdown and HTML styles.
                You can combine both syntaxes together.

            caption_entities (List of :obj:`~pyrogram.types.MessageEntity`):
                List of special entities that appear in the caption, which can be specified instead of *parse_mode*.

            disable_notification (``bool``, *optional*):
                Sends the message silently.
                Users will receive a notification with no sound.

            reply_to_message_id (``int``, *optional*):
                If the message is a reply, ID of the original message.

            message_thread_id (``int``, *optional*):
                Unique identifier for a forum topic in the chat.

            reply_parameters (:obj:`~pyrogram.types.ReplyParameters`, *optional*):
                Reply parameters for the message.

            schedule_date (:py:obj:`~datetime.datetime`, *optional*):
                Date when the message will be automatically sent.

            protect_content (``bool``, *optional*):
                Protects the contents of the sent message from forwarding and saving.

            effect_id (``int``, *optional*):
                Unique identifier of the effect to apply to the message.

            show_caption_above_media (``bool``, *optional*):
                Pass True to show the caption above the media.

            repeat_period (``int``, *optional*):
                Period in seconds for repeating the message.

            business_connection_id (``str``, *optional*):
                Business connection identifier.

            allow_paid_broadcast (``bool``, *optional*):
                Allow paid broadcast.

            paid_message_star_count (``int``, *optional*):
                Number of stars to charge for the paid message.

            suggested_post_parameters (:obj:`~pyrogram.types.SuggestedPostParameters`, *optional*):
                Parameters for the suggested post.

            direct_messages_topic_id (``int``, *optional*):
                If the message is a direct message, ID of the topic.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardRemove` | :obj:`~pyrogram.types.ForceReply`, *optional*):
                Additional interface options. An object for an inline keyboard, custom reply keyboard,
                instructions to remove reply keyboard or to force a reply from the user.

            reply_to_chat_id (``int`` | ``str``, *optional*):
                Unique identifier for the chat to which the replied message belongs.
                Only applicable in combination with *reply_to_message_id*.

            has_spoiler (``bool``, *optional*):
                Pass True if the message needs to be covered with a spoiler animation.

            quote_text (``str``, *optional*):
                Text of the quote to reply to.

            quote_entities (List of :obj:`~pyrogram.types.MessageEntity`):
                List of special entities that appear in *quote_text*, which can be specified instead of *parse_mode*.

            background (``bool``, *optional*):
                Send the message in background.

            clear_draft (``bool``, *optional*):
                Clear the draft of the chat.

            update_stickersets_order (``bool``, *optional*):
                Move the sticker set to the top of the list.

            send_as (``int`` | ``str``, *optional*):
                Unique identifier (int) or username (str) of the chat or channel to send the message as.

            quick_reply_shortcut (``int``, *optional*):
                Unique identifier of the quick reply shortcut the message belongs to.

            ephemeral_message_parameters (:obj:`~pyrogram.types.EphemeralMessageParameters`, *optional*):
                Send the message as an ephemeral message, visible only to the user it
                names and absent from the chat's history, rather than as an ordinary one.
                The ephemeral RPC has no field for *silent*, *background*, *clear_draft*,
                *schedule_date*, *repeat_period*, *send_as*, *effect_id*,
                *quick_reply_shortcut*, *allow_paid_broadcast*,
                *paid_message_star_count*, *suggested_post_parameters* or
                *update_stickersets_order*; any of those that is set is logged and
                dropped.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the sent media message is returned.

        Example:
            .. code-block:: python

                await app.send_cached_media("me", file_id)
        """

        if reply_parameters is None:
            if reply_to_message_id is not None:
                reply_parameters = types.ReplyParameters(
                    message_id=reply_to_message_id,
                    chat_id=reply_to_chat_id,
                    quote=quote_text,
                    quote_entities=quote_entities,
                )
            elif quote_text is not None:
                reply_parameters = types.ReplyParameters(
                    message_id=None,
                    chat_id=reply_to_chat_id,
                    quote=quote_text,
                    quote_entities=quote_entities,
                )

        text_params = await utils.parse_text_entities(self, caption, parse_mode, caption_entities)

        r = await self.invoke(
            await as_ephemeral(self, ephemeral_message_parameters, raw.functions.messages.SendMedia(
                peer=await self.resolve_peer(chat_id),
                media=utils.get_input_media_from_file_id(file_id, has_spoiler=has_spoiler),
                silent=disable_notification if disable_notification is not None else None,
                reply_to=await utils.get_reply_to(
                    self,
                    reply_parameters,
                    message_thread_id,
                    direct_messages_topic_id=direct_messages_topic_id
                ),
                random_id=self.rnd_id(),
                schedule_date=utils.datetime_to_timestamp(schedule_date),
                noforwards=protect_content,
                effect=effect_id,
                invert_media=show_caption_above_media if show_caption_above_media is not None else None,
                schedule_repeat_period=repeat_period,
                allow_paid_floodskip=allow_paid_broadcast if allow_paid_broadcast is not None else None,
                allow_paid_stars=paid_message_star_count if paid_message_star_count is not None else None,
                suggested_post=suggested_post_parameters.write() if suggested_post_parameters else None,
                reply_markup=await reply_markup.write(self) if reply_markup else None,
                background=background,
                clear_draft=clear_draft,
                update_stickersets_order=update_stickersets_order,
                send_as=await self.resolve_peer(send_as) if send_as is not None else None,
                quick_reply_shortcut=raw.types.InputQuickReplyShortcutId(shortcut_id=quick_reply_shortcut) if quick_reply_shortcut is not None else None,
                **text_params
            )),
            sleep_threshold=60,
            business_connection_id=business_connection_id
        )

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateNewMessage,
                              raw.types.UpdateNewChannelMessage,
                              raw.types.UpdateNewScheduledMessage,
                              raw.types.UpdateNewEphemeralMessage)):
                return await types.Message._parse(
                    self, i.message,
                    {i.id: i for i in r.users},
                    {i.id: i for i in r.chats},
                    is_scheduled=isinstance(i, raw.types.UpdateNewScheduledMessage)
                )
