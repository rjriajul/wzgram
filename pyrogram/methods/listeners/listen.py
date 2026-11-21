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

import asyncio
import logging
from typing import List, Optional, Union

import pyrogram
from pyrogram import enums, types, utils
from pyrogram.errors import ListenerStopped
from pyrogram.filters import Filter
from pyrogram.types.listeners.listener import UNSET

log = logging.getLogger(__name__)


async def resolve_listener_ids(client: "pyrogram.Client", value):
    """Turn whatever the caller passed into canonical peer ids.

    Listeners are filed by id, so a username has to become one at registration
    time. Ints are taken as given: resolving them would need the peer to be known
    already, and would refuse a listener for a chat the client has not met yet.
    """
    if value is None:
        return None

    if isinstance(value, list):
        return [await resolve_listener_ids(client, item) for item in value]

    if isinstance(value, str):
        return await utils.resolve_peer_id(client, value)

    return value


async def add_listener(
    client: "pyrogram.Client",
    filters,
    listener_type,
    timeout,
    unallowed_click_alert,
    chat_id,
    user_id,
    message_id,
    inline_message_id
):
    if client.no_updates:
        raise ListenerStopped(
            "Cannot listen for updates on a client started with no_updates"
        )

    if timeout is UNSET:
        timeout = client.listener_timeout

    identifier = types.Identifier(
        chat_id=await resolve_listener_ids(client, chat_id),
        user_id=await resolve_listener_ids(client, user_id),
        message_id=message_id,
        inline_message_id=inline_message_id
    )

    future = client.loop.create_future()

    listener = types.Listener(
        listener_type=listener_type,
        identifier=identifier,
        filters=filters,
        future=future,
        unallowed_click_alert=unallowed_click_alert
    )

    client.listeners.add(listener, timeout)

    return listener, future


async def wait_for_listener(client: "pyrogram.Client", listener, future):
    parked = client.dispatcher.park()

    try:
        return await future
    except asyncio.CancelledError:
        if future.done() and not future.cancelled() and not future.exception():
            log.warning(
                "A listener was cancelled after its update had already been "
                "delivered; that update is lost"
            )

        raise
    finally:
        if parked:
            client.dispatcher.unpark()

        client.listeners.remove(listener)


class Listen:
    async def listen(
        self: "pyrogram.Client",
        filters: Optional[Filter] = None,
        listener_type: "enums.ListenerTypes" = enums.ListenerTypes.MESSAGE,
        timeout: Optional[float] = UNSET,
        unallowed_click_alert: Union[bool, str] = True,
        chat_id: Optional[Union[int, str, List[Union[int, str]]]] = None,
        user_id: Optional[Union[int, str, List[Union[int, str]]]] = None,
        message_id: Optional[Union[int, List[int]]] = None,
        inline_message_id: Optional[Union[str, List[str]]] = None
    ) -> Union["types.Message", "types.CallbackQuery"]:
        """Wait for the next update matching the given criteria.

        The update is consumed: handlers do not see it. Raw update handlers still
        do, since they are a separate contract.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            filters (:obj:`~pyrogram.filters.Filter`, *optional*):
                Extra filter the update has to pass.

            listener_type (:obj:`~pyrogram.enums.ListenerTypes`, *optional*):
                Kind of update to wait for. Defaults to a new message.

            timeout (``float``, *optional*):
                Seconds to wait before raising ``ListenerTimeout``. Defaults to
                the client's ``listener_timeout`` (300s). Pass None to wait
                forever, which leaks a listener per abandoned conversation.

            unallowed_click_alert (``bool`` | ``str``, *optional*):
                For callback query listeners, answer clicks coming from a user
                this listener does not expect. Pass a string to set the text.

            chat_id (``int`` | ``str`` | List of ``int`` | ``str``, *optional*):
                Chat the update has to come from.

            user_id (``int`` | ``str`` | List of ``int`` | ``str``, *optional*):
                User the update has to come from.

            message_id (``int`` | List of ``int``, *optional*):
                Message the update has to belong to.

            inline_message_id (``str`` | List of ``str``, *optional*):
                Inline message the update has to belong to.

        Returns:
            :obj:`~pyrogram.types.Message` | :obj:`~pyrogram.types.CallbackQuery`:
            The matching update.

        Raises:
            ListenerTimeout: In case no matching update arrived in time.
            ListenerStopped: In case the listener was stopped, or the client is.
            ListenerLimitReached: In case no listener slot was available.

        Example:
            .. code-block:: python

                # Wait for the next message in a chat
                message = await app.listen(chat_id=chat_id)

                # Wait up to 60s for one specific user, ignoring everyone else
                reply = await app.listen(chat_id=chat_id, user_id=user_id, timeout=60)

                # Wait for a button press on a message you just sent
                query = await app.listen(
                    listener_type=enums.ListenerTypes.CALLBACK_QUERY,
                    chat_id=chat_id,
                    message_id=sent.id
                )
        """
        listener, future = await add_listener(
            self,
            filters=filters,
            listener_type=listener_type,
            timeout=timeout,
            unallowed_click_alert=unallowed_click_alert,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            inline_message_id=inline_message_id
        )

        return await wait_for_listener(self, listener, future)
