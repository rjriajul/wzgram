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

from typing import Optional

import pyrogram
from pyrogram import raw


class AnswerWidgetQuery:
    async def answer_widget_query(
        self: "pyrogram.Client",
        widget_query_id: str,
        data: Optional[str] = None,
    ) -> bool:
        """Send an answer to a query from a widget. The query must be answered within 15 seconds.
        The answer is received only by the widget that sent the query and doesn't change data of the widget;
        use :meth:`~pyrogram.Client.edit_message_widget_data` or :meth:`~pyrogram.Client.edit_shared_widget_data` to change it.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            widget_query_id (``str``):
                Unique identifier for the query to be answered.

            data (``str``, *optional*):
                Data to be returned to the widget, 0-1024 bytes.

        Returns:
            ``bool``: True on success.

        Example:
            .. code-block:: python

                @app.on_widget_query()
                async def answer(client, widget_query):
                    await client.answer_widget_query(widget_query.id, "ok")
        """
        return await self.invoke(
            raw.functions.messages.SetBotWidgetQueryAnswer(
                query_id=int(widget_query_id),
                result=data,
            )
        )
