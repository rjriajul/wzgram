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

import inspect
import re
from typing import Callable, List, Optional, Pattern, Union

import pyrogram
from pyrogram import enums
from pyrogram.types import (
    CallbackQuery,
    ChatBoostUpdated,
    ChosenInlineResult,
    InlineKeyboardMarkup,
    InlineQuery,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    Update,
    User,
)


class Filter:
    async def __call__(self, client: "pyrogram.Client", update: Update):
        raise NotImplementedError

    def __invert__(self):
        return InvertFilter(self)

    def __and__(self, other):
        return AndFilter(self, other)

    def __or__(self, other):
        return OrFilter(self, other)



async def check_filter(filter, client: "pyrogram.Client", update: Update):
    """Run a filter, awaiting it or offloading it depending on how it was written.

    ``create`` accepts a plain ``def`` as readily as a coroutine function, so
    every caller has to probe before invoking. Missing filters pass.
    """
    if not callable(filter):
        return True

    if inspect.iscoroutinefunction(filter.__call__):
        return await filter(client, update)

    return await client.loop.run_in_executor(
        client.executor,
        filter,
        client, update
    )


class InvertFilter(Filter):
    def __init__(self, base):
        self.base = base

    async def __call__(self, client: "pyrogram.Client", update: Update):
        return not await check_filter(self.base, client, update)


class AndFilter(Filter):
    def __init__(self, base, other):
        self.base = base
        self.other = other

    async def __call__(self, client: "pyrogram.Client", update: Update):
        x = await check_filter(self.base, client, update)

        if not x:
            return False

        return x and await check_filter(self.other, client, update)


class OrFilter(Filter):
    def __init__(self, base, other):
        self.base = base
        self.other = other

    async def __call__(self, client: "pyrogram.Client", update: Update):
        x = await check_filter(self.base, client, update)

        if x:
            return True

        return x or await check_filter(self.other, client, update)


CUSTOM_FILTER_NAME = "CustomFilter"


def create(func: Callable, name: Optional[str] = None, **kwargs) -> Filter:
    return type(
        name or func.__name__ or CUSTOM_FILTER_NAME,
        (Filter,),
        {"__call__": func, **kwargs}
    )()


# region all_filter
async def all_filter(_, __, ___):
    return True


all = create(all_filter)


# endregion


def _sender_of(update) -> Optional[User]:
    if isinstance(update, User):
        return update

    if isinstance(update, ChatBoostUpdated):
        return update.boost.from_user if update.boost else None

    return getattr(update, "from_user", None) or getattr(update, "user", None)


def _sender_chat_of(update):
    return getattr(update, "sender_chat", None) or getattr(update, "actor_chat", None)


def _chat_of(update):
    return getattr(update, "chat", None)


def _is_outgoing(update) -> bool:
    return bool(getattr(update, "outgoing", False))


# region me_filter
async def me_filter(_, __, m: Message):
    sender = _sender_of(m)
    return bool(sender and (sender.is_self or _is_outgoing(m)))


me = create(me_filter)


# endregion

# region bot_filter
async def bot_filter(_, __, m: Message):
    sender = _sender_of(m)
    return bool(sender and sender.is_bot)


bot = create(bot_filter)


# endregion

# region sender_chat_filter
async def sender_chat_filter(_, __, m: Message):
    return bool(_sender_chat_of(m))


sender_chat = create(sender_chat_filter)


# endregion

# region incoming_filter
async def incoming_filter(_, __, m: Message):
    return not _is_outgoing(m)


incoming = create(incoming_filter)


# endregion

# region outgoing_filter
async def outgoing_filter(_, __, m: Message):
    return _is_outgoing(m)


outgoing = create(outgoing_filter)


# endregion

# region text_filter
async def text_filter(_, __, m: Message):
    return bool(m.text)


text = create(text_filter)


# endregion

# region reply_filter
async def reply_filter(_, __, m: Message):
    return bool(m.reply_to_message_id or m.reply_to_story_id)


reply = create(reply_filter)


# endregion

# region forwarded_filter
async def forwarded_filter(_, __, m: Message):
    return bool(m.forward_origin)


forwarded = create(forwarded_filter)


# endregion

# region caption_filter
async def caption_filter(_, __, m: Message):
    return bool(m.caption)


caption = create(caption_filter)


# endregion

# region self_destruction_filter
async def self_destruction_filter(_, __, m: Message):
    return bool(m.media and getattr(getattr(m, m.media.value, None), "ttl_seconds", None))


self_destruction = create(self_destruction_filter)


# endregion

# region audio_filter
async def audio_filter(_, __, m: Message):
    return bool(m.audio)


audio = create(audio_filter)


# endregion

# region document_filter
async def document_filter(_, __, m: Message):
    return bool(m.document)


document = create(document_filter)


# endregion

# region photo_filter
async def photo_filter(_, __, m: Message):
    return bool(m.photo)


photo = create(photo_filter)


# endregion

# region sticker_filter
async def sticker_filter(_, __, m: Message):
    return bool(m.sticker)


sticker = create(sticker_filter)


# endregion

# region animation_filter
async def animation_filter(_, __, m: Message):
    return bool(m.animation)


animation = create(animation_filter)


# endregion

# region game_filter
async def game_filter(_, __, m: Message):
    return bool(m.game)


game = create(game_filter)


# endregion

# region giveaway_filter
async def giveaway_filter(_, __, m: Message):
    return bool(m.giveaway)


giveaway = create(giveaway_filter)


# endregion

# region giveaway_winners_filter
async def giveaway_winners_filter(_, __, m: Message):
    return bool(m.giveaway_winners)


giveaway_winners = create(giveaway_winners_filter)


# endregion

# region gift_code_filter
async def gift_code_filter(_, __, m: Message):
    return bool(m.premium_gift_code)


gift_code = create(gift_code_filter)


# endregion

# region gift_filter
async def gift_filter(_, __, m: Message):
    return bool(m.gift)


gift = create(gift_filter)


# endregion

# region users_shared_filter
async def users_shared_filter(_, __, m: Message):
    return bool(m.users_shared)


users_shared = create(users_shared_filter)


# endregion

# region chat_shared_filter
async def chat_shared_filter(_, __, m: Message):
    return bool(m.chat_shared)


chat_shared = create(chat_shared_filter)


# endregion

# region video_filter
async def video_filter(_, __, m: Message):
    return bool(m.video)


video = create(video_filter)


# endregion

# region media_group_filter
async def media_group_filter(_, __, m: Message):
    return bool(m.media_group_id)


media_group = create(media_group_filter)


# endregion

# region voice_filter
async def voice_filter(_, __, m: Message):
    return bool(m.voice)


voice = create(voice_filter)


# endregion

# region video_note_filter
async def video_note_filter(_, __, m: Message):
    return bool(m.video_note)


video_note = create(video_note_filter)


# endregion

# region contact_filter
async def contact_filter(_, __, m: Message):
    return bool(m.contact)


contact = create(contact_filter)


# endregion

# region location_filter
async def location_filter(_, __, m: Message):
    return bool(m.location and not m.location.live_period)


location = create(location_filter)


# endregion

# region live_location_filter
async def live_location_filter(_, __, m: Message):
    return bool(m.location and m.location.live_period)


live_location = create(live_location_filter)


# endregion

# region venue_filter
async def venue_filter(_, __, m: Message):
    return bool(m.venue)


venue = create(venue_filter)


# endregion

# region web_page_filter
async def web_page_filter(_, __, m: Message):
    return bool(m.web_page)


web_page = create(web_page_filter)


# endregion

# region poll_filter
async def poll_filter(_, __, m: Message):
    return bool(m.poll)


poll = create(poll_filter)


# endregion

# region dice_filter
async def dice_filter(_, __, m: Message):
    return bool(m.dice)


dice = create(dice_filter)


# endregion

# region quote_filter
async def quote_filter(_, __, m: Message):
    return bool(m.quote)


quote = create(quote_filter)


# endregion

# region media_spoiler
async def media_spoiler_filter(_, __, m: Message):
    return bool(m.has_media_spoiler)


media_spoiler = create(media_spoiler_filter)


# endregion

# region private_filter
async def private_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.type in {enums.ChatType.PRIVATE, enums.ChatType.BOT})


private = create(private_filter)


# endregion

# region group_filter
async def group_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.FORUM})


group = create(group_filter)


# endregion

# region channel_filter
async def channel_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.type == enums.ChatType.CHANNEL)


channel = create(channel_filter)


# endregion

# region direct_filter
async def direct_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.type == enums.ChatType.PRIVATE)


direct = create(direct_filter)


# endregion

# region forum_filter
async def forum_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.is_forum)


forum = create(forum_filter)


# endregion

# region story_filter
async def story_filter(_, __, m: Message):
    return bool(m.story)


story = create(story_filter)


# endregion

# region new_chat_members_filter
async def new_chat_members_filter(_, __, m: Message):
    return bool(m.new_chat_members)


new_chat_members = create(new_chat_members_filter)


# endregion

# region left_chat_member_filter
async def left_chat_member_filter(_, __, m: Message):
    return bool(m.left_chat_member)


left_chat_member = create(left_chat_member_filter)


# endregion

# region new_chat_title_filter
async def new_chat_title_filter(_, __, m: Message):
    return bool(m.new_chat_title)


new_chat_title = create(new_chat_title_filter)


# endregion

# region new_chat_photo_filter
async def new_chat_photo_filter(_, __, m: Message):
    return bool(m.new_chat_photo)


new_chat_photo = create(new_chat_photo_filter)


# endregion

# region delete_chat_photo_filter
async def delete_chat_photo_filter(_, __, m: Message):
    return bool(m.delete_chat_photo)


delete_chat_photo = create(delete_chat_photo_filter)


# endregion

# region group_chat_created_filter
async def group_chat_created_filter(_, __, m: Message):
    return bool(m.group_chat_created)


group_chat_created = create(group_chat_created_filter)


# endregion

# region supergroup_chat_created_filter
async def supergroup_chat_created_filter(_, __, m: Message):
    return bool(m.supergroup_chat_created)


supergroup_chat_created = create(supergroup_chat_created_filter)


# endregion

# region channel_chat_created_filter
async def channel_chat_created_filter(_, __, m: Message):
    return bool(m.channel_chat_created)


channel_chat_created = create(channel_chat_created_filter)


# endregion

# region migrate_to_chat_id_filter
async def migrate_to_chat_id_filter(_, __, m: Message):
    return bool(m.migrate_to_chat_id)


migrate_to_chat_id = create(migrate_to_chat_id_filter)


# endregion

# region migrate_from_chat_id_filter
async def migrate_from_chat_id_filter(_, __, m: Message):
    return bool(m.migrate_from_chat_id)


migrate_from_chat_id = create(migrate_from_chat_id_filter)


# endregion

# region pinned_message_filter
async def pinned_message_filter(_, __, m: Message):
    return bool(m.pinned_message)


pinned_message = create(pinned_message_filter)


# endregion

# region game_high_score_filter
async def game_high_score_filter(_, __, m: Message):
    return bool(m.game_high_score)


game_high_score = create(game_high_score_filter)


# endregion

# region reply_keyboard_filter
async def reply_keyboard_filter(_, __, m: Message):
    return isinstance(m.reply_markup, ReplyKeyboardMarkup)


reply_keyboard = create(reply_keyboard_filter)


# endregion

# region inline_keyboard_filter
async def inline_keyboard_filter(_, __, m: Message):
    return isinstance(m.reply_markup, InlineKeyboardMarkup)


inline_keyboard = create(inline_keyboard_filter)


# endregion

# region mentioned_filter
async def mentioned_filter(_, __, m: Message):
    return bool(m.mentioned)


mentioned = create(mentioned_filter)


# endregion

# region via_bot_filter
async def via_bot_filter(_, __, m: Message):
    return bool(m.via_bot)


via_bot = create(via_bot_filter)


# endregion

# region admin_filter
async def admin_filter(_, __, m: Message):
    chat = _chat_of(m)
    return bool(chat and chat.is_admin)


admin = create(admin_filter)


# endregion

# region video_chat_started_filter
async def video_chat_started_filter(_, __, m: Message):
    return bool(m.video_chat_started)


video_chat_started = create(video_chat_started_filter)


# endregion

# region video_chat_ended_filter
async def video_chat_ended_filter(_, __, m: Message):
    return bool(m.video_chat_ended)


video_chat_ended = create(video_chat_ended_filter)


# endregion

# region business
async def business_filter(_, __, m: Message):
    return bool(m.business_connection_id)


business = create(business_filter)


# endregion

# region video_chat_members_invited_filter
async def video_chat_members_invited_filter(_, __, m: Message):
    return bool(m.video_chat_members_invited)


video_chat_members_invited = create(video_chat_members_invited_filter)


# endregion

# region successful_payment_filter
async def successful_payment_filter(_, __, m: Message):
    return bool(m.successful_payment)


successful_payment = create(successful_payment_filter)


# endregion

# region service_filter
async def service_filter(_, __, m: Message):
    return bool(m.service)


service = create(service_filter)


# endregion

# region media_filter
async def media_filter(_, __, m: Message):
    return bool(m.media)


media = create(media_filter)


# endregion

# region scheduled_filter
async def scheduled_filter(_, __, m: Message):
    return bool(m.scheduled)


scheduled = create(scheduled_filter)


# endregion

# region from_scheduled_filter
async def from_scheduled_filter(_, __, m: Message):
    return bool(m.from_scheduled)


from_scheduled = create(from_scheduled_filter)


# endregion

# region paid_message_filter
async def paid_message_filter(_, __, m: Message):
    return bool(m.send_paid_messages_stars)


paid_message = create(paid_message_filter)


# endregion

# region ephemeral_filter
async def ephemeral_filter(_, __, m: Message):
    return m.is_ephemeral


ephemeral = create(ephemeral_filter)


# endregion

# region linked_channel_filter
async def linked_channel_filter(_, __, m: Message):
    return bool(
        m.forward_origin and
        m.forward_origin.type == enums.MessageOriginType.CHANNEL and
        m.forward_origin.chat == m.sender_chat
    )


linked_channel = create(linked_channel_filter)


# endregion

# region gift_offer_filter
async def gift_offer_filter(_, __, m: Message):
    return bool(
        m.upgraded_gift_purchase_offer and m.upgraded_gift_purchase_offer.state == enums.GiftPurchaseOfferState.PENDING
    )


gift_offer = create(gift_offer_filter)


# endregion

# region gift_offer_accepted_filter
async def gift_offer_accepted_filter(_, __, m: Message):
    return bool(
        m.upgraded_gift_purchase_offer and m.upgraded_gift_purchase_offer.state == enums.GiftPurchaseOfferState.ACCEPTED
    )


gift_offer_accepted = create(gift_offer_accepted_filter)


# endregion

# region gift_offer_rejected_filter
async def gift_offer_rejected_filter(_, __, m: Message):
    return bool(
        (m.upgraded_gift_purchase_offer and m.upgraded_gift_purchase_offer.state == enums.GiftPurchaseOfferState.REJECTED)
        or m.upgraded_gift_purchase_offer_rejected
    )


gift_offer_rejected = create(gift_offer_rejected_filter)


# endregion

# region command_filter
def command(commands: Union[str, List[str]], prefixes: Optional[Union[str, List[str]]] = "/", case_sensitive: bool = False):
    command_re = re.compile(r"([\"'])(.*?)(?<!\\)\1|(\S+)")

    async def func(flt, client: pyrogram.Client, message: Message):
        username = client.me.username or ""
        text = message.text or message.caption
        message.command = None

        if not text:
            return False

        for prefix in flt.prefixes:
            if not text.startswith(prefix):
                continue

            without_prefix = text[len(prefix):]

            for cmd in flt.commands:
                escaped_cmd = re.escape(cmd)
                escaped_username = re.escape(username)
                if not re.match(rf"^(?:{escaped_cmd}(?:@?{escaped_username})?)(?:\s|$)", without_prefix,
                                flags=re.IGNORECASE if not flt.case_sensitive else 0):
                    continue

                without_command = re.sub(rf"{escaped_cmd}(?:@?{escaped_username})?\s?", "", without_prefix, count=1,
                                         flags=re.IGNORECASE if not flt.case_sensitive else 0)

                message.command = [cmd] + [
                    re.sub(r"\\([\"'])", r"\1", m.group(2) or m.group(3) or "")
                    for m in command_re.finditer(without_command)
                ]

                return True

        return False

    commands = commands if isinstance(commands, list) else [commands]
    commands = {c if case_sensitive else c.lower() for c in commands}

    prefixes = [] if prefixes is None else prefixes
    prefixes = prefixes if isinstance(prefixes, list) else [prefixes]
    prefixes = set(prefixes) if prefixes else {""}

    return create(
        func,
        "CommandFilter",
        commands=commands,
        prefixes=prefixes,
        case_sensitive=case_sensitive
    )


# endregion

def regex(pattern: Union[str, Pattern], flags: int = 0):
    async def func(flt, _, update: Update):
        if isinstance(update, Message):
            value = update.text or update.caption
        elif isinstance(update, CallbackQuery):
            value = update.data
        elif isinstance(update, (ChosenInlineResult, InlineQuery)):
            value = update.query
        elif isinstance(update, PreCheckoutQuery):
            value = update.invoice_payload
        else:
            raise ValueError(f"Regex filter doesn't work with {type(update)}")

        update.matches = (list(flt.p.finditer(value)) or None) if value else None

        return bool(update.matches)

    return create(
        func,
        "RegexFilter",
        p=pattern if isinstance(pattern, Pattern) else re.compile(pattern, flags)
    )


# noinspection PyPep8Naming
class user(Filter, set):
    def __init__(self, users: Optional[Union[int, str, List[Union[int, str]]]] = None):
        users = [] if users is None else users if isinstance(users, list) else [users]

        super().__init__(
            "me" if u in ["me", "self"]
            else u.lower().strip("@") if isinstance(u, str)
            else u for u in users
        )

    async def __call__(self, _, message: Message):
        sender = _sender_of(message)
        return (sender
                and (sender.id in self
                     or (sender.username
                         and sender.username.lower() in self)
                     or ("me" in self
                         and sender.is_self)))


# noinspection PyPep8Naming
class chat(Filter, set):
    def __init__(self, chats: Optional[Union[int, str, List[Union[int, str]]]] = None):
        chats = [] if chats is None else chats if isinstance(chats, list) else [chats]

        super().__init__(
            "me" if c in ["me", "self"]
            else c.lower().strip("@") if isinstance(c, str)
            else c for c in chats
        )

    async def __call__(self, _, message: Message):
        chat = _chat_of(message)
        sender = _sender_of(message)
        return (chat
                and (chat.id in self
                     or (chat.username
                         and chat.username.lower() in self)
                     or ("me" in self
                         and sender
                         and sender.is_self
                         and not _is_outgoing(message))))


# noinspection PyPep8Naming
class topic(Filter, set):
    def __init__(self, topics: Optional[Union[int, List[int]]] = None):
        topics = [] if topics is None else topics if isinstance(topics, list) else [topics]

        super().__init__(
            t for t in topics
        )

    async def __call__(self, _, message: Message):
        return message.topic and message.topic.id in self
