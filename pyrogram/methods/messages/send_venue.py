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

from datetime import datetime
from typing import Union, List, Optional

import pyrogram
from pyrogram import raw, utils
from pyrogram import types

from ..ephemeral.as_ephemeral import as_ephemeral


class SendVenue:
    async def send_venue(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        latitude: float,
        longitude: float,
        title: str,
        address: str,
        foursquare_id: str = "",
        foursquare_type: str = "",
        disable_notification: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
        reply_to_chat_id: Optional[Union[int, str]] = None,
        schedule_date: Optional[datetime] = None,
        protect_content: Optional[bool] = None,
        reply_parameters: Optional["types.ReplyParameters"] = None,
        message_thread_id: Optional[int] = None,
        allow_paid_broadcast: Optional[bool] = None,
        paid_message_star_count: Optional[int] = None,
        business_connection_id: Optional[str] = None,
        quote_text: Optional[str] = None,
        quote_entities: Optional[List["types.MessageEntity"]] = None,
        effect_id: Optional[int] = None,
        show_caption_above_media: Optional[bool] = None,
        repeat_period: Optional[int] = None,
        suggested_post_parameters: Optional["types.SuggestedPostParameters"] = None,
        direct_messages_topic_id: Optional[int] = None,
        background: Optional[bool] = None,
        clear_draft: Optional[bool] = None,
        update_stickersets_order: Optional[bool] = None,
        send_as: Optional[Union[int, str]] = None,
        quick_reply_shortcut: Optional[int] = None,
        reply_markup: Optional[Union[
            "types.InlineKeyboardMarkup",
            "types.ReplyKeyboardMarkup",
            "types.ReplyKeyboardRemove",
            "types.ForceReply"
        ]] = None,
        ephemeral_message_parameters: Optional["types.EphemeralMessageParameters"] = None,
    ) -> "types.Message":
        """Send information about a venue.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.
                For your personal cloud (Saved Messages) you can simply use "me" or "self".
                For a contact that exists in your Telegram address book you can use his phone number (str).

            latitude (``float``):
                Latitude of the venue.

            longitude (``float``):
                Longitude of the venue.

            title (``str``):
                Name of the venue.

            address (``str``):
                Address of the venue.

            foursquare_id (``str``, *optional*):
                Foursquare identifier of the venue.

            foursquare_type (``str``, *optional*):
                Foursquare type of the venue, if known.
                (For example, "arts_entertainment/default", "arts_entertainment/aquarium" or "food/icecream".)

            disable_notification (``bool``, *optional*):
                Sends the message silently.
                Users will receive a notification with no sound.

            reply_to_message_id (``int``, *optional*):
                If the message is a reply, ID of the original message

            schedule_date (:py:obj:`~datetime.datetime`, *optional*):
                Date when the message will be automatically sent.

            protect_content (``bool``, *optional*):
                Protects the contents of the sent message from forwarding and saving.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardMarkup` | :obj:`~pyrogram.types.ReplyKeyboardRemove` | :obj:`~pyrogram.types.ForceReply`, *optional*):
                Additional interface options. An object for an inline keyboard, custom reply keyboard,
                instructions to remove reply keyboard or to force a reply from the user.

            ephemeral_message_parameters (:obj:`~pyrogram.types.EphemeralMessageParameters`, *optional*):
                Send the message as an ephemeral message, visible only to the user it
                names and absent from the chat's history, rather than as an ordinary one.
                The ephemeral RPC has no field for *silent*, *background*, *clear_draft*,
                *schedule_date*, *repeat_period*, *send_as*, *effect_id*,
                *quick_reply_shortcut*, *allow_paid_broadcast*,
                *paid_message_star_count*, *suggested_post_parameters* or
                *update_stickersets_order*; any of those that is set is logged and
                dropped.

            reply_to_chat_id (``int`` | ``str``, *optional*):
                Unique identifier for the chat to which the replied message belongs.
                Only applicable in combination with *reply_to_message_id*.

            reply_parameters (:obj:`~pyrogram.types.ReplyParameters`, *optional*):
                Describes reply parameters for the message that is being sent.

            message_thread_id (``int``, *optional*):
                Unique identifier for a message thread in a forum topic.

            allow_paid_broadcast (``bool``, *optional*):
                If True, you will be allowed to send up to 1000 messages per second.
                Ignoring broadcasting limits for a fee of 0.1 Telegram Stars per message.
                The relevant Stars will be withdrawn from the bot's balance.
                For bots only.

            paid_message_star_count (``int``, *optional*):
                The number of Telegram Stars the user agreed to pay to send the messages.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

            quote_text (``str``, *optional*):
                Text of the quote to reply to.

            quote_entities (List of :obj:`~pyrogram.types.MessageEntity`):
                List of special entities that appear in *quote_text*, which can be specified instead of *parse_mode*.

            effect_id (``int``, *optional*):
                Unique identifier of the effect to apply to the message.

            show_caption_above_media (``bool``, *optional*):
                Pass True, if the caption must be shown above the message media.

            repeat_period (``int``, *optional*):
                New period in seconds for the message to be sent repeatedly.

            suggested_post_parameters (:obj:`~pyrogram.types.SuggestedPostParameters`, *optional*):
                Parameters of the suggested post.

            direct_messages_topic_id (``int``, *optional*):
                Unique identifier of the topic in a channel direct messages chat administered by the current user.
                For directs only only.

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
        Returns:
            :obj:`~pyrogram.types.Message`: On success, the sent venue message is returned.

        Example:
            .. code-block:: python

                app.send_venue(
                    "me", latitude, longitude,
                    "Venue title", "Venue address")
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
        r = await self.invoke(
            await as_ephemeral(self, ephemeral_message_parameters, raw.functions.messages.SendMedia(
                peer=await self.resolve_peer(chat_id),
                media=raw.types.InputMediaVenue(
                    geo_point=raw.types.InputGeoPoint(
                        lat=latitude,
                        long=longitude
                    ),
                    title=title,
                    address=address,
                    provider="foursquare" if foursquare_id or foursquare_type else "",
                    venue_id=foursquare_id or "",
                    venue_type=foursquare_type or ""
                ),
                message="",
                silent=disable_notification if disable_notification is not None else None,
                reply_to=await utils.get_reply_to(
                    self,
                    reply_parameters,
                    message_thread_id,
                    direct_messages_topic_id=direct_messages_topic_id,
                ),
                random_id=self.rnd_id(),
                schedule_date=utils.datetime_to_timestamp(schedule_date),
                noforwards=protect_content,
                allow_paid_floodskip=allow_paid_broadcast if allow_paid_broadcast is not None else None,
                allow_paid_stars=paid_message_star_count if paid_message_star_count is not None else None,
                effect=effect_id,
                invert_media=show_caption_above_media if show_caption_above_media is not None else None,
                schedule_repeat_period=repeat_period,
                suggested_post=suggested_post_parameters.write() if suggested_post_parameters else None,
                background=background,
                clear_draft=clear_draft,
                update_stickersets_order=update_stickersets_order,
                send_as=await self.resolve_peer(send_as) if send_as is not None else None,
                quick_reply_shortcut=raw.types.InputQuickReplyShortcutId(shortcut_id=quick_reply_shortcut) if quick_reply_shortcut is not None else None,
                reply_markup=await reply_markup.write(self) if reply_markup else None,
                entities=None
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
