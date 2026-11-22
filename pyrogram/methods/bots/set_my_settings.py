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

from typing import Optional, Union

import pyrogram
from pyrogram import raw


class SetMySettings:
    async def set_my_settings(
        self: "pyrogram.Client",
        supports_inline_queries: Optional[bool] = None,
        inline_query_placeholder: Optional[str] = None,
        needs_inline_query_location: Optional[bool] = None,
        inline_feedback_share_denominator: Optional[int] = None,
        can_join_groups: Optional[bool] = None,
        can_read_all_group_messages: Optional[bool] = None,
        can_connect_to_business: Optional[bool] = None,
        can_manage_bots: Optional[bool] = None,
        supports_guest_queries: Optional[bool] = None,
        supports_join_request_queries: Optional[bool] = None,
        has_topics_enabled: Optional[bool] = None,
        allows_users_to_create_topics: Optional[bool] = None,
        has_topic_sidebar: Optional[bool] = None,
        can_communicate_with_bots: Optional[bool] = None,
        callback_query_mode: Optional[str] = None,
        for_my_bot: Optional[Union[int, str]] = None,
    ) -> bool:
        """Change the settings of the bot. Settings that aren't specified remain unchanged.

        .. note::

            If the current account is an User, can be called only if the ``for_my_bot`` has ``can_be_edited`` property set to True.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            supports_inline_queries (``bool``, *optional*):
                Pass True to enable inline mode for the bot or False to disable it.

            inline_query_placeholder (``str``, *optional*):
                New placeholder for inline queries, which is shown in the input field after the bot's username.
                Pass an empty string to use the default placeholder.

            needs_inline_query_location (``bool``, *optional*):
                Pass True to request the location of the user with every inline query to the bot or False to stop requesting it.

            inline_feedback_share_denominator (``int``, *optional*):
                Denominator of the share of chosen inline results received by the bot;
                the bot receives 1 out of inline_feedback_share_denominator chosen results.
                Must be one of 1, 10, 100, or 1000. Pass 0 to stop receiving chosen inline results.

            can_join_groups (``bool``, *optional*):
                Pass True to allow adding the bot to groups or False to disallow it.

            can_read_all_group_messages (``bool``, *optional*):
                Pass True to disable privacy mode for the bot or False to enable it.

            can_connect_to_business (``bool``, *optional*):
                Pass True to allow connecting the bot to user accounts to manage them or False to disallow it.

            can_manage_bots (``bool``, *optional*):
                Pass True to allow creating other bots that will be controlled by the bot or False to disallow it.

            supports_guest_queries (``bool``, *optional*):
                Pass True to allow guest queries to the bot from chats it isn't a member of or False to disallow them.

            supports_join_request_queries (``bool``, *optional*):
                Pass True to allow assigning the bot to process join request queries or False to disallow it.

            has_topics_enabled (``bool``, *optional*):
                Pass True to enable forum topic mode in private chats with the bot or False to disable it.

            allows_users_to_create_topics (``bool``, *optional*):
                Pass True to allow users to create and delete topics in private chats with the bot or False to disallow it.

            has_topic_sidebar (``bool``, *optional*):
                Pass True to show topics in private chats with the bot in a sidebar or False to stop showing them in a sidebar.

            can_communicate_with_bots (``bool``, *optional*):
                Pass True to allow the bot to communicate with other bots in groups, private chats,
                and through business accounts or False to disallow it.

            callback_query_mode (``str``, *optional*):
                Mode in which the bot receives callback queries from buttons in messages sent by the bot.
                Must be one of "default" (the field ``message`` is always used),
                "auto" (the field ``inline_message_id`` is used instead of the field ``message`` if the message is inaccessible to the bot),
                or "inline" (the field ``inline_message_id`` is always used instead of the field ``message``).

            for_my_bot (``int`` | ``str``, *optional*):
                Unique identifier (int) or username (str) of the bot whose settings have to be changed instead of the current bot.
                The bot should have ``can_be_edited`` property set to True.

        Returns:
            ``bool``: True on success.

        Example:
            .. code-block:: python

                await app.set_my_settings(has_topics_enabled=True, has_topic_sidebar=True)

                await app.set_my_settings(callback_query_mode="inline")
        """
        if callback_query_mode not in (None, "default", "auto", "inline"):
            raise ValueError('callback_query_mode must be one of "default", "auto" or "inline"')

        if inline_feedback_share_denominator not in (None, 0, 1, 10, 100, 1000):
            raise ValueError("inline_feedback_share_denominator must be one of 0, 1, 10, 100 or 1000")

        await self.invoke(
            raw.functions.bots.SetBotSettings(
                bot=await self.resolve_peer(for_my_bot) if for_my_bot is not None else None,
                inline_mode=supports_inline_queries,
                inline_placeholder=inline_query_placeholder,
                inline_geo=needs_inline_query_location,
                inline_feedback=inline_feedback_share_denominator,
                nochats=None if can_join_groups is None else not can_join_groups,
                chat_history=can_read_all_group_messages,
                business=can_connect_to_business,
                can_manage_bots=can_manage_bots,
                guestchat=supports_guest_queries,
                guard=supports_join_request_queries,
                forum_view=has_topics_enabled,
                forum_can_manage_topics=allows_users_to_create_topics,
                forum_sidebar=has_topic_sidebar,
                bot_to_bot_communication_mode=can_communicate_with_bots,
                callback_mode="" if callback_query_mode == "default" else callback_query_mode,
            )
        )

        return True
