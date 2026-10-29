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

from enum import auto

from .auto_name import AutoName


class MessageServiceType(AutoName):
    """Message service type enumeration used in :obj:`~pyrogram.types.Message`."""

    NEW_CHAT_MEMBERS = auto()
    "New members join"

    LEFT_CHAT_MEMBERS = auto()
    "Left chat members"

    NEW_CHAT_TITLE = auto()
    "New chat title"

    NEW_CHAT_PHOTO = auto()
    "New chat photo"

    DELETE_CHAT_PHOTO = auto()
    "Deleted chat photo"

    GROUP_CHAT_CREATED = auto()
    "Group chat created"

    CHANNEL_CHAT_CREATED = auto()
    "Channel chat created"

    MIGRATE_TO_CHAT_ID = auto()
    "Migrated to chat id"

    MIGRATE_FROM_CHAT_ID = auto()
    "Migrated from chat id"

    PINNED_MESSAGE = auto()
    "Pinned message"

    GAME_HIGH_SCORE = auto()
    "Game high score"

    VIDEO_CHAT_STARTED = auto()
    "Video chat started"

    VIDEO_CHAT_ENDED = auto()
    "Video chat ended"

    VIDEO_CHAT_SCHEDULED = auto()
    "Video chat scheduled"

    VIDEO_CHAT_MEMBERS_INVITED = auto()
    "Video chat members invited"

    WEB_APP_DATA = auto()
    "Web app data"

    CONNECTED_WEBSITE = auto()
    "Connected website"

    WRITE_ACCESS_ALLOWED = auto()
    "Write access allowed"

    CHAT_BOOST = auto()
    "Chat boost"

    SUPERGROUP_CHAT_CREATED = auto()
    "Supergroup chat created"

    LEFT_CHAT_MEMBER = auto()
    "Left chat member"

    CHAT_OWNER_LEFT = auto()
    "Chat owner left"

    CHAT_OWNER_CHANGED = auto()
    "Chat owner changed"

    CONTACT_REGISTERED = auto()
    "Contact registered"

    CUSTOM_ACTION = auto()
    "Custom action"

    PROXIMITY_ALERT_TRIGGERED = auto()
    "Proximity alert triggered"

    PREMIUM_GIFT_CODE = auto()
    "Premium gift code"

    GIFTED_PREMIUM = auto()
    "Gifted premium"

    GIFTED_STARS = auto()
    "Gifted stars"

    GIFTED_GRAMS = auto()
    "Gifted TON Grams"

    GIVEAWAY_CREATED = auto()
    "Giveaway created"

    GIVEAWAY_COMPLETED = auto()
    "Giveaway completed"

    MANAGED_BOT_CREATED = auto()
    "Managed bot created"

    HISTORY_CLEARED = auto()
    "History cleared"

    SUCCESSFUL_PAYMENT = auto()
    "Successful payment"

    REFUNDED_PAYMENT = auto()
    "Refunded payment"

    SUGGESTED_POST_APPROVAL_FAILED = auto()
    "Suggested post approval failed"

    SUGGESTED_POST_DECLINED = auto()
    "Suggested post declined"

    SUGGESTED_POST_APPROVED = auto()
    "Suggested post approved"

    SUGGESTED_POST_PAID = auto()
    "Suggested post paid"

    SUGGESTED_POST_REFUNDED = auto()
    "Suggested post refunded"

    PHONE_CALL_ENDED = auto()
    "Phone call ended"

    PHONE_CALL_STARTED = auto()
    "Phone call started"

    GIVEAWAY_PRIZE_STARS = auto()
    "Giveaway prize stars"

    USERS_SHARED = auto()
    "Users shared"

    CHAT_SHARED = auto()
    "Chat shared"

    SCREENSHOT_TAKEN = auto()
    "Screenshot taken"

    UPGRADED_GIFT_PURCHASE_OFFER = auto()
    "Upgraded gift purchase offer"

    UPGRADED_GIFT_PURCHASE_OFFER_REJECTED = auto()
    "Upgraded gift purchase offer rejected"

    CHAT_HAS_PROTECTED_CONTENT_TOGGLED = auto()
    "Chat has protected content toggled"

    CHAT_HAS_PROTECTED_CONTENT_DISABLE_REQUESTED = auto()
    "Chat has protected content disable requested"

    CHAT_SET_THEME = auto()
    "Chat set theme"

    CHAT_SET_BACKGROUND = auto()
    "Chat set background"

    SET_MESSAGE_AUTO_DELETE_TIME = auto()
    "Set message auto delete time"

    GIFT = auto()
    "Gift"

    SUGGEST_PROFILE_PHOTO = auto()
    "Suggest profile photo"

    SUGGEST_BIRTHDAY = auto()
    "Suggest birthday"

    FORUM_TOPIC_CREATED = auto()
    "Forum topic created"

    GENERAL_FORUM_TOPIC_HIDDEN = auto()
    "General forum topic hidden"

    GENERAL_FORUM_TOPIC_UNHIDDEN = auto()
    "General forum topic unhidden"

    FORUM_TOPIC_CLOSED = auto()
    "Forum topic closed"

    FORUM_TOPIC_REOPENED = auto()
    "Forum topic reopened"

    FORUM_TOPIC_EDITED = auto()
    "Forum topic edited"

    PAID_MESSAGES_REFUNDED = auto()
    "Paid messages refunded"

    DIRECT_MESSAGE_PRICE_CHANGED = auto()
    "Direct message price changed"

    PAID_MESSAGES_PRICE_CHANGED = auto()
    "Paid messages price changed"

    CHECKLIST_TASKS_DONE = auto()
    "Checklist tasks done"

    CHECKLIST_TASKS_ADDED = auto()
    "Checklist tasks added"

    POLL_OPTION_ADDED = auto()
    "Poll option added"

    POLL_OPTION_DELETED = auto()
    "Poll option deleted"

    COMMUNITY_CHAT_ADDED = auto()
    "Chat added to community"

    COMMUNITY_CHAT_REMOVED = auto()
    "Chat removed from community"

    COMMUNITY_CHAT_JOINED = auto()
    "Chat joined by a user from a community"

    TON_WALLET_TRANSFER = auto()
    "TON wallet transfer"

    TON_CONNECT_REQUEST = auto()
    "TON Connect request"

    NO_PAID_MESSAGES_TOKEN_USED = auto()
    "The sender used a link to message without paying Stars"

    CONFERENCE_CALL = auto()
    "Conference call"

    PASSPORT_DATA_SEND = auto()
    "Passport data sent"

    PASSPORT_DATA_RECEIVED = auto()
    "Passport data received"

    UNSUPPORTED = auto()
    "Unsupported service message"
