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
from typing import Optional, Union

import pyrogram
from pyrogram import raw, types, utils


class EditMessageChecklist:
    async def edit_message_checklist(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        message_id: int,
        checklist: "types.InputChecklist",
        business_connection_id: Optional[str] = None,
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        schedule_date: Optional[datetime] = None,
        repeat_period: Optional[int] = None,
        quick_reply_shortcut: Optional[int] = None,
    ) -> "types.Message":
        """Use this method to edit a checklist.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.
                For your personal cloud (Saved Messages) you can simply use "me" or "self".
                For a contact that exists in your Telegram address book you can use his phone number (str).

            message_id (``int``):
                Message identifier in the chat specified in chat_id.

            checklist (:obj:`~pyrogram.types.InputChecklist`):
                New checklist.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection on behalf of which the message will be sent.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An InlineKeyboardMarkup object.
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

                # Replace the current checklist with a new one
                await app.edit_message_checklist(
                    chat_id=chat_id,
                    message_id=message_id,
                    checklist=types.InputChecklist(
                        title="Checklist",
                        tasks=[
                            types.InputChecklistTask(id=1, text="Task 1"),
                            types.InputChecklistTask(id=2, text="Task 2")
                        ]
                    )
                )
        """
        title, entities = (await utils.parse_text_entities(
            self, checklist.title, checklist.parse_mode, checklist.entities
        )).values()

        r = await self.invoke(
            raw.functions.messages.EditMessage(
                schedule_date=utils.datetime_to_timestamp(schedule_date),
                schedule_repeat_period=repeat_period,
                quick_reply_shortcut_id=quick_reply_shortcut,
                peer=await self.resolve_peer(chat_id),
                id=message_id,
                media=raw.types.InputMediaTodo(
                    todo=raw.types.TodoList(
                        title=raw.types.TextWithEntities(
                            text=title,
                            entities=entities or []
                        ),
                        list=[await task.write(self) for task in checklist.tasks],
                        others_can_append=checklist.others_can_add_tasks,
                        others_can_complete=checklist.others_can_mark_tasks_as_done
                    )
                ),
                reply_markup=await utils.write_edit_reply_markup(self, reply_markup=reply_markup),
            ),
            business_connection_id=business_connection_id
        )

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateEditMessage, raw.types.UpdateEditChannelMessage, raw.types.UpdateEditEphemeralMessage)):
                return await types.Message._parse(
                    self, i.message,
                    {i.id: i for i in r.users},
                    {i.id: i for i in r.chats}
                )

