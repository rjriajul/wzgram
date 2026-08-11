from typing import Union, Optional

import pyrogram
from pyrogram import raw, types


class SendRichMessageDraft:
    async def send_rich_message_draft(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        draft_id: int,
        rich_message: "types.InputRichMessage",
        message_thread_id: Optional[int] = None,
    ) -> bool:
        """Send a rich message draft action, allowing bots to stream partial rich messages.

        When generating a rich message progressively (e.g. during AI response streaming),
        this method shows the user a typing indicator with the partial rich message content.
        The block :obj:`~pyrogram.types.InputRichBlockThinking` may be used as a placeholder
        while waiting for content to be generated.

        .. include:: /_includes/usable-by/bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.

            draft_id (``int``):
                Unique identifier of the draft; must be non-zero.
                Keep it constant for the whole generation, updates sharing an identifier are animated by clients.
                A different identifier does not restart the draft, it adds a second concurrent draft,
                and some clients collapse them into one.

            rich_message (:obj:`~pyrogram.types.InputRichMessage`):
                The partial rich message to stream.
                Use :obj:`~pyrogram.types.InputRichBlockThinking` as a placeholder
                for content still being generated.

            message_thread_id (``int``, *optional*):
                Unique identifier for a forum topic thread.

        Returns:
            ``bool``: On success, True is returned.

        .. note::

            The draft is ephemeral: clients drop it after ``message_typing_draft_ttl`` seconds
            (30 by default, server-configured) or as soon as a real message arrives, so call
            :meth:`~pyrogram.Client.send_rich_message` to persist the result. Throttle the stream:
            setTyping is rate-limited to 20 calls per 5s and 40 per 30s per peer.

        Example:
            .. code-block:: python

                draft_id = app.rnd_id()

                for i, word in enumerate(words):
                    await app.send_rich_message_draft(
                        chat_id, draft_id,
                        types.InputRichMessage(html=" ".join(words[:i + 1])),
                    )
                    await asyncio.sleep(0.33)

                await app.send_rich_message(chat_id, text)
        """
        return await self.invoke(
            raw.functions.messages.SetTyping(
                peer=await self.resolve_peer(chat_id),
                action=raw.types.InputSendMessageRichMessageDraftAction(
                    random_id=draft_id,
                    rich_message=rich_message.write(),
                ),
                top_msg_id=message_thread_id,
            )
        )
