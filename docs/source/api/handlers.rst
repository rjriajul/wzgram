Update Handlers
===============

A handler is the object that binds a callback function to a kind of update. Every
:meth:`~pyrogram.Client.on_message`-style decorator builds one of these and registers it for
you; :meth:`~pyrogram.Client.add_handler` takes one directly, which is what you want when
handlers are built at runtime.

.. code-block:: python

    from wzgram import Client, filters
    from wzgram.handlers import MessageHandler


    async def echo(client, message):
        await message.reply(message.text)


    app = Client("my_account")
    app.add_handler(MessageHandler(echo, filters.text & filters.private))
    app.run()

Every handler takes the same two arguments: a ``callback`` and an optional ``filters``. The
callback's second parameter is the parsed update, and which type that is depends on the
handler — a :obj:`~pyrogram.types.Message` for
:class:`~pyrogram.handlers.MessageHandler`, a :obj:`~pyrogram.types.CallbackQuery` for
:class:`~pyrogram.handlers.CallbackQueryHandler`, and so on.

See :doc:`/topics/more-on-updates` for handler groups, propagation and priority.


-----

Messages
--------

.. autoclass:: pyrogram.handlers.MessageHandler()
.. autoclass:: pyrogram.handlers.EditedMessageHandler()
.. autoclass:: pyrogram.handlers.DeletedMessagesHandler()
.. autoclass:: pyrogram.handlers.MessageReactionHandler()
.. autoclass:: pyrogram.handlers.MessageReactionCountHandler()
.. autoclass:: pyrogram.handlers.PollHandler()
.. autoclass:: pyrogram.handlers.StoryHandler()

Business connections
--------------------

.. autoclass:: pyrogram.handlers.BusinessConnectionHandler()
.. autoclass:: pyrogram.handlers.BusinessMessageHandler()
.. autoclass:: pyrogram.handlers.EditedBusinessMessageHandler()
.. autoclass:: pyrogram.handlers.DeletedBusinessMessagesHandler()

Bots
----

.. autoclass:: pyrogram.handlers.CallbackQueryHandler()
.. autoclass:: pyrogram.handlers.InlineQueryHandler()
.. autoclass:: pyrogram.handlers.ChosenInlineResultHandler()
.. autoclass:: pyrogram.handlers.GuestMessageHandler()
.. autoclass:: pyrogram.handlers.ManagedBotUpdatedHandler()
.. autoclass:: pyrogram.handlers.MessageGenerationStoppedHandler()
.. autoclass:: pyrogram.handlers.StartHandler()

Chats and members
-----------------

.. autoclass:: pyrogram.handlers.ChatMemberUpdatedHandler()
.. autoclass:: pyrogram.handlers.ChatJoinRequestHandler()
.. autoclass:: pyrogram.handlers.ChatBoostHandler()
.. autoclass:: pyrogram.handlers.UserStatusHandler()

Payments
--------

.. autoclass:: pyrogram.handlers.PreCheckoutQueryHandler()
.. autoclass:: pyrogram.handlers.ShippingQueryHandler()
.. autoclass:: pyrogram.handlers.PurchasedPaidMediaHandler()

Wallet
------

.. autoclass:: pyrogram.handlers.TonWalletStateHandler()

Client lifecycle
----------------

.. autoclass:: pyrogram.handlers.ConnectHandler()
.. autoclass:: pyrogram.handlers.DisconnectHandler()
.. autoclass:: pyrogram.handlers.StopHandler()
.. autoclass:: pyrogram.handlers.ErrorHandler()

Raw updates
-----------

.. autoclass:: pyrogram.handlers.RawUpdateHandler()

Base class
----------

.. autoclass:: pyrogram.handlers.Handler()
