Client Settings
===============

:obj:`~pyrogram.Client` takes a lot of arguments. Most have a default you never need to
touch; the ones on this page are the ones worth knowing about, grouped by what they change.

The full list with types and descriptions is in the :obj:`~pyrogram.Client` reference.


-----

How your client appears
-----------------------

Telegram shows every logged-in client in **Settings → Devices → Active Sessions**. By default
yours reads:

-   Device Model: ``CPython x.y.z``
-   Application: ``wzgram x.y.z``, where x.y.z is the wzgram version
-   System Version: the platform wzgram detects

Change any of it:

.. code-block:: python

    app = Client(
        "my_account",
        app_version="MyApp 1.2.3",
        device_model="PC",
        system_version="Linux",
    )

``client_platform`` (:obj:`~pyrogram.enums.ClientPlatform`) is a separate, structured hint
Telegram uses for feature availability — set it to what your program actually is rather than
leaving it ``OTHER`` if it matters to you.

Language
--------

``lang_code`` tells Telegram which language to speak in terms of service, bot replies and
service messages. It takes an `ISO 639-1 <https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes>`_
code and defaults to ``"en"``:

.. code-block:: python

    app = Client("my_account", lang_code="it")

``system_lang_code`` and ``lang_pack`` exist for completeness and rarely need changing.

Where the session lives
-----------------------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 30 20 50

    ``name``, —, "session name; becomes ``<name>.session`` on disk"
    ``workdir``, "the parent dir", "where that file is written"
    ``in_memory``, ``None``, "keep the session in memory only, discarded on stop"
    ``session_string``, ``None``, "resume from an exported string instead of a file"
    ``storage_engine``, ``None``, "another engine: MongoDB, Redis, hybrid, or your own"

See :doc:`storage-engines` for the remote and hybrid engines, and
:doc:`/features/session-strings` for moving a session as text.

An explicit ``storage_engine`` wins over ``session_string``: the string is loaded *into*
that engine rather than replacing it.

Logging in without prompts
--------------------------

Supplying these makes the first login non-interactive, which is what you want in a container
where nobody is at a terminal:

.. csv-table::
    :header: Argument, What it does
    :widths: 30 70

    ``bot_token``, "log in as a bot"
    ``phone_number``, "the number to authorize, instead of asking"
    ``phone_code``, "the login code, if you have a way to obtain it"
    ``password``, "the two-step verification password"
    ``hide_password``, "read the password without echoing it"

.. note::

    A prompt on a host with no terminal **fails** rather than retrying. That is deliberate:
    the retry loop it replaced spun thousands of times a second against an EOF.

Updates
-------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 30 20 50

    ``workers``, "cpu + 4", "dispatcher worker tasks running your handlers"
    ``no_updates``, ``False``, "receive no updates at all — for batch programs"
    ``skip_updates``, ``True``, "drop updates that arrived while you were offline"
    ``auto_no_updates``, ``True``, "wrap read-only calls so they do not generate update traffic"
    ``fetch_replies``, ``True``, "resolve the message a reply points at"
    ``fetch_topics``, ``True``, "resolve the forum topic a message belongs to"
    ``fetch_stories``, ``True``, "resolve stories referenced by a message"
    ``fetch_stickers``, ``True``, "resolve sticker sets"

The four ``fetch_*`` switches each cost an extra lookup per update. Turning off the ones you
never read is the cheapest throughput win available on a busy client.

Rate limiting and floods
------------------------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 30 20 50

    ``sleep_threshold``, ``10``, "seconds of ``FloodWait`` wzgram waits out for you"
    ``rate_limits``, ``None``, "turn on the client-side token buckets (off while ``None``)"

.. code-block:: python

    app = Client(
        "my_bot",
        sleep_threshold=60,
        rate_limits={"media": {"rate": 2, "burst": 4}},
    )

A ``FloodWait`` longer than ``sleep_threshold`` is raised for you to handle. The client-side
limiter is off unless you pass ``rate_limits``; pass ``{}`` to enable it with the built-in
defaults. See :doc:`/features/rate-limiting`.

Transfers and caches
--------------------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 35 15 50

    ``max_concurrent_transmissions``, ``16``, "uploads and downloads running at once"
    ``max_message_cache_size``, ``1000``, "messages held in memory"
    ``max_topic_cache_size``, ``1000``, "forum topics held in memory"

Memory budgets that are process-wide rather than per client — read-ahead, in-flight media,
the peer cache — are environment variables instead, and are listed in
:doc:`/features/performance`.

Conversations
-------------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 35 15 50

    ``max_listeners``, "process-wide 1000", "outstanding :meth:`~pyrogram.Client.listen` waiters"
    ``listener_timeout``, ``300``, "default seconds before a waiter gives up"
    ``unallowed_click_alert``, ``True``, "answer button presses from the wrong user with an alert"
    ``unallowed_click_alert_text``, —, "what that alert says"

See :doc:`/features/listeners`.

Network
-------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 30 20 50

    ``ipv6``, ``False``, "connect over IPv6"
    ``proxy``, ``None``, "SOCKS4/5 or HTTP proxy — see :doc:`proxy`"
    ``test_mode``, ``False``, "use Telegram's test datacenters — see :doc:`test-servers`"
    ``protocol_factory``, "abridged", "the MTProto transport to use"
    ``connection_factory``, ``Connection``, "a custom connection implementation"
    ``init_connection_params``, ``None``, "extra fields for ``InitConnection``"

Text and plugins
----------------

.. csv-table::
    :header: Argument, Default, What it does
    :widths: 30 20 50

    ``parse_mode``, ``DEFAULT``, "global parse mode — see :doc:`text-formatting`"
    ``link_preview_options``, ``None``, "default link preview behaviour for sent messages"
    ``plugins``, ``None``, "Smart Plugins config — see :doc:`smart-plugins`"
    ``takeout``, ``None``, "run the session in takeout mode for bulk export"
