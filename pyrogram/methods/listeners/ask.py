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
from pyrogram import enums, types
from pyrogram.filters import Filter

from .listen import UNSET, add_listener, wait_for_listener


class Ask:
    async def ask(
        self: "pyrogram.Client",
        chat_id: Union[int, str, List[Union[int, str]]],
        text: str,
        filters: Optional[Filter] = None,
        listener_type: "enums.ListenerTypes" = enums.ListenerTypes.MESSAGE,
        timeout: Optional[float] = UNSET,
        unallowed_click_alert: Union[bool, str] = True,
        user_id: Optional[Union[int, str, List[Union[int, str]]]] = None,
        message_id: Optional[Union[int, List[int]]] = None,
        inline_message_id: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> Union["types.Message", "types.CallbackQuery"]:
        """Send a message and wait for the answer to it.

        Shortcut for :meth:`~pyrogram.Client.send_message` followed by
        :meth:`~pyrogram.Client.listen`. The returned update carries the prompt
        as ``sent_message``.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str`` | List of ``int`` | ``str``):
                Chat to send the question to. When a list is given, the question
                goes to the first one and any of them may answer.

            text (``str``):
                Text of the question.

            filters (:obj:`~pyrogram.filters.Filter`, *optional*):
                Extra filter the answer has to pass.

            listener_type (:obj:`~pyrogram.enums.ListenerTypes`, *optional*):
                Kind of update to wait for. Defaults to a new message.

            timeout (``float``, *optional*):
                Seconds to wait before raising ``ListenerTimeout``. Defaults to
                the client's ``listener_timeout`` (300s).

            unallowed_click_alert (``bool`` | ``str``, *optional*):
                For callback query listeners, answer clicks coming from a user
                this listener does not expect. Pass a string to set the text.

            user_id (``int`` | ``str`` | List of ``int`` | ``str``, *optional*):
                User the answer has to come from.

            message_id (``int`` | List of ``int``, *optional*):
                Message the answer has to belong to.

            inline_message_id (``str`` | List of ``str``, *optional*):
                Inline message the answer has to belong to.

            kwargs:
                Any other argument accepted by
                :meth:`~pyrogram.Client.send_message`.

        Returns:
            :obj:`~pyrogram.types.Message` | :obj:`~pyrogram.types.CallbackQuery`:
            The answer, with the prompt attached as ``sent_message``.

        Raises:
            ListenerTimeout: In case nobody answered in time.
            ListenerStopped: In case the listener was stopped, or the client is.
            ListenerLimitReached: In case no listener slot was available.

        Example:
            .. code-block:: python

                answer = await app.ask(chat_id, "What is your name?", timeout=60)
                await answer.reply(f"Hello {answer.text}")
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

        try:
            sent_message = await self.send_message(
                chat_id[0] if isinstance(chat_id, list) else chat_id,
                text,
                **kwargs
            )
        except BaseException:
            self.listeners.remove(listener)
            raise

        response = await wait_for_listener(self, listener, future)

        if response is not None:
            response.sent_message = sent_message

        return response
