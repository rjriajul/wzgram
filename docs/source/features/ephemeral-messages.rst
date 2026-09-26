Ephemeral Messages
==================

*Bot API 10.2 — July 2026*

An ephemeral message is sent into a group but shown to **one person**. Nobody else in the
chat sees it, and it is not part of the chat's history — there is no message id to fetch
later, no forwarding, no search.

It is what a bot should use for anything addressed to one member: an error, a private prompt,
a result nobody else asked for. Before this existed the choices were spamming the group or
starting a private chat the user may not have opened.

Ephemeral messages are sent by **bots**.


-----

Sending one
-----------

.. code-block:: python

    from wzgram import Client, filters

    app = Client("my_bot")


    @app.on_message(filters.command("balance"))
    async def balance(client, message):
        await client.send_ephemeral_message(
            chat_id=message.chat.id,
            receiver_id=message.from_user.id,
            text=f"Your balance is {get_balance(message.from_user.id)} Stars.",
        )


    app.run()

``chat_id`` is the group it appears in; ``receiver_id`` is the only person who will see it.
Both are required — an ephemeral message with no receiver has nowhere to go.

Keyboards, replies and rich text
--------------------------------

The message is otherwise a normal one. It takes a ``reply_markup``, so a private prompt can
carry buttons; ``reply_parameters``, so it can quote the message that triggered it; and
``rich_text`` with ``rich_text_media`` for a full :doc:`rich message <rich-messages>`:

.. code-block:: python

    from wzgram.types import InlineKeyboardMarkup, InlineKeyboardButton

    await app.send_ephemeral_message(
        chat_id=group_id,
        receiver_id=user_id,
        text="Only you can see this. Continue?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes", callback_data="go"),
            InlineKeyboardButton("No", callback_data="stop"),
        ]]),
    )

``query_id`` answers a guest bot query with an ephemeral message — see
:doc:`guest-mode-and-managed-bots`.

Welcome messages
----------------

*Bot API 10.3 — August 2026*

An ephemeral message sent with ``welcome=True`` is not delivered once. The server keeps it
as a template and shows it to each user the first time they open the chat, so a bot can
greet everyone without posting anything the whole group sees:

.. code-block:: python

    await app.send_ephemeral_message(
        chat_id=group_id,
        receiver_id=user_id,
        text="Welcome! Read the rules before posting.",
        welcome=True,
    )

The RPC still takes a receiver even for a template, so pass one; the stored message is
shown to everyone who arrives regardless of who it names.

The stored templates are listed and removed separately from ordinary ephemeral messages,
because they outlive the send:

.. code-block:: python

    for message in await app.get_welcome_messages(group_id):
        print(message.id, message.text)

    await app.delete_welcome_message(group_id, message_id)
    await app.delete_all_welcome_messages(group_id)

A message parsed back from ``get_welcome_messages`` has ``is_welcome_template`` set, which
is what separates a stored template from a message that happened to be sent once.

Sending or managing them needs the ``can_send_welcome_messages`` administrator right:

.. code-block:: python

    from wzgram.types import ChatPrivileges

    await app.promote_chat_member(
        group_id, bot_id,
        ChatPrivileges(can_send_welcome_messages=True),
    )

Anchoring and protection
------------------------

*Bot API 10.3 — August 2026*

``anchor=True`` keeps the message beside the message it replies to instead of at the bottom
of the chat, which is what an inline correction or a per-message hint wants.
``protect_content`` and ``show_caption_above_media`` behave as they do elsewhere.

.. code-block:: python

    await app.send_ephemeral_message(
        chat_id=group_id,
        receiver_id=user_id,
        text="That command needs an argument.",
        reply_parameters=ReplyParameters(message_id=message.id),
        anchor=True,
    )

From any send method
--------------------

*Bot API 10.3 — August 2026*

Bot API 10.3 sends an ephemeral message by adding ``ephemeral_message_parameters`` to an
ordinary send method rather than by calling a separate one. :meth:`~pyrogram.Client.send_message`,
:meth:`~pyrogram.Client.send_rich_message`, :meth:`~pyrogram.Client.send_cached_media` and the
twelve that send one kind of media take it:

.. code-block:: python

    from wzgram.types import EphemeralMessageParameters

    await app.send_photo(
        chat_id, "chart.png", caption="Only you can see this",
        ephemeral_message_parameters=EphemeralMessageParameters(
            receiver_user_id=user_id
        ),
    )

Answering a callback query with one is what the other two fields are for:

.. code-block:: python

    @app.on_callback_query()
    async def pressed(client, query):
        await client.send_message(
            query.message.chat.id, "Only you can see this",
            ephemeral_message_parameters=EphemeralMessageParameters(
                receiver_user_id=query.from_user.id,
                callback_query_id=query.id,
                replace_callback_query_message=True,
            ),
        )

``replace_callback_query_message`` anchors the ephemeral message to the message the button
was on, which is how a client shows one in place of another. It must be False for a callback
query that came from an ephemeral message — edit those with
:meth:`~pyrogram.Client.edit_ephemeral_message_text` instead.

The RPC behind ephemeral messages is not ``messages.sendMedia`` and has fewer fields, so
``disable_notification``, ``schedule_date``, ``send_as``, ``effect_id`` and the rest of that
family have nowhere to go. They are **logged and dropped** rather than silently ignored —
watch for ``ephemeral.sendMessage has no field for …`` in your log.

Editing one
-----------

*Bot API 10.3 — August 2026*

Layer 229 added ``ephemeral.editMessage``; before it an ephemeral message could only be
sent and deleted. Four methods edit one, and each names the receiver again, because the
message only ever existed for them:

.. code-block:: python

    await app.edit_ephemeral_message_text(chat_id, receiver_id, sent.id, "Updated")
    await app.edit_ephemeral_message_caption(chat_id, receiver_id, sent.id, "New caption")
    await app.edit_ephemeral_message_media(chat_id, receiver_id, sent.id, InputMediaPhoto("new.jpg"))
    await app.edit_ephemeral_message_reply_markup(chat_id, receiver_id, sent.id, markup)

Pass ``welcome=True`` when the message being edited is a stored welcome template rather
than one that was delivered once.

Unlike :meth:`~pyrogram.Client.send_ephemeral_message`, the text form takes a built
:obj:`~pyrogram.types.InputRichMessage` as ``rich_message`` rather than a string: a rich
message that has to be composed is composed once and edited many times.

Bound methods
-------------

A :obj:`~pyrogram.types.Message` that arrived as an ephemeral one carries everything the edit
and delete RPCs need, so it edits and deletes itself:

.. code-block:: python

    sent = await app.send_ephemeral_message(chat_id, user_id, "Working…")

    await sent.edit_ephemeral_text("Done")
    await sent.edit_ephemeral_reply_markup(markup)
    await sent.delete_ephemeral()

``edit_ephemeral`` and ``reply_ephemeral`` are aliases of the ``_text`` forms, matching
``edit`` and ``reply``. They are separate from :meth:`~pyrogram.types.Message.edit_text` and
:meth:`~pyrogram.types.Message.delete` on purpose — those send ``messages.editMessage``, which
is the wrong request for a message that is not in the chat's history. Calling an ephemeral
shortcut on an ordinary message raises rather than sending it.

:obj:`~pyrogram.types.Message.is_ephemeral` says which kind you have.

Replying to any message with an ephemeral one needs no identifiers at all — it goes to
whoever sent it, quoting it:

.. code-block:: python

    @app.on_message(filters.command("balance"))
    async def balance(client, message):
        await message.reply_ephemeral_text(f"You have {get_balance(message.from_user.id)}")

A message that is itself ephemeral keeps the conversation private. ``reply``, ``answer``
and the media shortcuts built on the send methods that take ``ephemeral_message_parameters``
send their message as an ephemeral one to the other side — the sender of a message you
received, or the receiver of one you sent — so a user's ephemeral command is never answered
in front of the whole group. The same holds for a button pressed on an ephemeral
message:

.. code-block:: python

    @app.on_callback_query()
    async def pressed(client, query):
        await query.message.reply("Only you can see this")

A reply quotes the message when it came from the other side. Telegram refuses a quote of an
ephemeral message you sent yourself, so a reply to one of those is sent without the quote.

Polls, dice, games, invoices, paid media, checklists, media groups and inline bot results
cannot be ephemeral: Telegram refuses them in ``ephemeral.sendMessage`` or strips them from it.
Their ``reply_*`` and ``answer_*`` shortcuts raise :class:`ValueError` on an ephemeral message
rather than post the answer to a private message for the whole chat. Call the client method,
such as :meth:`~pyrogram.Client.send_poll`, to post one publicly on purpose.

Deleting one
------------

.. code-block:: python

    await app.delete_ephemeral_message(
        chat_id=group_id,
        receiver_id=user_id,
        message_id=sent.id,
    )

The receiver has to be named again, because the message only ever existed for them.

Gotchas
-------

- ``disable_web_page_preview`` is accepted and **ignored**. The RPC behind ephemeral
  messages has no link preview field; the parameter is kept so existing call sites do not
  break. ``edit_ephemeral_message_text`` takes no such parameter at all, for the same
  reason.
- These messages are not in the chat history. Do not expect
  :meth:`~pyrogram.Client.get_messages` to find one, and do not build a flow that needs to
  read it back — hold what you need in your own state.
- Everything about them is per-receiver. To tell three people something privately, send
  three messages. A welcome message is the exception: it is stored once and shown to
  everyone who arrives.
