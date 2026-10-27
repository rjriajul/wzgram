Available Methods
=================

This page is about wzgram methods. All the methods listed here are bound to a :class:`~pyrogram.Client` instance,
except for :meth:`~pyrogram.idle()` and :meth:`~pyrogram.compose()`, which are special functions that can be found in
the main package directly.

.. code-block:: python

    from wzgram import Client

    app = Client("my_account")

    with app:
        app.send_message("me", "hi")

-----

.. currentmodule:: pyrogram.Client

Listeners
---------

.. autosummary::
    :nosignatures:

    {listeners}

.. toctree::
    :hidden:

    {listeners}

Utilities
---------

.. autosummary::
    :nosignatures:

    {utilities}

.. toctree::
    :hidden:

    {utilities}

.. currentmodule:: pyrogram

.. autosummary::
    :nosignatures:

    idle
    compose

.. toctree::
    :hidden:

    idle
    compose

.. currentmodule:: pyrogram.Client

Account
--------

.. autosummary::
    :nosignatures:

    {account}

.. toctree::
    :hidden:

    {account}

Messages
--------

.. autosummary::
    :nosignatures:

    {messages}

.. toctree::
    :hidden:

    {messages}

Stickers
--------

.. note::

    The sticker set methods were ported from `kurigram <https://github.com/kurigram-org/kurigram>`_ by
    `KurimuzonAkuma <https://github.com/KurimuzonAkuma>`_ and modified for wzgram.

.. autosummary::
    :nosignatures:

    {stickers}

.. toctree::
    :hidden:

    {stickers}

Chats
-----

.. autosummary::
    :nosignatures:

    {chats}

.. toctree::
    :hidden:

    {chats}

Users
-----

.. autosummary::
    :nosignatures:

    {users}

.. toctree::
    :hidden:

    {users}

Invite Links
------------

.. autosummary::
    :nosignatures:

    {invite_links}

.. toctree::
    :hidden:

    {invite_links}

Contacts
--------

.. autosummary::
    :nosignatures:

    {contacts}

.. toctree::
    :hidden:

    {contacts}

Folders
-------

.. autosummary::
    :nosignatures:

    {folders}

.. toctree::
    :hidden:

    {folders}

Password
--------

.. autosummary::
    :nosignatures:

    {password}

.. toctree::
    :hidden:

    {password}

Bots
----

.. autosummary::
    :nosignatures:

    {bots}

.. toctree::
    :hidden:

    {bots}

Business
---------

.. autosummary::
    :nosignatures:

    {business}

.. toctree::
    :hidden:

    {business}

Payments
---------

.. autosummary::
    :nosignatures:

    {payments}

.. toctree::
    :hidden:

    {payments}

Stories
--------

.. autosummary::
    :nosignatures:

    {stories}

.. toctree::
    :hidden:

    {stories}

Wallet
------

.. autosummary::
    :nosignatures:

    {wallet}

.. toctree::
    :hidden:

    {wallet}

Phone
------

.. autosummary::
    :nosignatures:

    {phone}

.. toctree::
    :hidden:

    {phone}

Premium
--------

.. autosummary::
    :nosignatures:

    {premium}

.. toctree::
    :hidden:

    {premium}

Decorators
-----------

.. autosummary::
    :nosignatures:

    {decorators}

.. toctree::
    :hidden:

    {decorators}

Authorization
--------------

.. autosummary::
    :nosignatures:

    {auth}

.. toctree::
    :hidden:

    {auth}

Advanced
--------

Methods used only when dealing with the raw Telegram API.
Learn more about how to use the raw API at :doc:`Advanced Usage <../../topics/advanced-usage>`.

.. autosummary::
    :nosignatures:

    {advanced}

.. toctree::
    :hidden:

    {advanced}
