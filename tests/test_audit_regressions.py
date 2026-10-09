import asyncio
import inspect
import io
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import pyrogram
from pyrogram import enums, raw, types, utils
from pyrogram.dispatcher import Dispatcher
from pyrogram.errors import UserNotParticipant
from pyrogram.handlers import MessageHandler
from pyrogram.methods.bots.get_chat_menu_button import GetChatMenuButton
from pyrogram.methods.messages.delete_scheduled_messages import DeleteScheduledMessages
from pyrogram.methods.messages.edit_message_text import EditMessageText
from pyrogram.methods.messages.get_scheduled_messages import GetScheduledMessages
from pyrogram.methods.messages.send_media_group import SendMediaGroup
from pyrogram.methods.messages.send_message import SendMessage
from pyrogram.methods.messages.send_venue import SendVenue
from pyrogram.methods.rate_limiter import TokenBucket
from pyrogram.parser.markdown import Markdown
from pyrogram.parser.parser import Parser
from pyrogram.types.listeners import registry as registry_module


class _DispatcherClient:
    name = "audit"
    workers = 3
    no_updates = False
    skip_updates = True
    start_handler = None
    stop_handler = None
    rate_limiter = None
    listeners = None

    def __init__(self):
        self.loop = asyncio.get_event_loop()

    async def recover_gaps(self):
        return (0, 0)


def make_dispatcher():
    return Dispatcher(_DispatcherClient())


async def test_a_dispatcher_cycle_does_not_grow_its_lock_list():
    dispatcher = make_dispatcher()

    await dispatcher.start()
    first = len(dispatcher.locks_list)
    await dispatcher.stop()

    await dispatcher.start()
    second = len(dispatcher.locks_list)
    await dispatcher.stop()

    assert first == dispatcher.client.workers
    assert second == first, (
        "every start appends one lock per worker; without a matching clear the "
        f"list grows on each cycle ({first} then {second}) for the life of the client"
    )
    assert not dispatcher.locks_list, (
        "a stopped dispatcher owns no workers, so it must hold no worker locks"
    )


async def test_a_handler_added_across_a_dispatcher_cycle_releases_what_it_took():
    dispatcher = make_dispatcher()

    first = asyncio.Lock()
    blocker = asyncio.Lock()
    await blocker.acquire()

    dispatcher.locks_list = [first, blocker]
    dispatcher.add_handler(MessageHandler(lambda *a: None), 0)

    await asyncio.sleep(0.05)
    assert first.locked(), "the barrier should be mid-acquire"

    dispatcher.locks_list = []
    blocker.release()
    await asyncio.sleep(0.05)

    assert not first.locked(), (
        "add_handler must release the locks it actually took; releasing whatever "
        "locks_list holds at the end leaves a worker lock held forever and the "
        "dispatcher stops delivering updates"
    )


async def test_the_token_bucket_lets_only_one_waiter_wait(monkeypatch):
    import pyrogram.methods.rate_limiter as rate_limiter

    waiters = 8
    bucket = TokenBucket(rate=20, burst=1)
    await bucket.acquire()

    # counting sleeps would be counting the platform clock: time.monotonic has a
    # 15.6ms resolution on Windows before 3.13, so a sleep can report less
    # elapsed than it took and cost a waiter an extra pass. How many waiters are
    # asleep at once is what tells the two designs apart, and it is exact.
    sleeping = 0
    peak = 0
    real_sleep = asyncio.sleep

    async def tracking_sleep(delay, *args, **kwargs):
        nonlocal sleeping, peak

        sleeping += 1
        peak = max(peak, sleeping)

        try:
            return await real_sleep(delay, *args, **kwargs)
        finally:
            sleeping -= 1

    monkeypatch.setattr(rate_limiter.asyncio, "sleep", tracking_sleep)

    order = []

    async def take(i):
        await bucket.acquire()
        order.append(i)

    await asyncio.gather(*(take(i) for i in range(waiters)))

    assert peak == 1, (
        "the wait is served holding the lock, so exactly one waiter is ever "
        f"asleep; {peak} of {waiters} were, which is every waiter waking for a "
        "token all but one of them will not get"
    )
    assert order == list(range(waiters)), (
        f"admission must be first-come-first-served, got {order}"
    )


class _PoolSession:
    def __init__(self, started: bool):
        self.is_started = asyncio.Event()
        self.results = {}
        self.stopped = False

        if started:
            self.is_started.set()

    @property
    def is_restarting(self) -> bool:
        return False

    async def stop(self):
        self.stopped = True


async def test_a_dead_pooled_session_is_stopped_not_orphaned(monkeypatch):
    from tests.test_transfers import (
        MediaSessionPoolFakeAuth as FakeAuth,
        MediaSessionPoolFakeClient as FakeClient,
        MediaSessionPoolFakeSession as FakeSession,
    )

    monkeypatch.setattr(pyrogram.client, "Session", FakeSession)
    monkeypatch.setattr(pyrogram.client, "Auth", FakeAuth)

    client = FakeClient()
    client.loop = asyncio.get_event_loop()

    dead = _PoolSession(started=False)
    client.media_session_pools[2] = [dead]

    await client._get_media_session_pool(2, 2)
    await asyncio.sleep(0.05)

    assert dead.stopped, (
        "a session dropped from the pool is no longer reachable by the reaper, so "
        "dropping it without stopping it leaks its socket and its worker tasks"
    )


async def test_upload_shutdown_does_not_wait_on_workers_that_are_gone():
    from pyrogram.methods.advanced.save_file import _stop_workers

    queue = asyncio.Queue(2)

    async def already_finished():
        return None

    workers = [asyncio.ensure_future(already_finished()) for _ in range(2)]
    await asyncio.sleep(0.05)

    queue.put_nowait("an unsent part")
    queue.put_nowait("another unsent part")

    await asyncio.wait_for(_stop_workers(queue, workers), timeout=5)


async def test_upload_shutdown_gives_up_on_a_worker_that_never_takes_its_sentinel(monkeypatch):
    from pyrogram.methods.advanced.save_file import _stop_workers
    from pyrogram.session import Session

    monkeypatch.setattr(Session, "MEDIA_WAIT_TIMEOUT", 0.1)

    queue = asyncio.Queue(2)
    queue.put_nowait("an unsent part")
    queue.put_nowait("another unsent part")

    async def finished():
        return None

    async def stuck():
        await asyncio.sleep(3600)

    workers = [asyncio.ensure_future(finished()), asyncio.ensure_future(stuck())]
    await asyncio.sleep(0.05)

    results = await asyncio.wait_for(_stop_workers(queue, workers), timeout=5)

    assert workers[1].cancelled(), (
        "a worker that cannot be handed a sentinel must be cancelled, or the "
        "gather that follows waits for it forever"
    )
    assert isinstance(results[1], asyncio.CancelledError), (
        "asking a cancelled task for its exception re-raises instead of returning, "
        "so a cancelled worker must be read from gather"
    )


async def test_editing_a_local_video_names_the_uploaded_file():
    import io

    from pyrogram import raw, types
    from pyrogram.methods.messages.edit_message_media import resolve_input_media

    class _Parser:
        async def parse(self, text, parse_mode):
            return {"message": text, "entities": None}

    class _Client:
        parser = _Parser()
        sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def save_file(self, media, **kwargs):
            if media is None:
                return None

            return raw.types.InputFile(id=1, parts=1, name="f", md5_checksum="")

        def guess_mime_type(self, media):
            return "video/mp4"

        async def invoke(self, query):
            self.sent = query

            return raw.types.MessageMediaDocument(
                document=raw.types.Document(
                    id=1, access_hash=2, file_reference=b"", date=0,
                    mime_type="video/mp4", size=1, dc_id=1, attributes=[]
                )
            )

    async def uploaded_name(media, **kwargs):
        client = _Client()
        await resolve_input_media(client, 1, media, **kwargs)

        for attribute in client.sent.media.attributes:
            if isinstance(attribute, raw.types.DocumentAttributeFilename):
                return attribute.file_name

        raise AssertionError("the upload carried no file name at all")

    buffer = io.BytesIO(b"a video")
    buffer.name = "from_the_buffer.mp4"

    assert await uploaded_name(types.InputMediaVideo(buffer)) == "from_the_buffer.mp4", (
        "with no name given anywhere the upload falls back to the media itself"
    )

    assert await uploaded_name(
        types.InputMediaVideo(buffer, file_name="on_the_media.mp4")
    ) == "on_the_media.mp4", (
        "InputMediaVideo.file_name is documented, so it must reach the wire"
    )

    assert await uploaded_name(
        types.InputMediaVideo(buffer, file_name="on_the_media.mp4"),
        file_name="on_the_call.mp4",
    ) == "on_the_call.mp4", (
        "edit_message_media's own file_name parameter is the more specific of "
        "the two, so it wins"
    )


async def test_reacting_to_a_message_sends_the_emoji():
    from pyrogram import raw
    from pyrogram.methods.messages.send_reaction import SendReaction
    from pyrogram.types import Message

    class _Client(SendReaction):
        sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query, **kwargs):
            self.sent = query

            return True

    async def reaction_of(*args, **kwargs):
        client = _Client()
        message = Message(id=7, chat=object.__new__(type("C", (), {"id": -100})))
        message._client = client

        await message.react(*args, **kwargs)

        return client.sent.reaction

    assert await reaction_of("🔥") == [raw.types.ReactionEmoji(emoticon="🔥")], (
        "react must forward its emoji; sending none is the documented way to "
        "retract, so dropping it turns every reaction into a retraction"
    )

    assert await reaction_of() is None, (
        "react() with no emoji still retracts"
    )

    assert await reaction_of(5875309033427620643) == [
        raw.types.ReactionCustomEmoji(document_id=5875309033427620643)
    ], (
        "an int is a custom emoji document id, not an emoticon string"
    )

    assert await reaction_of(["🔥", 5875309033427620643]) == [
        raw.types.ReactionEmoji(emoticon="🔥"),
        raw.types.ReactionCustomEmoji(document_id=5875309033427620643),
    ], (
        "react documents a list for reacting with several emojis at once"
    )


async def test_clicking_a_url_button_returns_its_url():
    import inspect

    from pyrogram import raw
    from pyrogram.types import (
        InlineKeyboardButton, InlineKeyboardMarkup, Message,
    )

    message = Message(
        id=7,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("open", url="https://example.org"),
        ]]),
    )

    assert await message.click() == "https://example.org", (
        "click reaches the url branch only if the branches before it stop "
        "reading attributes the button does not have"
    )

    raw_button = raw.types.KeyboardInlineButton(
        text="confirm",
        type=raw.types.InlineButtonTypeCallback(data=b"go", requires_password=True),
    )
    button = InlineKeyboardButton.read(raw_button)

    positional = [
        name
        for name in inspect.signature(InlineKeyboardButton.__init__).parameters
    ][1:]

    assert positional[:3] == ["text", "callback_data", "url"], (
        "InlineKeyboardButton is built positionally in Pyrogram code this "
        "library has to stay a drop-in replacement for, so a new parameter "
        f"belongs at the end, never inserted: {positional}"
    )

    assert button.requires_password, (
        "the flag is on the wire, so it has to survive the read or click can "
        "never tell a password button from an ordinary one"
    )
    assert (await button.write(None)).type == raw_button.type, (
        "and it has to survive the write, or a bot cannot build one"
    )


async def test_clicking_a_password_button_forwards_the_password():
    from pyrogram.types import (
        InlineKeyboardButton, InlineKeyboardMarkup, Message,
    )

    class _Client:
        asked = None

        async def request_callback_answer(self, **kwargs):
            self.asked = kwargs

            return True

    message = Message(
        id=7,
        chat=object.__new__(type("C", (), {"id": -100})),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("confirm", callback_data="go", requires_password=True),
        ]]),
    )
    message._client = _Client()

    with pytest.raises(ValueError, match="requires a password"):
        await message.click()

    await message.click(password="hunter2")

    assert message._client.asked["password"] == "hunter2", (
        "a password button always carries callback data, so the password has "
        "to be forwarded from the callback branch or it is never sent at all"
    )


async def test_restricting_a_member_sends_the_granular_permissions():
    import logging

    from pyrogram import raw
    from pyrogram.methods.chats.restrict_chat_member import RestrictChatMember
    from pyrogram.methods.chats.set_chat_permissions import SetChatPermissions
    from pyrogram.types import ChatPermissions

    class _Client(RestrictChatMember, SetChatPermissions):
        sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query):
            self.sent = query

            return raw.types.messages.ChatFull(
                full_chat=None, chats=[None], users=[]
            )

    async def rights_of(call, permissions):
        client = _Client()

        try:
            await call(client, permissions)
        except AttributeError:
            pass

        return client.sent.banned_rights

    allowed = ChatPermissions(
        can_send_messages=True, can_send_photos=True, can_send_videos=True
    )

    for call, label in [
        (lambda c, p: c.restrict_chat_member(-100, 1, p), "restrict_chat_member"),
        (lambda c, p: c.set_chat_permissions(-100, p), "set_chat_permissions"),
    ]:
        rights = await rights_of(call, allowed)

        assert rights.send_photos is False, (
            f"{label} granted photos, so the ban flag must say photos are not "
            "banned; hand-rolling the rights drops every granular field"
        )
        assert rights.send_videos is False, f"{label} granted videos"
        assert rights.send_media is not True, (
            f"{label}: can_send_media_messages defaults to None, so `not None` "
            "bans all media on a call that never mentioned it"
        )
        assert rights.send_reactions is not None, (
            f"{label} must decide reactions, or a muted user keeps reacting"
        )
        assert rights.manage_topics is not None, (
            f"{label} must decide topics, or a muted user keeps managing them"
        )

    logging.disable(logging.WARNING)
    try:
        legacy = await rights_of(
            lambda c, p: c.restrict_chat_member(-100, 1, p),
            ChatPermissions(can_send_messages=True, can_send_media_messages=True),
        )
    finally:
        logging.disable(logging.NOTSET)

    assert legacy.send_media is False and legacy.send_photos is None, (
        "the deprecated can_send_media_messages still has to work on its own, "
        "without the granular flags contradicting it"
    )


async def test_lifecycle_decorators_reach_the_client():
    import pyrogram
    from pyrogram.handlers import (
        ConnectHandler, DisconnectHandler, MessageHandler, StartHandler,
        StopHandler,
    )

    fired = []

    class _Client:
        name = "lifecycle"
        workers = 1
        no_updates = True
        skip_updates = True
        rate_limiter = None
        listeners = None
        start_handler = None
        stop_handler = None
        connect_handler = None
        disconnect_handler = None

        def __init__(self):
            self.loop = asyncio.get_event_loop()
            self.dispatcher = Dispatcher(self)

        async def recover_gaps(self):
            return (0, 0)

        add_handler = pyrogram.Client.add_handler
        remove_handler = pyrogram.Client.remove_handler

    def callback(name):
        async def fire(client):
            fired.append(name)

        return fire

    client = _Client()
    slots = {
        StartHandler: "start_handler",
        StopHandler: "stop_handler",
        ConnectHandler: "connect_handler",
        DisconnectHandler: "disconnect_handler",
    }
    registered = {
        handler_type: client.add_handler(handler_type(callback(attribute)))[0]
        for handler_type, attribute in slots.items()
    }

    for handler_type, attribute in slots.items():
        assert callable(getattr(client, attribute)), (
            f"{handler_type.__name__} is a lifecycle callback, so add_handler "
            "must put it on the client; parking it in dispatcher group 0 means "
            "it can never match an update and never runs"
        )

    assert not client.dispatcher.groups, (
        "no lifecycle handler belongs in a dispatcher group"
    )

    await client.dispatcher.start()
    await asyncio.sleep(0.05)
    await client.dispatcher.stop()

    assert fired == ["start_handler", "stop_handler"], (
        f"the dispatcher runs both around its own lifecycle, got {fired}"
    )

    for handler in registered.values():
        client.remove_handler(handler)

    for attribute in slots.values():
        assert getattr(client, attribute) is None, (
            f"remove_handler must clear {attribute}, not leave it firing"
        )

    client.add_handler(MessageHandler(callback("message")))
    await asyncio.sleep(0.05)

    assert [type(h).__name__ for h in client.dispatcher.groups[0]] == ["MessageHandler"], (
        "an ordinary handler still belongs to the dispatcher"
    )


async def test_removing_a_handler_spares_another_callback_of_the_same_type():
    import pyrogram
    from pyrogram.handlers import StartHandler

    class _Client:
        start_handler = None
        stop_handler = None
        connect_handler = None
        disconnect_handler = None
        dispatcher = None

        add_handler = pyrogram.Client.add_handler
        remove_handler = pyrogram.Client.remove_handler

    async def mine(client):
        pass

    async def theirs(client):
        pass

    client = _Client()
    client.add_handler(StartHandler(theirs))
    installed = client.add_handler(StartHandler(mine))[0]

    client.remove_handler(StartHandler(theirs))

    assert client.start_handler is mine, (
        "matching on type alone lets unloading one plugin clear whatever "
        "on_start another plugin installed, which the loader's exclude= path "
        "does on every run"
    )

    client.remove_handler(installed)

    assert client.start_handler is None, (
        "removing the callback that is actually installed still clears it"
    )


async def test_editing_a_folder_keeps_what_was_not_passed():
    from pyrogram import raw
    from pyrogram.methods.chats.edit_folder import EditFolder

    def make_folder():
        return raw.types.DialogFilter(
            id=2,
            title=raw.types.TextWithEntities(text="Work", entities=[]),
            pinned_peers=[raw.types.InputPeerUser(user_id=1, access_hash=1)],
            include_peers=[raw.types.InputPeerUser(user_id=2, access_hash=2)],
            exclude_peers=[raw.types.InputPeerUser(user_id=3, access_hash=3)],
            contacts=True,
            exclude_muted=True,
            emoticon="\U0001f4bc"
        )

    class _Parser:
        async def parse(self, text, parse_mode):
            return {"message": text, "entities": None}

    class _Client(EditFolder):
        parser = _Parser()

        def __init__(self, folder):
            self.folder = folder
            self.sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerUser(user_id=9, access_hash=9)

        async def invoke(self, query):
            if isinstance(query, raw.functions.messages.GetDialogFilters):
                return raw.types.messages.DialogFilters(filters=[self.folder])

            self.sent = query

            return True

    client = _Client(make_folder())

    await client.edit_folder(2, excluded_chats=["spam"])

    sent = client.sent.filter

    assert sent.title.text == "Work", (
        "editing a folder without a name must not blank its title"
    )
    assert len(sent.pinned_peers) == 1, (
        "editing a folder without pinned_chats must not drop its pinned chats"
    )
    assert len(sent.include_peers) == 1, (
        "editing a folder without included_chats must not drop its included chats"
    )
    assert sent.contacts is True and sent.exclude_muted is True, (
        "editing a folder must not reset the flags that were not passed"
    )
    assert sent.emoticon == "\U0001f4bc", (
        "editing a folder without an icon must not drop its icon"
    )
    assert [p.user_id for p in sent.exclude_peers] == [9], (
        "excluded_chats must replace the excluded peers it was given"
    )

    client = _Client(make_folder())

    await client.edit_folder(2, animate_custom_emoji=None)

    assert client.sent.filter.title_noanimate is None, (
        "omitting animate_custom_emoji must not switch name animation off"
    )


async def test_editing_a_shared_folder_rejects_a_field_it_cannot_carry():
    import pytest

    from pyrogram import raw
    from pyrogram.methods.chats.edit_folder import EditFolder

    class _Parser:
        async def parse(self, text, parse_mode):
            return {"message": text, "entities": None}

    folder = raw.types.DialogFilterChatlist(
        id=3,
        title=raw.types.TextWithEntities(text="Shared", entities=[]),
        pinned_peers=[],
        include_peers=[]
    )

    class _Client(EditFolder):
        parser = _Parser()
        sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query):
            if isinstance(query, raw.functions.messages.GetDialogFilters):
                return raw.types.messages.DialogFilters(filters=[folder])

            self.sent = query

            return True

    client = _Client()

    with pytest.raises(ValueError, match="excluded_chats"):
        await client.edit_folder(3, excluded_chats=["spam"])

    assert client.sent is None, (
        "an unsupported field must be rejected before the folder is written back"
    )


async def test_editing_a_folder_can_still_clear_its_color():
    from pyrogram import enums, raw
    from pyrogram.methods.chats.edit_folder import EditFolder

    class _Client(EditFolder):
        def __init__(self):
            self.folder = raw.types.DialogFilter(
                id=2,
                title=raw.types.TextWithEntities(text="Work", entities=[]),
                pinned_peers=[],
                include_peers=[],
                exclude_peers=[],
                color=3
            )
            self.sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query):
            if isinstance(query, raw.functions.messages.GetDialogFilters):
                return raw.types.messages.DialogFilters(filters=[self.folder])

            self.sent = query

            return True

    client = _Client()

    await client.edit_folder(2, color=enums.FolderColor.NO_COLOR)

    assert client.sent.filter.color is None, (
        "FolderColor.NO_COLOR must clear the color, not be read as no color given"
    )

    client = _Client()

    await client.edit_folder(2, color=enums.FolderColor.RED)

    assert client.sent.filter.color == 0, (
        "FolderColor.RED carries value 0 and must not be read as no color given"
    )

    client = _Client()

    await client.edit_folder(2, name=None)

    assert client.sent.filter.color == 3, (
        "an edit that does not mention the color must leave it alone"
    )


async def test_the_folder_edit_shortcut_keeps_its_own_pinned_chats():
    from pyrogram import types

    class _Client:
        sent = None

        async def edit_folder(self, **kwargs):
            _Client.sent = kwargs

            return True

    def chat(chat_id):
        return types.Chat(id=chat_id)

    folder = types.Folder(
        client=_Client(),
        id=2,
        name="Work",
        pinned_chats=[chat(1)],
        included_chats=[chat(1), chat(2)],
        excluded_chats=[chat(3)]
    )

    await folder.edit(exclude_muted=True)

    assert _Client.sent["pinned_chats"] == [1], (
        "editing a folder must fall back to its own pinned chats, "
        "not to its included chats"
    )

    await folder.edit(name="Work")

    assert _Client.sent["pinned_chats"] == [1], (
        "editing a folder must fall back to its own pinned chats, "
        "not to its included chats"
    )
    assert _Client.sent["included_chats"] == [1, 2], (
        "editing a folder must keep its included chats"
    )
    assert _Client.sent["excluded_chats"] == [3], (
        "editing a folder must keep its excluded chats"
    )


async def test_inviting_to_an_empty_folder_does_not_crash():
    from pyrogram import types

    class _Client:
        sent = None

        async def create_folder_invite_link(self, **kwargs):
            _Client.sent = kwargs

            return True

    folder = types.Folder(client=_Client(), id=2, name="Work")

    await folder.create_invite_link()

    assert _Client.sent["chat_ids"] == [], (
        "a folder with no included chats must send an empty chat list, not raise"
    )


async def test_a_peer_that_never_changes_is_still_written_back(tmp_path, monkeypatch):
    import time

    from pyrogram.storage import caching

    from pyrogram.storage import SQLiteStorage

    async def age(storage, peer_id, seconds):
        stale = int(time.time()) - seconds

        await storage.conn.execute("DROP TRIGGER trg_peers_last_update_on")
        await storage.conn.execute(
            "UPDATE peers SET last_update_on = ? WHERE id = ?",
            (stale, peer_id)
        )
        await storage.conn.execute(
            "CREATE TRIGGER trg_peers_last_update_on AFTER UPDATE ON peers BEGIN "
            "UPDATE peers SET last_update_on = CAST(STRFTIME('%s','now') AS INTEGER) "
            "WHERE id = NEW.id; END"
        )
        await storage._ensure_committed()

        return stale

    async def stamp_of(storage, peer_id):
        cursor = await storage.conn.execute(
            "SELECT last_update_on FROM peers WHERE id = ?", (peer_id,)
        )

        return (await cursor.fetchone())[0]

    storage = SQLiteStorage("peers", tmp_path)
    await storage.open()

    try:
        peer = (777, 123, "user", None)

        await storage.update_peers([peer])
        await storage.update_usernames([(777, ["bob"])])
        await storage._ensure_committed()

        stale = await age(storage, 777, 3600)
        await storage.update_peers([peer])
        await storage._ensure_committed()

        assert await stamp_of(storage, 777) == stale, (
            "an unchanged peer seen again within the cache window must not be rewritten"
        )

        later = time.monotonic() + storage.USERNAME_TTL
        monkeypatch.setattr(caching.time, "monotonic", lambda: later)

        await storage.update_peers([peer])
        await storage._ensure_committed()

        assert await stamp_of(storage, 777) > stale, (
            "an unchanged peer seen again after the cache window must be rewritten, "
            "or its username expires while the client is still seeing it"
        )

        await storage.get_peer_by_username("bob")

        assert storage._peer_cache.write_ttl < storage.USERNAME_TTL, (
            "a peer row must be rewritten well before the username on it expires"
        )
    finally:
        await storage.close()


async def test_a_phone_number_learned_later_is_stored(tmp_path):
    from pyrogram.storage import SQLiteStorage

    storage = SQLiteStorage("phones", tmp_path)
    await storage.open()

    try:
        await storage.update_peers([(777, 123, "user", None)])
        await storage.update_peers([(777, 123, "user", "+15551234")])
        await storage._ensure_committed()

        await storage.get_peer_by_phone_number("+15551234")
    finally:
        await storage.close()


async def test_the_obfuscated_transports_survive_their_handshake(monkeypatch):
    import asyncio

    from pyrogram.connection.transport.tcp.tcp import TCP
    from pyrogram.connection.transport.tcp.tcp_abridged_o import TCPAbridgedO
    from pyrogram.connection.transport.tcp.tcp_intermediate_o import TCPIntermediateO
    from pyrogram.connection.transport.tcp.tcp_padded_intermediate_o import (
        TCPPaddedIntermediateO,
    )
    from pyrogram.crypto import aes

    for transport_type in (TCPAbridgedO, TCPIntermediateO, TCPPaddedIntermediateO):
        wire = []

        async def connect(self, address):
            return None

        async def send(self, data, *args):
            wire.append(bytes(data))

        monkeypatch.setattr(TCP, "connect", connect)
        monkeypatch.setattr(TCP, "send", send)

        transport = transport_type(False, None, None, asyncio.get_event_loop())

        await transport.connect(("127.0.0.1", 443))

        assert len(wire) == 1 and len(wire[0]) == 64, (
            f"{transport_type.__name__} must send a 64 byte handshake nonce"
        )

        nonce = wire[0]
        peer = (bytes(nonce[8:40]), bytearray(nonce[40:56]), bytearray(1))

        aes.ctr256_decrypt(nonce, *peer)

        await transport.send(b"\x01" * 16)

        plain = aes.ctr256_decrypt(wire[1], *peer)

        assert b"\x01" * 16 in plain, (
            f"{transport_type.__name__} must encrypt its first packet with the "
            "same keystream the peer derives"
        )

        assert not isinstance(transport.encrypt[0], bytearray), (
            f"{transport_type.__name__} must hand the cipher a bytes key"
        )


async def test_the_clients_transport_choice_reaches_the_connection(monkeypatch):
    from pyrogram.connection.transport import TCPAbridgedO
    from pyrogram.session.auth import Auth
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    seen = {}

    class _Recorded(Exception):
        pass

    def record(*args, **kwargs):
        seen.update(kwargs)

        raise _Recorded

    client = DummyClient()
    client.protocol_factory = TCPAbridgedO

    monkeypatch.setattr(client, "connection_factory", record)

    session = Session(client, 1, b"\x00" * 256, False, is_media=False, crypto_executor=None)

    with pytest.raises(_Recorded):
        await session.start(max_attempts=1)

    assert seen.get("protocol_factory") is TCPAbridgedO, (
        "Client(protocol_factory=...) must reach the connection the session opens, "
        f"got {seen.get('protocol_factory')}"
    )

    seen.clear()

    auth = Auth(client, 1, False)

    with pytest.raises(_Recorded):
        await auth.create()

    assert seen.get("protocol_factory") is TCPAbridgedO, (
        "Client(protocol_factory=...) must reach the connection that creates the "
        f"auth key, got {seen.get('protocol_factory')}"
    )


async def test_init_connection_params_reach_the_server(monkeypatch):
    from pyrogram import raw
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    class _Connection:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def close(self):
            pass

    sent = []

    async def send(self, query, *args, **kwargs):
        sent.append(query)

        return None

    monkeypatch.setattr(DummyClient, "connection_factory", _Connection)
    monkeypatch.setattr(Session, "send", send)
    monkeypatch.setattr(Session, "recv_worker", lambda self: asyncio.sleep(0))

    client = DummyClient()
    client.init_connection_params = {"tz_offset": 3600}

    session = Session(client, 1, b"\x00" * 256, False, is_media=False, crypto_executor=None)

    await session.start(max_attempts=1)
    await session.stop()

    init = next(
        q.query for q in sent
        if isinstance(q, raw.functions.InvokeWithLayer)
    )

    assert isinstance(init.params, raw.types.JsonObject), (
        f"init_connection_params must be sent as a JsonObject, got {init.params!r}"
    )
    assert init.params.value[0].key == "tz_offset", (
        "init_connection_params must carry the keys it was given"
    )


async def test_the_clients_connection_factory_is_the_one_that_gets_used(monkeypatch):
    import pyrogram.session.auth as auth_mod
    import pyrogram.session.session as session_mod
    from pyrogram.session.auth import Auth
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    class _FactoryUsed(Exception):
        pass

    class _ModuleGlobalUsed(Exception):
        pass

    def chosen(*args, **kwargs):
        raise _FactoryUsed

    def ignored(*args, **kwargs):
        raise _ModuleGlobalUsed

    monkeypatch.setattr(session_mod, "Connection", ignored)
    monkeypatch.setattr(auth_mod, "Connection", ignored, raising=False)

    client = DummyClient()
    client.connection_factory = chosen

    session = Session(client, 1, b"\x00" * 256, False, is_media=False, crypto_executor=None)

    with pytest.raises(_FactoryUsed):
        await session.start(max_attempts=1)

    with pytest.raises(_FactoryUsed):
        await Auth(client, 1, False).create()


async def test_a_registered_on_connect_callback_actually_runs(monkeypatch):
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    class _Connection:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def close(self):
            pass

    seen = []

    async def on_connect(client, session):
        await asyncio.wait_for(session._wait_started(), timeout=2)

        seen.append((client, session))

    async def send(self, query, *args, **kwargs):
        return None

    monkeypatch.setattr(Session, "send", send)
    monkeypatch.setattr(Session, "recv_worker", lambda self: asyncio.sleep(0))

    client = DummyClient()
    client.connection_factory = _Connection
    client.connect_handler = on_connect

    session = Session(client, 1, b"\x00" * 256, False, is_media=False, crypto_executor=None)
    client.session = session

    await session.start(max_attempts=1)

    assert seen == [(client, session)], (
        "a callback registered with @on_connect must run once the session is up, "
        f"and receive (client, session); got {seen}"
    )

    await session.restart()
    await session.stop()

    assert len(seen) == 2, (
        "on_connect must run again after a reconnect, the way on_disconnect runs "
        f"again after every drop; ran {len(seen)} times"
    )


async def test_on_connect_stays_quiet_when_the_connection_never_came_up(monkeypatch):
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    class _Refused:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            raise OSError("no route to host")

        async def close(self):
            pass

    fired = []

    async def on_connect(client, session):
        fired.append(session)

    client = DummyClient()
    client.connection_factory = _Refused
    client.connect_handler = on_connect

    session = Session(client, 1, b"\x00" * 256, False, is_media=False, crypto_executor=None)
    client.session = session

    with pytest.raises(OSError):
        await session.start(max_attempts=1)

    assert not fired, (
        "on_connect must not run for a connection that never came up"
    )


async def test_the_client_counts_as_connected_while_on_connect_runs(monkeypatch):
    import pyrogram.methods.auth.connect as connect_mod
    from pyrogram.methods.auth.connect import Connect

    seen = {}

    class _Storage:
        conn = object()

        async def dc_id(self):
            return 2

        async def auth_key(self):
            return b"\x00" * 256

        async def test_mode(self):
            return False

        async def server_address(self):
            return None

        async def port(self):
            return None

        async def user_id(self):
            return 12345

    class _Session:
        fails = False

        def __init__(self, client, *args, **kwargs):
            self.client = client

        async def start(self):
            seen["is_connected"] = self.client.is_connected

            if _Session.fails:
                raise OSError("no route to host")

    class _Client(Connect):
        is_connected = False
        ipv6 = False
        crypto_executor = None
        storage = _Storage()

        async def load_session(self):
            pass

    monkeypatch.setattr(connect_mod, "Session", _Session)

    client = _Client()

    assert await client.connect() is True

    assert seen["is_connected"] is True, (
        "an on_connect callback fires from inside Session.start, so the client has "
        "to count as connected by then or client.invoke() raises ConnectionError"
    )

    _Session.fails = True
    client.is_connected = False

    with pytest.raises(OSError):
        await client.connect()

    assert client.is_connected is False, (
        "a connect that never got a session must not leave the client claiming to "
        "be connected"
    )


async def test_a_datacenter_migration_announces_the_new_connection(monkeypatch):
    import pyrogram.client as client_mod
    from pyrogram.errors import PhoneMigrate
    from pyrogram.session.session import Session

    seen = []

    class _Done(Exception):
        pass

    class _DcOption:
        ip_address = "1.2.3.4"
        port = 443

    class _Auth:
        def __init__(self, *args, **kwargs):
            pass

        async def create(self):
            return bytes(256)

    class _Connection:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):
            pass

        async def close(self):
            pass

    async def send(self, query, *args, **kwargs):
        return None

    async def on_connect(client, session):
        seen.append(session.dc_id)

    attempts = []

    async def invoke(query, *args, **kwargs):
        attempts.append(query)

        if len(attempts) == 1:
            raise PhoneMigrate(4)

        raise _Done

    async def get_dc_option(*args, **kwargs):
        return _DcOption()

    monkeypatch.setattr(client_mod, "Auth", _Auth)
    monkeypatch.setattr(Session, "send", send)
    monkeypatch.setattr(Session, "recv_worker", lambda self: asyncio.sleep(0))

    client = pyrogram.Client("migration", api_id=1, api_hash="x", in_memory=True)
    await client.storage.open()

    try:
        await client.storage.dc_id(2)

        client.connection_factory = _Connection
        client.connect_handler = on_connect
        client.session = Session(client, 2, bytes(256), False, crypto_executor=None)

        monkeypatch.setattr(client, "invoke", invoke)
        monkeypatch.setattr(client, "get_dc_option", get_dc_option)

        with pytest.raises(_Done):
            await client.send_code("+10000000000")

        await client.session.stop()
    finally:
        await client.storage.close()

    assert seen == [4], (
        "a datacenter migration stops the old session and opens a new one, so "
        f"on_connect has to run for the new datacenter; got {seen}"
    )


async def test_a_saved_message_does_not_ask_for_a_direct_messages_topic():
    """Saved Messages carries ``saved_peer_id`` to name the saved dialog a message
    belongs to. A monoforum names its topic with the same field, and reports
    ``ChatType.PRIVATE`` like any user chat, so the chat type alone cannot tell the
    two apart: keying on it sends ``messages.GetSavedDialogsByID`` with a user as
    ``parent_peer``, and Telegram answers PARENT_PEER_INVALID. Only a monoforum
    sets ``is_direct_messages``.
    """

    from unittest.mock import Mock

    from pyrogram import raw, types

    asked = []

    client = Mock()
    client.me = Mock(id=7, is_bot=False, is_premium=False)
    client.message_cache = {}
    client.topic_cache = pyrogram.client.Cache(8)
    client.parse_mode = None
    client.fetch_topics = True

    async def get_direct_messages_topics_by_id(chat_id, topic_ids):
        asked.append((chat_id, topic_ids))
        raise AssertionError("a user chat has no direct messages topic to fetch")

    client.get_direct_messages_topics_by_id = get_direct_messages_topics_by_id

    message = raw.types.Message(
        id=1,
        peer_id=raw.types.PeerUser(user_id=7),
        from_id=raw.types.PeerUser(user_id=7),
        saved_peer_id=raw.types.PeerUser(user_id=7),
        date=1700000000,
        restriction_reason=[],
        entities=[],
        message="saved",
    )

    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1, is_self=True
    )}

    parsed = await types.Message._parse(client, message, users, {})

    assert not asked, (
        "Saved Messages is a plain user chat, so parsing a message in it must not "
        f"reach for a direct messages topic; asked {asked}"
    )
    assert parsed.topic is None


async def test_get_users_survives_an_answer_the_server_left_short():
    """``users.getUsers`` answers only for user peers, and drops whatever it will not
    answer for rather than refusing: a channel id, or a user held by an access hash
    the server no longer honours, comes back as a short vector. Indexing that for the
    single-id form raised a bare ``IndexError`` naming nothing.
    """

    from pyrogram import raw
    from pyrogram.methods.users.get_users import GetUsers

    class _Client(GetUsers):
        async def resolve_peer(self, peer_id):
            if peer_id == "durov":
                return raw.types.InputPeerChannel(channel_id=1, access_hash=1)

            return raw.types.InputPeerUser(user_id=2, access_hash=1)

        async def invoke(self, query):
            # the server answers for the user peers only and drops the rest
            return [
                raw.types.User(
                    id=p.user_id, first_name="U", usernames=[], restriction_reason=[],
                    access_hash=1
                )
                for p in query.id
                if isinstance(p, raw.types.InputPeerUser)
            ]

    client = _Client()

    with pytest.raises(ValueError):
        await client.get_users("durov")

    assert (await client.get_users("someone")).id == 2, "a real user still parses"

    with pytest.raises(ValueError):
        await client.get_users(["durov", "someone"])


async def test_a_monoforum_message_still_asks_for_its_direct_messages_topic():
    """The other half of the pairing: a monoforum reports ``ChatType.PRIVATE`` like
    any user chat, so telling the two apart by ``is_direct_messages`` has to keep
    the monoforum fetching the topic it really does own.
    """

    from unittest.mock import Mock

    from pyrogram import raw, types

    asked = []

    client = Mock()
    client.me = Mock(id=7, is_bot=False, is_premium=False)
    client.message_cache = {}
    client.topic_cache = pyrogram.client.Cache(8)
    client.parse_mode = None
    client.fetch_topics = True

    async def get_direct_messages_topics_by_id(chat_id, topic_ids):
        asked.append((chat_id, topic_ids))
        return None

    client.get_direct_messages_topics_by_id = get_direct_messages_topics_by_id

    channel = raw.types.Channel(
        id=100, title="DM", photo=raw.types.ChatPhotoEmpty(), date=0, access_hash=1,
        usernames=[], restriction_reason=[], monoforum=True, broadcast=False, megagroup=False
    )

    message = raw.types.Message(
        id=1,
        peer_id=raw.types.PeerChannel(channel_id=100),
        from_id=raw.types.PeerUser(user_id=7),
        saved_peer_id=raw.types.PeerUser(user_id=42),
        date=1700000000,
        restriction_reason=[],
        entities=[],
        message="m",
    )

    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )}

    parsed = await types.Message._parse(client, message, users, {100: channel})

    assert parsed.chat.is_direct_messages, "a monoforum is what marks a direct messages chat"
    assert parsed.direct_messages_topic_id == 42
    assert asked == [(parsed.chat.id, 42)], (
        f"a monoforum still owns the topic its saved_peer_id names; asked {asked}"
    )


async def test_a_saved_channel_message_does_not_read_a_user_id_off_a_channel():
    """``saved_peer_id`` in Saved Messages is whoever sent the message originally,
    and that can be a channel, which carries no ``user_id`` to read.
    """

    from unittest.mock import Mock

    from pyrogram import raw, types

    client = Mock()
    client.me = Mock(id=7, is_bot=False, is_premium=False)
    client.message_cache = {}
    client.topic_cache = pyrogram.client.Cache(8)
    client.parse_mode = None
    client.fetch_topics = True

    message = raw.types.Message(
        id=1,
        peer_id=raw.types.PeerUser(user_id=7),
        from_id=raw.types.PeerUser(user_id=7),
        saved_peer_id=raw.types.PeerChannel(channel_id=555),
        date=1700000000,
        restriction_reason=[],
        entities=[],
        message="saved from a channel",
    )

    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1, is_self=True
    )}

    parsed = await types.Message._parse(client, message, users, {})

    assert parsed.direct_messages_topic_id is None
    assert parsed.topic is None


def test_a_hidden_read_date_is_not_a_shown_one():
    """``globalPrivacySettings`` carries the *negative* flags ``hide_read_marks`` and
    ``new_noncontact_peers_require_premium``. Both were mapped straight onto the
    positively named ``show_read_date`` and ``allow_new_chats_from_unknown_users``
    with no negation, so every read reported the opposite of the truth, and both
    errors fell on the permissive side. TDLib settles the polarity:
    ``hide_read_marks_ = !show_read_date_``.
    """

    from pyrogram import raw, types

    hidden = types.GlobalPrivacySettings._parse(
        raw.types.GlobalPrivacySettings(
            hide_read_marks=True,
            new_noncontact_peers_require_premium=True,
        )
    )
    assert hidden.show_read_date is False, "a hidden read date is not a shown one"
    assert hidden.allow_new_chats_from_unknown_users is False, (
        "requiring premium of non-contacts is not allowing them"
    )

    shown = types.GlobalPrivacySettings._parse(
        raw.types.GlobalPrivacySettings(
            hide_read_marks=False,
            new_noncontact_peers_require_premium=False,
        )
    )
    assert shown.show_read_date is True
    assert shown.allow_new_chats_from_unknown_users is True

    absent = types.GlobalPrivacySettings._parse(raw.types.GlobalPrivacySettings())
    assert absent.show_read_date is True, "an unset hide flag means the date is shown"
    assert absent.allow_new_chats_from_unknown_users is True

    from io import BytesIO

    written = types.GlobalPrivacySettings(
        show_read_date=False, allow_new_chats_from_unknown_users=False
    ).write()
    assert written.hide_read_marks is True
    assert written.new_noncontact_peers_require_premium is True

    reread = types.GlobalPrivacySettings._parse(
        raw.types.GlobalPrivacySettings.read(BytesIO(written.write()[4:]))
    )
    assert reread.show_read_date is False, "the round trip keeps what was asked for"
    assert reread.allow_new_chats_from_unknown_users is False


def test_an_unspecified_privacy_flag_is_not_a_restriction():
    """``write()`` must not turn "the caller said nothing" into "hide it". A bare
    ``not None`` would have set both restrictions on an object built with neither
    field.
    """

    from pyrogram import types

    written = types.GlobalPrivacySettings().write()

    assert written.hide_read_marks is None, "saying nothing is not asking to hide"
    assert written.new_noncontact_peers_require_premium is None


async def test_asking_to_show_a_read_date_clears_the_hide_flag():
    """The setter reads the live settings and writes back a modified copy, so the
    negation has to happen there too, not only in the type.
    """

    from pyrogram import raw
    from pyrogram.methods.account.set_global_privacy_settings import (
        SetGlobalPrivacySettings,
    )

    sent = []

    class _Client(SetGlobalPrivacySettings):
        async def invoke(self, query):
            if isinstance(query, raw.functions.account.GetGlobalPrivacySettings):
                return raw.types.GlobalPrivacySettings(
                    hide_read_marks=True,
                    new_noncontact_peers_require_premium=True,
                )

            sent.append(query.settings)
            return query.settings

    client = _Client()

    result = await client.set_global_privacy_settings(
        show_read_date=True,
        allow_new_chats_from_unknown_users=True,
    )

    assert sent[0].hide_read_marks is False, (
        "asking to show the read date must clear the hide flag, not set it"
    )
    assert sent[0].new_noncontact_peers_require_premium is False, (
        "allowing unknown users must clear the premium requirement"
    )
    assert result.show_read_date is True, "and the answer reads back the way it was asked"
    assert result.allow_new_chats_from_unknown_users is True


def _progress_client(chunks):
    import asyncio as _asyncio
    from concurrent.futures import ThreadPoolExecutor

    from tests.test_transfers import FakeClient

    client = FakeClient(chunks)
    client.loop = _asyncio.get_event_loop()
    client.executor = ThreadPoolExecutor(1)

    return client


async def test_a_finished_download_says_it_finished(tmp_path):
    """The progress callback was moved onto a task that polls every 0.5s and is
    cancelled the moment the transfer ends, so a download could finish having
    reported nothing at all, and none ever reported the final chunk. Measured
    live, a 12 MB file produced between zero and two calls, the last of them
    claiming 58%.
    """

    from tests.test_transfers import CHUNK, file_id

    for label, chunks, file_size in (
        ("shorter than one chunk", [b"x" * 2048], 2048),
        ("exactly one chunk", [b"a" * CHUNK], CHUNK),
        ("spilling past a chunk", [b"a" * CHUNK, b"b" * 4096], CHUNK + 4096),
    ):
        seen = []

        async def note(current, total):
            seen.append((current, total))

        client = _progress_client(chunks)
        await client.handle_download(
            (file_id(), str(tmp_path), "out.bin", False, file_size, note, ())
        )

        assert seen, f"{label}: a download that transferred bytes reported none"
        assert seen[-1] == (file_size, file_size), (
            f"{label}: the last call must report the whole file, got {seen[-1]}"
        )
        assert all(c <= file_size for c, _ in seen), (
            f"{label}: no call may claim more than the file holds"
        )
        assert seen == sorted(seen), f"{label}: progress must not go backwards"
        assert len(seen) == len(set(seen)), (
            f"{label}: the same value was reported more than once: {seen}"
        )


async def test_a_download_progress_callback_may_be_a_plain_function(tmp_path):
    """The callback is documented as either kind, and the sync branch hands it to
    the executor rather than awaiting it.
    """

    from tests.test_transfers import file_id

    seen = []
    client = _progress_client([b"x" * 4096])

    await client.handle_download(
        (file_id(), str(tmp_path), "out.bin", False, 4096,
         lambda current, total: seen.append((current, total)), ())
    )

    assert seen[-1] == (4096, 4096), f"a plain function is called too, got {seen}"


async def test_progress_args_reach_the_download_callback(tmp_path):
    """``progress_args`` is appended to every call, and the reporter rewrite had to
    keep passing it through.
    """

    from tests.test_transfers import file_id

    seen = []

    async def note(current, total, tag):
        seen.append((current, total, tag))

    client = _progress_client([b"x" * 4096])
    await client.handle_download(
        (file_id(), str(tmp_path), "out.bin", False, 4096, note, ("tag",))
    )

    assert seen[-1] == (4096, 4096, "tag")


async def test_a_finished_upload_says_it_finished(tmp_path):
    """The upload half of the same rewrite. It polled ``file_part``, which counts
    parts handed to a worker rather than parts the server acknowledged, so it both
    over-reported and stopped short of the end.
    """

    from types import SimpleNamespace as NS

    from tests.e2e import CHUNK, FakeDC, make_client

    size = 8 * CHUNK
    path = tmp_path / "up.bin"
    with open(path, "wb") as handle:
        handle.truncate(size)

    dc = FakeDC(size, step=0.00002)
    client = make_client(dc, "upprogress", pool=dc.pool(4))
    client.me = NS(is_bot=False, is_premium=False)
    await client.storage.open()

    seen = []

    async def note(current, total):
        seen.append((current, total))

    await client.save_file(str(path), progress=note)

    assert seen, "an upload that transferred bytes reported none"
    assert seen[-1] == (size, size), (
        f"the last call must report the whole file, got {seen[-1]}"
    )
    assert all(c <= size for c, _ in seen), (
        "no call may claim more bytes than were sent"
    )
    assert seen == sorted(seen), "progress must not go backwards"
    assert len(seen) == len(set(seen)), (
        f"the same value was reported more than once: {seen}"
    )


async def test_stop_transmission_from_the_callback_still_stops_both_ways(tmp_path):
    import pyrogram
    from types import SimpleNamespace as NS

    from tests.e2e import CHUNK, FakeDC, make_client
    from tests.test_transfers import file_id

    calls = []

    async def stop_on_second(current, total):
        calls.append(current)
        if len(calls) == 2:
            raise pyrogram.StopTransmission

    client = _progress_client([b"a" * CHUNK, b"b" * CHUNK, b"c" * CHUNK])
    result = await client.handle_download(
        (file_id(), str(tmp_path), "out.bin", False, 3 * CHUNK, stop_on_second, ())
    )

    assert result is None and not (tmp_path / "out.bin.temp").exists()
    assert len(calls) == 2, f"download kept reporting after the stop: {calls}"

    calls.clear()
    size = 8 * CHUNK
    path = tmp_path / "up.bin"
    path.write_bytes(b"\x01" * size)

    dc = FakeDC(size, step=0.00002)
    client = make_client(dc, "upstop", pool=dc.pool(4))
    client.me = NS(is_bot=False, is_premium=False)
    await client.storage.open()

    with pytest.raises(pyrogram.StopTransmission):
        await client.save_file(str(path), progress=stop_on_second)

    assert len(calls) == 2, f"upload kept reporting after the stop: {calls}"
OWN_ID = 7933658472


def _self_aware_client():
    from types import SimpleNamespace

    from pyrogram import raw
    from tests.test_listeners import FakeClient

    class _Client(FakeClient):
        async def resolve_peer(self, peer_id):
            if peer_id in ("me", "self"):
                return raw.types.InputPeerSelf()

            return raw.types.InputPeerUser(user_id=555, access_hash=1)

    client = _Client(listener_timeout=0.05)

    async def user_id():
        return OWN_ID

    client.storage = SimpleNamespace(user_id=user_id)

    return client


async def test_a_listener_can_wait_on_saved_messages():
    """``resolve_peer("me")`` answers ``InputPeerSelf``, which carries no id, and
    ``get_peer_id`` raised ``ValueError: Peer type invalid`` on it. That killed
    listen, ask, wait_for_message, wait_for_callback_query, stop_listening and
    register_next_step_handler for the commonest peer string in the library.
    """

    from pyrogram.errors import ListenerTimeout
    from pyrogram.methods.listeners.listen import resolve_listener_ids

    client = _self_aware_client()

    assert await resolve_listener_ids(client, "me") == OWN_ID
    assert await resolve_listener_ids(client, "self") == OWN_ID
    assert await resolve_listener_ids(client, "someone") == 555, (
        "a username still resolves the way it always did"
    )
    assert await resolve_listener_ids(client, 42) == 42, "an int is still taken as given"
    assert await resolve_listener_ids(client, None) is None
    assert await resolve_listener_ids(client, ["me", 42]) == [OWN_ID, 42]

    with pytest.raises(ListenerTimeout):
        await asyncio.wait_for(client.listen(chat_id="me"), timeout=2)


async def test_a_listener_on_saved_messages_hears_its_own_chat():
    """Resolving to the right number is only half of it: the listener is filed by
    that id, so a message from Saved Messages has to reach it.
    """

    from pyrogram.enums import ListenerTypes
    from tests.test_listeners import message, waiting

    from pyrogram.methods.listeners.listen import resolve_listener_ids

    client = _self_aware_client()
    resolved = await resolve_listener_ids(client, "me")
    _, future = waiting(client, chat_id=resolved)

    assert await client.listeners.feed(
        client, ListenerTypes.MESSAGE, message(chat_id=OWN_ID)
    ) is True
    assert future.result().chat.id == OWN_ID


async def test_stopping_a_saved_messages_listener_does_not_raise():
    """``stop_listening`` and ``register_next_step_handler`` share the same
    resolver, so they went down with it.
    """

    client = _self_aware_client()

    assert await client.stop_listening(chat_id="me") == 0

    def step(c, m):
        return None

    await client.register_next_step_handler(step, chat_id="me")
    assert await client.stop_listening(chat_id="me") == 1


def test_the_peer_id_behind_a_self_peer_needs_the_session():
    """The helper the fix leans on: every other peer keeps its old answer."""

    from pyrogram import raw, utils

    assert utils.get_peer_id(raw.types.InputPeerUser(user_id=7, access_hash=1)) == 7
    assert utils.get_peer_id(raw.types.InputPeerChat(chat_id=7)) == -7

    with pytest.raises(ValueError):
        utils.get_peer_id(raw.types.InputPeerSelf())


def _history_client(result):
    from pyrogram import raw
    from pyrogram.methods.messages.delete_chat_history import DeleteChatHistory

    class _Client(DeleteChatHistory):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=1, access_hash=1)

        async def invoke(self, query):
            return result

    return _Client()


async def test_clearing_a_channel_reads_the_update_that_answers():
    """``channels.deleteHistory`` answers with a plain ``Updates``, whose order is
    not contractual and which can be empty. Taking ``updates[0].messages`` raised
    ``AttributeError`` on the default call for a supergroup, where the server hides
    the history and sends ``updateChannelAvailableMessages``, and ``IndexError``
    whenever there was nothing left to delete.
    """

    from pyrogram import raw

    deleted = raw.types.Updates(
        updates=[raw.types.UpdateDeleteChannelMessages(
            channel_id=1, messages=[2, 3, 4], pts=4, pts_count=3
        )],
        users=[], chats=[], date=0, seq=0,
    )
    assert await _history_client(deleted).delete_chat_history(-100) == 3

    hidden = raw.types.Updates(
        updates=[raw.types.UpdateChannelAvailableMessages(
            channel_id=1, available_min_id=5
        )],
        users=[], chats=[], date=0, seq=0,
    )
    assert await _history_client(hidden).delete_chat_history(-100) == 0, (
        "a hidden history deleted no messages, and saying so beats crashing"
    )

    empty = raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)
    assert await _history_client(empty).delete_chat_history(-100) == 0, (
        "there was nothing to delete, which is not an IndexError"
    )

    unordered = raw.types.Updates(
        updates=[
            raw.types.UpdateChannelAvailableMessages(channel_id=1, available_min_id=5),
            raw.types.UpdateDeleteChannelMessages(
                channel_id=1, messages=[2, 3], pts=4, pts_count=2
            ),
        ],
        users=[], chats=[], date=0, seq=0,
    )
    assert await _history_client(unordered).delete_chat_history(-100) == 2, (
        "the answer is found by type, not by position"
    )


async def test_clearing_a_private_history_still_counts_the_old_way():
    """Only the channel branch changed; a user or basic group peer still reports
    what ``messages.affectedHistory`` carried.
    """

    from pyrogram import raw
    from pyrogram.methods.messages.delete_chat_history import DeleteChatHistory

    class _Client(DeleteChatHistory):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerUser(user_id=1, access_hash=1)

        async def invoke(self, query):
            return raw.types.messages.AffectedHistory(pts=9, pts_count=7, offset=0)

    assert await _Client().delete_chat_history(1) == 7


def test_a_buffer_without_a_name_still_gets_one():
    """Uploads accept any binary stream, and ``save_file`` already falls back with
    ``getattr(fp, "name", "file.jpg")``. The naming layer then read ``.name`` bare,
    so an ``io.BytesIO`` built from generated bytes raised ``AttributeError`` in
    seven send methods, three of which have no ``file_name`` parameter to work
    around it with.
    """

    import io as _io
    import pathlib

    from pyrogram import utils

    assert utils.get_file_name(_io.BytesIO(b"x"), fallback="file.zip") == "file.zip"

    named = _io.BytesIO(b"x")
    named.name = "kept.mp4"
    assert utils.get_file_name(named, fallback="file.zip") == "kept.mp4"
    assert utils.get_file_name(named, file_name="wins.mp4", fallback="file.zip") == "wins.mp4"

    assert utils.get_file_name("dir/on_disk.png", fallback="file.zip") == "on_disk.png"
    assert utils.get_file_name(pathlib.PurePath("dir/on_disk.png")) == "on_disk.png"


def test_a_stream_that_is_not_a_bytesio_is_still_a_stream():
    """The helper tested only for ``io.BytesIO``, so any other binary stream fell
    through to ``pathlib.Path(media)`` and raised ``TypeError``.
    """

    import io as _io

    from pyrogram import utils

    class _Stream(_io.RawIOBase):
        name = "opened.bin"

        def readable(self):
            return True

    assert utils.get_file_name(_Stream(), fallback="file.zip") == "opened.bin"

    class _Anonymous(_io.RawIOBase):
        def readable(self):
            return True

    assert utils.get_file_name(_Anonymous(), fallback="file.zip") == "file.zip"


def test_guessing_a_mime_type_survives_a_nameless_buffer():
    """``guess_mime_type`` is what the whole InputMedia family and
    ``edit_message_media`` reach first, and it read ``.name`` off any BytesIO.
    """

    import io as _io

    import pyrogram

    client = pyrogram.Client("mimeguess", api_id=1, api_hash="x", in_memory=True)

    assert client.guess_mime_type(_io.BytesIO(b"x")) is None, (
        "an unnamed buffer has nothing to guess from, which is not a crash"
    )

    named = _io.BytesIO(b"x")
    named.name = "a.png"
    assert client.guess_mime_type(named) == "image/png"
    assert client.guess_mime_type("a.png") == "image/png"


@pytest.mark.parametrize("name,mime", [
    ("a.mts", None),
    ("a.ts", None),
    ("a.jxl", "image/jxl"),
    ("a.avif", "image/avif"),
    ("a.heic", "image/heic"),
    ("a.md", "text/markdown"),
    ("a.fb2", "application/x-fictionbook+xml"),
    ("a.sqlite", "application/vnd.sqlite3"),
])
def test_guessed_mime_types_do_not_depend_on_the_python_version(name, mime):
    client = pyrogram.Client.__new__(pyrogram.Client)

    assert client.guess_mime_type(name) == mime


class _CapturedUpload(Exception):
    pass


def _upload_capturing_client(base):
    from pyrogram import enums, raw

    class _Client(base):
        sent = None
        parse_mode = enums.ParseMode.DISABLED

        def rnd_id(self):
            return 1

        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

        async def save_file(self, path, **kwargs):
            if path is None:
                return None

            return raw.types.InputFile(id=1, parts=1, name="x", md5_checksum="")

        async def invoke(self, query, **kwargs):
            _Client.sent = query
            raise _CapturedUpload

        def guess_mime_type(self, filename):
            import pyrogram

            return pyrogram.Client.guess_mime_type(self, filename)

        mimetypes = __import__("mimetypes").MimeTypes()

    client = _Client()

    from pyrogram.parser import Parser

    client.parser = Parser(client)

    return client


async def _uploaded_attributes(client, coro):
    with pytest.raises(_CapturedUpload):
        await coro

    return client.sent.media


async def test_sending_a_nameless_buffer_names_it_on_the_wire():
    """The seven singular send methods read ``.name`` straight off the caller's
    stream. ``send_media_group`` and ``send_paid_media`` next door already used
    ``getattr(i.media, "name", "video.mp4")``, so the crash was an inconsistency
    inside the same package rather than a documented limit.
    """

    import io as _io

    from pyrogram import raw
    from pyrogram.methods.messages.send_document import SendDocument
    from pyrogram.methods.messages.send_sticker import SendSticker

    def name_of(media):
        for attribute in media.attributes:
            if isinstance(attribute, raw.types.DocumentAttributeFilename):
                return attribute.file_name

        raise AssertionError("the upload carried no file name at all")

    client = _upload_capturing_client(SendDocument)
    media = await _uploaded_attributes(
        client, client.send_document(1, _io.BytesIO(b"generated"))
    )
    assert name_of(media) == "file.zip"
    assert media.mime_type == "application/zip"

    named = _io.BytesIO(b"generated")
    named.name = "kept.txt"
    media = await _uploaded_attributes(client, client.send_document(1, named))
    assert name_of(media) == "kept.txt", "a stream that has a name keeps it"

    media = await _uploaded_attributes(
        client, client.send_document(1, _io.BytesIO(b"x"), file_name="chosen.csv")
    )
    assert name_of(media) == "chosen.csv", "file_name still wins"

    sticker = _upload_capturing_client(SendSticker)
    media = await _uploaded_attributes(
        sticker, sticker.send_sticker(1, _io.BytesIO(b"webp"))
    )
    assert name_of(media) == "sticker.webp", (
        "send_sticker has no file_name parameter, so the fallback is the only way"
    )


def test_something_that_is_not_a_name_falls_back():
    """The helper reached ``pathlib.Path(media)`` with whatever it was handed and
    raised ``TypeError`` on anything that was not a path.
    """

    from pyrogram import utils

    for odd in (None, b"raw", 5, object()):
        assert utils.get_file_name(odd, fallback="file.zip") == "file.zip"


def test_guessing_a_mime_type_reads_any_stream():
    """``guess_mime_type`` tested for ``io.BytesIO`` alone, so an open file went to
    ``mimetypes.guess_type`` as an object and raised ``TypeError`` - which
    edit_message_media walks straight into, since it passes the media itself.
    """

    import io as _io
    import pathlib
    import tempfile

    import pyrogram

    client = pyrogram.Client("mimeany", api_id=1, api_hash="x", in_memory=True)

    path = pathlib.Path(tempfile.mkdtemp()) / "real.png"
    path.write_bytes(b"x")

    with open(path, "rb") as handle:
        assert client.guess_mime_type(handle) == "image/png"

    assert client.guess_mime_type(pathlib.PurePath("a/b.png")) == "image/png"

    for odd in (None, b"raw", 5):
        assert client.guess_mime_type(odd) is None, "a guess that cannot be made is None"

    named = _io.BytesIO(b"x")
    named.name = "a.mp4"
    assert client.guess_mime_type(named) == "video/mp4"


async def test_an_edited_media_is_named_after_its_kind():
    """The InputMedia types asked for a name with no fallback, so a nameless
    buffer put an empty DocumentAttributeFilename on the wire and the message
    arrived with no file name at all.
    """

    import io as _io

    from pyrogram import raw, types
    from pyrogram.methods.messages.edit_message_media import resolve_input_media

    class _Parser:
        async def parse(self, text, parse_mode):
            return {"message": text, "entities": None}

    class _Client:
        parser = _Parser()
        sent = None

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerSelf()

        async def save_file(self, media, **kwargs):
            if media is None:
                return None

            return raw.types.InputFile(id=1, parts=1, name="f", md5_checksum="")

        def guess_mime_type(self, media):
            import pyrogram

            return pyrogram.Client.guess_mime_type(self, media)

        mimetypes = __import__("mimetypes").MimeTypes()

        async def invoke(self, query):
            self.sent = query

            return raw.types.MessageMediaDocument(
                document=raw.types.Document(
                    id=1, access_hash=2, file_reference=b"", date=0,
                    mime_type="video/mp4", size=1, dc_id=1, attributes=[]
                )
            )

    async def uploaded_name(media, **kwargs):
        client = _Client()
        await resolve_input_media(client, 1, media, **kwargs)

        for attribute in client.sent.media.attributes:
            if isinstance(attribute, raw.types.DocumentAttributeFilename):
                return attribute.file_name

        raise AssertionError("the upload carried no file name at all")

    buffer = _io.BytesIO(b"generated")

    assert await uploaded_name(types.InputMediaVideo(buffer)) == "video.mp4"
    assert await uploaded_name(types.InputMediaDocument(buffer)) == "file.zip"
    assert await uploaded_name(types.InputMediaAudio(buffer)) == "audio.mp3"
    assert await uploaded_name(types.InputMediaAnimation(buffer)) == "animation.mp4"

    named = _io.BytesIO(b"generated")
    named.name = "kept.mp4"
    assert await uploaded_name(types.InputMediaVideo(named)) == "kept.mp4", (
        "a stream that has a name still keeps it"
    )


async def test_a_fallback_name_keeps_the_mime_type_its_method_documents():
    """The fallback name is what the mime is guessed from, so an invented
    extension quietly decides what goes on the wire. Every fallback must guess
    back to the default its own method already declared, and send_voice - whose
    fallback feeds nothing else, since a voice note carries no file name - takes
    none at all so that ``audio/mpeg`` still applies.
    """

    import io as _io

    from pyrogram.methods.messages.send_animation import SendAnimation
    from pyrogram.methods.messages.send_audio import SendAudio
    from pyrogram.methods.messages.send_document import SendDocument
    from pyrogram.methods.messages.send_sticker import SendSticker
    from pyrogram.methods.messages.send_video import SendVideo
    from pyrogram.methods.messages.send_video_note import SendVideoNote
    from pyrogram.methods.messages.send_voice import SendVoice

    cases = [
        (SendDocument, "send_document", "application/zip"),
        (SendVideo, "send_video", "video/mp4"),
        (SendAudio, "send_audio", "audio/mpeg"),
        (SendAnimation, "send_animation", "video/mp4"),
        (SendSticker, "send_sticker", "image/webp"),
        (SendVoice, "send_voice", "audio/mpeg"),
        (SendVideoNote, "send_video_note", "video/mp4"),
    ]

    for base, name, documented in cases:
        client = _upload_capturing_client(base)
        media = await _uploaded_attributes(
            client, getattr(client, name)(1, _io.BytesIO(b"generated"))
        )

        assert media.mime_type == documented, (
            f"{name} sends {media.mime_type} for a nameless stream, but documents "
            f"{documented}; the fallback name must not change what goes on the wire"
        )


def _flood_session(amounts):
    import collections
    from types import SimpleNamespace

    from pyrogram import raw
    from pyrogram.errors import FloodWait
    from pyrogram.session.session import Session

    session = Session.__new__(Session)
    session.is_started = asyncio.Event()
    session.is_started.set()
    session.client = SimpleNamespace(name="flood")
    session.last_used = 0.0
    session.flood_history = collections.deque(maxlen=50)
    session._dynamic_backoff = float(Session.SLEEP_THRESHOLD)
    session._last_flood_decay = 0.0
    session.sent = []
    session.slept = []

    queue = list(amounts)

    async def send(query, timeout=None):
        session.sent.append(query)

        if queue:
            raise FloodWait(queue.pop(0))

        return "answered"

    session.send = send

    return session


async def _drive(session, sleep_threshold, monkeypatch):
    from pyrogram import raw

    async def no_wait(amount):
        session.slept.append(amount)

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    return await session._invoke(
        raw.functions.help.GetConfig(), retries=10, timeout=5,
        sleep_threshold=sleep_threshold,
    )


async def test_asking_for_no_sleeping_raises_the_flood(monkeypatch):
    """``sleep_threshold=0`` is documented as raising every flood, and it is the
    only way a caller can refuse to be slept. A dynamic backoff raised the bar it
    was compared against to between 10 and 60 seconds, so any flood under that was
    slept through and the setting did nothing.
    """

    from pyrogram.errors import FloodWait

    session = _flood_session([3])

    with pytest.raises(FloodWait):
        await _drive(session, 0, monkeypatch)

    assert session.slept == [], "asking for no sleeping must not sleep"


async def test_a_flood_under_the_threshold_is_still_slept(monkeypatch):
    """The ordinary case has to keep working: one short flood, one sleep, one
    answer.
    """

    session = _flood_session([3])

    assert await _drive(session, 10, monkeypatch) == "answered"
    assert session.slept == [3]


async def test_a_flood_that_never_lets_up_gives_up(monkeypatch):
    """A server that keeps answering FLOOD_WAIT 3 met a branch that slept, retried,
    and never decremented ``retries`` - so a single call looped for as long as the
    server kept saying no. Observed live: fifty waits and counting on one
    unpin_all_chat_messages, killed rather than returned.
    """

    from pyrogram.errors import FloodWait

    session = _flood_session([3] * 500)

    with pytest.raises(FloodWait):
        await _drive(session, 10, monkeypatch)

    assert sum(session.slept) <= 10 * 10, (
        "the total time spent sleeping on floods is bounded by the threshold "
        "the caller allowed"
    )
    assert len(session.slept) < 500, "it must stop asking long before the server does"


async def test_a_caller_can_still_choose_to_wait_forever(monkeypatch):
    """A negative threshold has always meant "sleep through anything", and the
    bound must not take that away.
    """

    session = _flood_session([3] * 40)

    assert await _drive(session, -1, monkeypatch) == "answered"
    assert len(session.slept) == 40


async def test_creating_a_group_unwraps_the_answer_it_gets():
    """``messages.createChat`` returned ``Updates`` at layer 158 and the method read
    ``r.chats[0]`` off it. The layer 227 bump changed the return type to
    ``messages.InvitedUsers``, which carries the real ``Updates`` in a field of its
    own and has no ``chats`` at all, so every call raised AttributeError.
    """

    from pyrogram import raw, types
    from pyrogram.methods.chats.create_group import CreateGroup

    class _Client(CreateGroup):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query):
            return raw.types.messages.InvitedUsers(
                updates=raw.types.Updates(
                    updates=[],
                    users=[],
                    chats=[raw.types.Chat(
                        id=7, title="made", photo=raw.types.ChatPhotoEmpty(),
                        participants_count=1, date=0, version=1,
                    )],
                    date=0, seq=0,
                ),
                missing_invitees=[],
            )

    chat = await _Client().create_group("made", "me")

    assert isinstance(chat, types.Chat), "the docstring promises a Chat"
    assert chat.id == -7, "and it is the chat the server just made"
    assert chat.title == "made"


async def test_voting_sends_the_option_the_server_named():
    """``messages.sendVote`` takes the ``option:bytes`` the server put on each
    ``pollAnswer``. Poll parsing keeps that as ``persistent_id``, decoded UTF-8,
    but the layer 227 bump renamed the attribute from ``data`` without updating
    this caller, so every vote raised AttributeError before a request was built.
    """

    from types import SimpleNamespace

    from pyrogram import raw, types
    from pyrogram.methods.messages.vote_poll import VotePoll

    answers = [
        raw.types.PollAnswer(text=raw.types.TextWithEntities(text=t, entities=[]), option=o)
        for t, o in (("a", b"0"), ("b", b"1"), ("c", b"2"))
    ]
    media_poll = raw.types.MessageMediaPoll(
        poll=raw.types.Poll(id=1, question=raw.types.TextWithEntities(text="q", entities=[]),
                            answers=answers, hash=0),
        results=raw.types.PollResults(results=[], total_voters=0),
    )

    class _Client(VotePoll):
        sent = None

        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

        async def get_messages(self, chat_id, message_id):
            return SimpleNamespace(poll=await types.Poll._parse(self, media_poll))

        async def invoke(self, query):
            _Client.sent = query

            return raw.types.Updates(
                updates=[raw.types.UpdateMessagePoll(poll_id=1, results=media_poll.results,
                                                     poll=media_poll.poll)],
                users=[], chats=[], date=0, seq=0,
            )

    client = _Client()

    await client.vote_poll(1, 2, 0)
    assert _Client.sent.options == [b"0"], (
        "the vote carries the option bytes the server named, not a missing attribute"
    )

    await client.vote_poll(1, 2, [1, 2])
    assert _Client.sent.options == [b"1", b"2"], "and every option for a multi answer poll"


async def test_every_privacy_setting_reaches_the_field_it_belongs_to():
    """The setter reads the live settings and writes a modified copy back, so each
    parameter has to be assigned onto the raw field name, not its own. Seven were;
    show_gift_button was assigned onto itself, and the raw object is slotted, so
    passing it raised AttributeError before the write RPC was sent.
    """

    from pyrogram import raw, types
    from pyrogram.methods.account.set_global_privacy_settings import (
        SetGlobalPrivacySettings,
    )

    sent = []

    class _Client(SetGlobalPrivacySettings):
        async def invoke(self, query):
            if isinstance(query, raw.functions.account.GetGlobalPrivacySettings):
                return raw.types.GlobalPrivacySettings()

            sent.append(query.settings)

            return query.settings

    result = await _Client().set_global_privacy_settings(
        archive_and_mute_new_chats=True,
        keep_unmuted_chats_archived=True,
        keep_chats_from_folders_archived=True,
        show_read_date=False,
        allow_new_chats_from_unknown_users=False,
        incoming_paid_message_star_count=5,
        show_gift_button=True,
    )

    written = sent[0]

    assert written.display_gifts_button is True, (
        "show_gift_button belongs to display_gifts_button on the wire"
    )
    assert written.archive_and_mute_new_noncontact_peers is True
    assert written.keep_archived_unmuted is True
    assert written.keep_archived_folders is True
    assert written.hide_read_marks is True
    assert written.new_noncontact_peers_require_premium is True
    assert written.noncontact_peers_paid_stars == 5
    assert result.show_gift_button is True, "and it reads back the way it was asked"

    assert not set(raw.types.GlobalPrivacySettings.__slots__) - {
        "archive_and_mute_new_noncontact_peers", "keep_archived_unmuted",
        "keep_archived_folders", "hide_read_marks",
        "new_noncontact_peers_require_premium", "display_gifts_button",
        "noncontact_peers_paid_stars", "disallowed_gifts",
    }, "a new raw field means the setter needs a parameter for it"


def test_a_vector_of_objects_survives_a_trailing_field():
    from io import BytesIO

    from pyrogram import raw
    from pyrogram.raw.core import TLObject

    update = raw.types.UpdateShort(
        update=raw.types.UpdatePrivacy(
            key=raw.types.PrivacyKeyPhoneNumber(),
            rules=[raw.types.PrivacyValueAllowAll()],
        ),
        date=1735689600,
    )

    read_back = TLObject.read(BytesIO(update.write()))

    assert isinstance(read_back.update, raw.types.UpdatePrivacy)
    assert [type(rule) for rule in read_back.update.rules] == [
        raw.types.PrivacyValueAllowAll
    ], "a vector of objects stays a vector of objects"
    assert read_back.date == 1735689600, "and the field after it is still there"


def test_a_bare_vector_of_numbers_still_reads_as_numbers():
    from io import BytesIO

    from pyrogram import raw
    from pyrogram.raw.core import TLObject
    from pyrogram.raw.core.primitives import Int, Long, Vector

    assert list(TLObject.read(BytesIO(Vector([7, 8, 9], Int)))) == [7, 8, 9]
    assert list(TLObject.read(BytesIO(Vector([42], Int)))) == [42]
    assert list(TLObject.read(BytesIO(Vector([2 ** 40 + 1], Long)))) == [2 ** 40 + 1]
    assert list(TLObject.read(BytesIO(Vector([], Int)))) == []

    counters = [
        raw.types.messages.SearchCounter(
            filter=raw.types.InputMessagesFilterPhotos(), count=3
        ),
        raw.types.messages.SearchCounter(
            filter=raw.types.InputMessagesFilterVideo(), count=4
        ),
    ]
    read_back = TLObject.read(BytesIO(Vector(counters)))

    assert [counter.count for counter in read_back] == [3, 4], (
        "a bare vector of objects reads as objects too"
    )


def _channel_photos_client(pages, chat_photo_id):
    from types import SimpleNamespace

    from pyrogram import raw

    class _Client:
        searches = []
        me = SimpleNamespace(is_bot=False)

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerChannel(channel_id=1, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            if isinstance(query, raw.functions.channels.GetFullChannel):
                return SimpleNamespace(
                    full_chat=SimpleNamespace(chat_photo=chat_photo_id)
                )

            self.searches.append(query.offset_id)

            return pages.get(query.offset_id, [])

    return _Client()


def _photo(unique_id):
    from types import SimpleNamespace

    return SimpleNamespace(file_id=f"id-{unique_id}", file_unique_id=unique_id)


def _photo_message(message_id, unique_id):
    from types import SimpleNamespace

    return SimpleNamespace(id=message_id, new_chat_photo=_photo(unique_id))


async def test_a_channels_photo_history_is_paged_to_the_end(monkeypatch):
    from pyrogram import types, utils
    from pyrogram.methods.users.get_chat_photos import GetChatPhotos

    pages = {
        0: [_photo_message(30, "c"), _photo_message(20, "b")],
        20: [_photo_message(10, "a")],
        10: [],
    }

    client = _channel_photos_client(pages, "current")

    async def parse_messages(_client, messages, **kwargs):
        return messages

    monkeypatch.setattr(utils, "parse_messages", parse_messages)
    monkeypatch.setattr(types.Photo, "_parse", staticmethod(lambda _c, photo: _photo(photo)))

    got = [photo.file_unique_id async for photo in GetChatPhotos.get_chat_photos(client, 1)]

    assert got == ["current", "c", "b", "a"], (
        "with no limit the generator must walk every page, not stop after the first"
    )
    assert client.searches == [0, 20, 10], "each page must start where the last one ended"

    client.searches.clear()
    capped = [
        photo.file_unique_id
        async for photo in GetChatPhotos.get_chat_photos(client, 1, limit=2)
    ]

    assert capped == ["current", "c"], "a limit still caps the run"


async def test_a_channels_current_photo_is_not_yielded_twice(monkeypatch):
    from pyrogram import types, utils
    from pyrogram.methods.users.get_chat_photos import GetChatPhotos

    newest = _photo_message(30, "c")
    newest.new_chat_photo.file_id = "id-from-a-message"

    client = _channel_photos_client({0: [newest], 30: []}, "c")

    async def parse_messages(_client, messages, **kwargs):
        return messages

    monkeypatch.setattr(utils, "parse_messages", parse_messages)
    monkeypatch.setattr(
        types.Photo, "_parse", staticmethod(lambda _c, photo: _photo(photo))
    )

    got = [
        photo.file_unique_id
        async for photo in GetChatPhotos.get_chat_photos(client, 1, limit=5)
    ]

    assert got == ["c"], (
        "the same photo carries a different file_id depending on where it was "
        "read from, so only file_unique_id can tell the current photo from its "
        "own history entry"
    )


async def test_a_removed_channel_photo_does_not_end_the_walk(monkeypatch):
    from types import SimpleNamespace

    from pyrogram import types, utils
    from pyrogram.methods.users.get_chat_photos import GetChatPhotos

    removed = SimpleNamespace(id=20, new_chat_photo=None)

    pages = {
        0: [_photo_message(30, "b")],
        30: [removed],
        20: [_photo_message(10, "a")],
        10: [],
    }

    client = _channel_photos_client(pages, None)

    async def parse_messages(_client, messages, **kwargs):
        return messages

    monkeypatch.setattr(utils, "parse_messages", parse_messages)
    monkeypatch.setattr(
        types.Photo, "_parse", staticmethod(lambda _c, photo: _photo(photo) if photo else None)
    )

    got = [photo.file_unique_id async for photo in GetChatPhotos.get_chat_photos(client, 1)]

    assert got == ["b", "a"], (
        "a page carrying only a removed photo is not the end of the history"
    )


async def test_all_stories_follows_the_servers_has_more():
    from pyrogram import raw
    from pyrogram.methods.stories.get_all_stories import GetAllStories

    def page(has_more, state):
        return raw.types.stories.AllStories(
            has_more=has_more, count=0, state=state, peer_stories=[],
            chats=[], users=[], stealth_mode=raw.types.StoriesStealthMode()
        )

    pages = [page(True, "s1"), page(False, "s2"), page(True, "s3")]
    asked = []

    class _Client:
        async def invoke(self, query, *args, **kwargs):
            asked.append((query.next, query.state))

            return pages[len(asked) - 1]

    async for _ in GetAllStories.get_all_stories(_Client()):
        pass

    assert asked == [(None, None), (True, "s1")], (
        "has_more means another page, and the state of the page just read is "
        "what asks for it"
    )


async def test_unchanged_stories_end_the_generator_instead_of_crashing():
    from pyrogram import raw
    from pyrogram.methods.stories.get_all_stories import GetAllStories

    class _Client:
        async def invoke(self, query, *args, **kwargs):
            return raw.types.stories.AllStoriesNotModified(
                state="s", stealth_mode=raw.types.StoriesStealthMode()
            )

    async for _ in GetAllStories.get_all_stories(_Client(), state="s"):
        raise AssertionError(
            "passing a state is the documented way to check for changes, and "
            "an unchanged peerset carries no stories to yield"
        )


async def test_all_stories_stops_when_the_state_stops_moving():
    from pyrogram import raw
    from pyrogram.methods.stories.get_all_stories import GetAllStories

    class _Client:
        asked = 0

        async def invoke(self, query, *args, **kwargs):
            self.asked += 1

            if self.asked > 10:
                raise AssertionError("the generator never stopped asking")

            return raw.types.stories.AllStories(
                has_more=True, count=0, state="stuck", peer_stories=[],
                chats=[], users=[], stealth_mode=raw.types.StoriesStealthMode()
            )

    client = _Client()

    async for _ in GetAllStories.get_all_stories(client):
        pass

    assert client.asked == 2, (
        "a page that hands back the state it was asked for has not moved, so "
        "honouring has_more again would just ask for it forever"
    )


def test_a_peer_id_of_none_is_invalid_rather_than_unorderable():
    from pyrogram import utils

    with pytest.raises(ValueError):
        utils.get_peer_type(None)


async def test_a_method_whose_peer_is_required_names_the_missing_peer():
    from pyrogram.methods.messages.summarize_text import SummarizeText

    class _Client:
        is_connected = True

        async def resolve_peer(self, peer_id):
            from pyrogram import utils
            return utils.get_peer_type(peer_id)

        async def invoke(self, query, *args, **kwargs):
            raise AssertionError("a call with no peer must not reach the wire")

    with pytest.raises(ValueError):
        await SummarizeText.summarize_text(_Client(), id=1)


async def test_get_bot_info_without_a_bot_asks_about_the_caller():
    from pyrogram import raw
    from pyrogram.methods.bots.get_bot_info import GetBotInfo

    sent = []

    class _Client:
        async def resolve_peer(self, peer_id):
            raise AssertionError(
                "bots.getBotInfo declares bot as flags.0?InputUser, so omitting "
                "it is how the caller asks about its own bot"
            )

        async def invoke(self, query, *args, **kwargs):
            sent.append(query)
            return raw.types.bots.BotInfo(name="n", about="a", description="d")

    await GetBotInfo.get_bot_info(_Client())

    assert sent[0].bot is None, (
        "an unset flag is what tells the server to answer for the current bot; "
        f"the query carried {sent[0].bot!r} instead"
    )


@pytest.mark.parametrize(
    "bad",
    ["", "!!!!not-base64!!!!", "AQADAgAT", None],
    ids=["empty", "not-base64", "short", "none"],
)
def test_a_file_id_that_cannot_be_read_is_refused_by_value(bad):
    from pyrogram.file_id import FileId

    with pytest.raises(ValueError):
        FileId.decode(bad)


@pytest.mark.parametrize(
    "bad",
    ["", "!!!!not-base64!!!!", "AQADAgAT", None],
    ids=["empty", "not-base64", "short", "none"],
)
def test_a_file_unique_id_that_cannot_be_read_is_refused_by_value(bad):
    from pyrogram.file_id import FileUniqueId

    with pytest.raises(ValueError):
        FileUniqueId.decode(bad)


async def test_downloading_a_malformed_file_id_says_what_is_wrong_with_it():
    import pyrogram

    client = pyrogram.Client("badfileid", api_id=1, api_hash="x", in_memory=True)

    with pytest.raises(ValueError):
        await client.download_media("!!!!not-base64!!!!")


async def test_get_bot_info_still_refuses_a_peer_id_that_is_not_a_peer():
    from pyrogram.methods.bots.get_bot_info import GetBotInfo

    class _Client:
        is_connected = True

        async def resolve_peer(self, peer_id):
            from pyrogram import utils
            return utils.get_peer_type(peer_id)

        async def invoke(self, query, *args, **kwargs):
            raise AssertionError(
                "0 is not a peer id, and it is falsy: treating it as an omitted "
                "flag would quietly answer about the caller's own bot instead"
            )

    with pytest.raises(ValueError):
        await GetBotInfo.get_bot_info(_Client(), 0)


@pytest.mark.parametrize(
    "module, klass, method, extra",
    [
        ("get_bot_name", "GetBotName", "get_bot_name", {}),
        ("get_bot_info_description", "GetBotInfoDescription",
         "get_bot_info_description", {}),
        ("get_bot_info_short_description", "GetBotInfoShortDescription",
         "get_bot_info_short_description", {}),
        ("set_bot_name", "SetBotName", "set_bot_name", {"name": "x"}),
        ("set_bot_info_description", "SetBotInfoDescription",
         "set_bot_info_description", {"description": "x"}),
        ("set_bot_info_short_description", "SetBotInfoShortDescription",
         "set_bot_info_short_description", {"short_description": "x"}),
    ],
)
async def test_a_bot_this_account_does_not_own_is_refused_not_taken_for_itself(
    module, klass, method, extra
):
    import importlib

    mod = importlib.import_module(f"pyrogram.methods.bots.{module}")

    class _Client:
        is_connected = True

        async def resolve_peer(self, peer_id):
            from pyrogram import utils
            return utils.get_peer_type(peer_id)

        async def invoke(self, query, *args, **kwargs):
            raise AssertionError(
                "0 is not a bot id, and it is falsy: leaving the flag unset "
                "would aim the call at the caller's own bot instead"
            )

    fn = getattr(getattr(mod, klass), method)

    with pytest.raises(ValueError):
        await fn(_Client(), for_my_bot=0, **extra)


async def test_a_personal_chat_history_asks_the_server_once(monkeypatch):
    from pyrogram import raw, utils
    from pyrogram.methods.messages.get_user_personal_chat_messages import (
        GetUserPersonalChatMessages,
    )

    class _Message:
        def __init__(self, id):
            self.id = id

    class _Client:
        def __init__(self):
            self.asked = []

        async def resolve_peer(self, peer_id):
            return raw.types.InputUserSelf()

        async def invoke(self, query, *args, **kwargs):
            self.asked.append(query.max_id)
            return [_Message(i) for i in range(26, 6, -1)]

    async def parse_messages(client, history, **kwargs):
        return history

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    client = _Client()
    got = [
        message.id
        async for message in GetUserPersonalChatMessages.get_user_personal_chat_messages(
            client, "me"
        )
    ]

    assert len(got) == 20
    assert client.asked == [0], (
        "messages.getPersonalChannelHistory answers with at most the 20 most "
        "recent messages and returns nothing for a max_id below that window, "
        "so asking a second time costs a round trip and can only come back "
        f"empty; it asked {len(client.asked)} times"
    )


def test_every_get_messages_call_in_the_types_uses_a_real_parameter():
    """Chat._parse_full_chat, _parse_full_user and User._parse_full asked for the
    pinned message with ``pinned=True``, which get_messages has never accepted, so
    get_chat raised TypeError on any private chat or basic group with a pin.
    """

    import inspect
    import re
    from pathlib import Path

    from pyrogram.methods.messages.get_messages import GetMessages

    accepted = set(inspect.signature(GetMessages.get_messages).parameters)
    root = Path(pyrogram.__file__).parent / "types"
    bad = []

    for path in root.rglob("*.py"):
        for call in re.finditer(r"client\.get_messages\(([^)]*)\)", path.read_text(encoding="utf-8")):
            for kw in re.findall(r"(\w+)\s*=", call.group(1)):
                if kw not in accepted:
                    bad.append(f"{path.relative_to(root)}: {kw}")

    assert not bad, bad


async def test_joining_a_chat_unwraps_the_layer_229_result():
    """channels.joinChannel and messages.importChatInvite answer with
    messages.ChatInviteJoinResult since layer 229; the Ok variant wraps the old
    Updates. join_chat still read .chats[0] off the wrapper and raised
    AttributeError after every successful join.
    """

    from pyrogram import raw
    from pyrogram.methods.chats.join_chat import JoinChat

    channel = raw.types.Channel(id=7, title="t", photo=raw.types.ChatPhotoEmpty(), date=0, megagroup=True, usernames=[], restriction_reason=[])

    class _Client(JoinChat):
        INVITE_LINK_RE = pyrogram.Client.INVITE_LINK_RE

        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            return raw.types.messages.ChatInviteJoinResultOk(
                updates=raw.types.Updates(updates=[], users=[], chats=[channel], date=0, seq=0)
            )

    chat = await _Client().join_chat("somegroup")

    assert chat.id == -1000000000007
    assert chat.title == "t"


async def test_the_contacts_member_filter_carries_its_query():
    """channelParticipantsContacts requires q; the filter was not in the
    queryable list, so filter.value() was called without it and raised TypeError.
    """

    from pyrogram import enums, raw
    from pyrogram.methods.chats.get_chat_members import get_chunk

    sent = {}

    class _Client:
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=1, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            sent["filter"] = query.filter  # noqa

            return raw.types.channels.ChannelParticipants(count=0, participants=[], chats=[], users=[])

    await get_chunk(_Client(), 1, 0, enums.ChatMembersFilter.CONTACTS, 10, "")

    assert isinstance(sent["filter"], raw.types.ChannelParticipantsContacts)
    assert sent["filter"].q == ""


async def test_a_formatted_poll_question_writes_its_entities():
    """A FormattedText question, explanation or description put its MessageEntity
    objects straight into the raw poll without awaiting write(), so the request
    failed to serialise: expected a bytes-like object, coroutine found.
    """

    from unittest.mock import AsyncMock

    from pyrogram import enums, raw, types
    from pyrogram.methods.messages.send_poll import SendPoll

    captured = {}

    async def invoke(query, *args, **kw):
        captured["query"] = query

        return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    client = AsyncMock()
    client.invoke = invoke
    client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
    client.rnd_id = lambda: 1
    client.parser.parse = AsyncMock(return_value={"message": "x", "entities": []})

    bold = [types.MessageEntity(type=enums.MessageEntityType.BOLD, offset=0, length=1)]

    await SendPoll.send_poll(
        client,
        chat_id=1,
        question=types.FormattedText(text="Q?", entities=bold),
        options=["a", "b"],
        type=enums.PollType.QUIZ,
        correct_option_id=0,
        explanation=types.FormattedText(text="why", entities=bold),
        description=types.FormattedText(text="d", entities=bold),
    )

    query = captured["query"]

    assert isinstance(query.media.poll.question.entities[0], raw.types.MessageEntityBold)
    assert isinstance(query.media.solution_entities[0], raw.types.MessageEntityBold)
    assert isinstance(query.entities[0], raw.types.MessageEntityBold)
    query.write()


def _input_photo_from_file_id(*args, **kwargs):
    from pyrogram import raw

    _input_photo_from_file_id.calls.append((args, kwargs))

    return raw.types.InputMediaPhoto(id=raw.types.InputPhoto(id=1, access_hash=1, file_reference=b""))
_input_photo_from_file_id.calls = []


def _sending_client(captured):
    from unittest.mock import AsyncMock

    from pyrogram import raw

    async def invoke(query, *args, **kw):
        captured["query"] = query

        return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    client = AsyncMock()
    client.invoke = invoke
    client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
    client.rnd_id = lambda: 1
    client.parser.parse = AsyncMock(return_value={"message": "plain", "entities": None})

    return client


async def test_a_media_group_carries_explicit_caption_entities(monkeypatch):
    """send_media_group parsed only caption + parse_mode and never looked at the
    caption_entities every InputMedia accepts, so explicit entities were dropped.
    """

    from pyrogram import enums, raw, types, utils
    from pyrogram.methods.messages.send_media_group import SendMediaGroup

    monkeypatch.setattr(utils, "get_input_media_from_file_id", _input_photo_from_file_id)
    captured = {}
    client = _sending_client(captured)
    bold = [types.MessageEntity(type=enums.MessageEntityType.BOLD, offset=0, length=2)]

    await SendMediaGroup.send_media_group(
        client, 1, [types.InputMediaPhoto("AgACAgfake", caption="hi", caption_entities=bold)]
    )

    single = captured["query"].multi_media[0]

    assert single.message == "hi"
    assert isinstance(single.entities[0], raw.types.MessageEntityBold)


async def test_copying_a_media_group_keeps_the_source_formatting(monkeypatch):
    """copy_media_group fed the plain caption of each source message to the
    markdown parser instead of forwarding its caption_entities, so bold and
    italic vanished and any literal markup character was reinterpreted.
    """

    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pyrogram import enums, raw, types, utils
    from pyrogram.methods.messages.copy_media_group import CopyMediaGroup

    monkeypatch.setattr(utils, "get_input_media_from_file_id", _input_photo_from_file_id)
    captured = {}
    client = _sending_client(captured)
    bold = [types.MessageEntity(type=enums.MessageEntityType.BOLD, offset=0, length=3)]
    source = SimpleNamespace(
        photo=SimpleNamespace(file_id="AgACAgfake"), audio=None, document=None, video=None,
        caption="one_two", caption_entities=bold, has_media_spoiler=None,
    )
    client.get_media_group = AsyncMock(return_value=[source])

    await CopyMediaGroup.copy_media_group(client, 1, 2, 3)

    single = captured["query"].multi_media[0]

    assert single.message == "one_two", "the caption is forwarded verbatim, not re-parsed"
    assert isinstance(single.entities[0], raw.types.MessageEntityBold)


async def test_a_spoiler_survives_a_send_by_file_id(monkeypatch):
    """The upload and URL branches of every send_* passed has_spoiler, the
    file_id branch did not (nor ttl_seconds in animation, audio and sticker), so
    copying a spoilered video or re-sending a cached photo lost the spoiler.
    """

    from pyrogram import types, utils
    from pyrogram.methods.messages.send_animation import SendAnimation
    from pyrogram.methods.messages.send_media_group import SendMediaGroup
    from pyrogram.methods.messages.send_photo import SendPhoto

    monkeypatch.setattr(utils, "get_input_media_from_file_id", _input_photo_from_file_id)
    _input_photo_from_file_id.calls.clear()
    client = _sending_client({})

    await SendPhoto.send_photo(client, 1, "AgACAgfake", has_spoiler=True)
    await SendAnimation.send_animation(client, 1, "CgACAgfake", has_spoiler=True, ttl_seconds=5)
    await SendMediaGroup.send_media_group(client, 1, [types.InputMediaPhoto("AgACAgfake", has_spoiler=True)])

    kwargs = [call[1] for call in _input_photo_from_file_id.calls]

    assert [k.get("has_spoiler") for k in kwargs] == [True, True, True]
    assert kwargs[1]["ttl_seconds"] == 5


async def test_a_session_string_is_loaded_into_a_fresh_session_file(tmp_path):
    """Client handed the session string to an explicit storage engine, but only
    the in-memory branch of SQLiteStorage.open loaded it; a fresh session file
    (FileStorage, or SQLiteStorage with in_memory=False) came up with no auth
    key and start() fell into the phone-number prompt.
    """

    from pyrogram.storage.file_storage import FileStorage
    from pyrogram.storage.memory_storage import MemoryStorage
    from pyrogram.storage.sqlite_storage import SQLiteStorage

    source = MemoryStorage(":memory:")
    await source.open()
    await source.dc_id(2)
    await source.api_id(1)
    await source.test_mode(False)
    await source.auth_key(b"\x07" * 256)
    await source.user_id(4242)
    await source.is_bot(False)
    await source.port(443)
    await source.server_address("149.154.167.51")
    string = await source.export_session_string()
    await source.close()

    for storage in (
        FileStorage("fresh_file", workdir=tmp_path),
        SQLiteStorage("fresh_sqlite", workdir=tmp_path, session_string=string),
    ):
        storage.session_string = string
        await storage.open()

        assert await storage.user_id() == 4242, type(storage).__name__
        assert await storage.auth_key() == b"\x07" * 256, type(storage).__name__

        await storage.close()


async def test_downloading_a_story_hands_its_media_to_download_media():
    """Story.download passed the Story itself as ``message``; download_media only
    unwraps a Message, so it fell through to ``media.file_id`` and raised
    AttributeError - taking Story.copy and copy_story down with it.
    """

    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pyrogram import types

    client = SimpleNamespace(download_media=AsyncMock(return_value="path"))
    photo = SimpleNamespace(file_id="AgACAgfake")
    story = types.Story(client=client, id=1, photo=photo)

    assert await story.download() == "path"
    assert client.download_media.await_args.kwargs["message"] is photo

    with pytest.raises(ValueError):
        await types.Story(client=client, id=2).download()


def test_a_chosen_inline_result_keeps_a_64_bit_inline_message_id():
    """ChosenInlineResult packed only the 32-bit inputBotInlineMessageID by hand
    and left inline_message_id as None for the inputBotInlineMessageID64 the
    server sends now, so a bot could never edit the message it just placed.
    """

    from pyrogram import raw, types, utils

    msg_id = raw.types.InputBotInlineMessageID64(dc_id=2, owner_id=3, id=4, access_hash=5)
    update = raw.types.UpdateBotInlineSend(user_id=1, query="q", id="r", msg_id=msg_id)

    result = types.ChosenInlineResult._parse(None, update, {1: raw.types.User(id=1, usernames=[], restriction_reason=[])})

    assert result.inline_message_id == utils.pack_inline_message_id(msg_id)
    assert utils.unpack_inline_message_id(result.inline_message_id) == msg_id


async def test_a_client_throttles_itself_only_when_it_was_asked_to():
    """The client-side limiter used to be built unconditionally, so every invoke()
    paid a token bucket the caller never asked for: broadcasts serialised at the
    per-category rate on top of a 30/s global bucket, and seven TokenBuckets plus
    their locks were allocated per client. It is opt-in now, and the four sites
    that reach for it -- invoke, the dispatcher, initialize and terminate -- all
    have to keep tolerating None.
    """

    from types import SimpleNamespace

    from pyrogram import raw
    from pyrogram.methods.rate_limiter import RateLimiter

    def a_client(**kwargs):
        return pyrogram.Client("ratelimit", api_id=1, api_hash="x", in_memory=True, **kwargs)

    assert a_client().rate_limiter is None, (
        "a client nobody asked to throttle must not build a limiter"
    )

    opted_in = a_client(rate_limits={})
    assert isinstance(opted_in.rate_limiter, RateLimiter), (
        "an empty dict is still a request for the limiter, at the built-in defaults"
    )
    assert opted_in.rate_limiter._buckets["message"].rate == 20.0

    tuned = a_client(rate_limits={"message": {"rate": 1.0}})
    assert tuned.rate_limiter._buckets["message"].rate == 1.0, "the override reaches its bucket"
    assert tuned.rate_limiter._buckets["media"].rate == 5.0, "the rest keep their defaults"

    # invoke() must not reach the limiter at all when there is none to reach.
    acquired = []

    async def recording_acquire(self, category, tokens=1.0):
        acquired.append(category)

    async def run_invoke(client):
        client.is_connected = True
        client.session = SimpleNamespace(invoke=lambda *a, **k: _answer())
        client.fetch_peers = _nothing
        await client.invoke(raw.functions.help.GetConfig())

    async def _answer():
        return raw.types.Config

    async def _nothing(*args, **kwargs):
        return None

    original = RateLimiter.acquire
    RateLimiter.acquire = recording_acquire

    try:
        await run_invoke(a_client())
        assert acquired == [], "an opted-out client must not wait on a bucket"

        await run_invoke(a_client(rate_limits={}))
        assert acquired == ["query"], (
            "an opted-in client still classifies the call and waits on its bucket"
        )
    finally:
        RateLimiter.acquire = original


def test_upload_name_is_a_basename_not_a_local_path(tmp_path):
    import io
    import os

    from pyrogram import utils

    path = tmp_path / "holiday.jpg"
    path.write_bytes(b"x")

    with open(path, "rb") as fp:
        name = utils.get_file_name(fp, fallback="file.jpg")

    assert name == "holiday.jpg", f"an upload must not carry its local path, got {name!r}"
    assert os.sep not in name and "/" not in name

    assert utils.get_file_name(io.BytesIO(b"x"), fallback="file.jpg") == "file.jpg"

    named = io.BytesIO(b"x")
    named.name = "clip.mp4"
    assert utils.get_file_name(named, file_name="", fallback="video.mp4") == "clip.mp4"
    assert utils.get_file_name(named, file_name="pinned.mp4", fallback="video.mp4") == "pinned.mp4"
    assert utils.get_file_name(str(path), fallback="video.mp4") == "holiday.jpg"


class _PasswordClient:
    def __init__(self, hint):
        algo = pyrogram.raw.types.PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow(
            salt1=b"salt1", salt2=b"salt2", g=3, p=pyrogram.utils.itob((1 << 127) - 1)
        )
        self.password = pyrogram.raw.types.account.Password(
            new_algo=algo,
            new_secure_algo=pyrogram.raw.types.SecurePasswordKdfAlgoUnknown(),
            secure_random=b"r",
            has_password=True,
            current_algo=algo,
            srp_B=pyrogram.utils.itob(12345),
            srp_id=1,
            hint=hint,
        )
        self.sent = None

    async def invoke(self, query):
        if isinstance(query, pyrogram.raw.functions.account.GetPassword):
            return self.password

        self.sent = pyrogram.raw.functions.account.UpdatePasswordSettings.read(
            BytesIO(query.write()[4:])
        )
        return True


@pytest.mark.parametrize(
    "stored,passed,expected",
    [
        ("old hint", None, "old hint"),
        (None, None, ""),
        ("old hint", "new hint", "new hint"),
        ("old hint", "", ""),
    ],
)
@pytest.mark.asyncio
async def test_changing_the_password_keeps_the_hint_unless_told_otherwise(stored, passed, expected):
    client = _PasswordClient(stored)

    kwargs = {} if passed is None else {"new_hint": passed}
    assert await pyrogram.Client.change_cloud_password(client, "old", "new", **kwargs) is True

    assert client.sent.new_settings.hint == expected


@pytest.mark.parametrize("style", [pyrogram.enums.ParseMode.HTML, pyrogram.enums.ParseMode.MARKDOWN])
def test_a_mention_survives_copy_and_pickle(style):
    import copy
    import pickle

    from pyrogram.types.user_and_chats.user import Link

    link = Link("tg://user?id=1", "A <b> & B", style)
    copies = [copy.copy(link), copy.deepcopy(link)] + [
        pickle.loads(pickle.dumps(link, protocol)) for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
    ]

    for copied in copies:
        assert type(copied) is Link
        assert copied == link
        assert (copied.url, copied.text, copied.style) == (link.url, link.text, link.style)
        assert copied("other") == link("other")
_FILTERED_DECORATORS = sorted(
    name for name in dir(pyrogram.Client)
    if name.startswith("on_")
    and name not in {"on_start", "on_stop", "on_connect", "on_disconnect", "on_error"}
)


def _unbound_registration(decorator):
    def callback(*args):
        pass

    decorator(callback)
    [(handler, group)] = callback.handlers
    return handler, group


@pytest.mark.parametrize("name", _FILTERED_DECORATORS)
@pytest.mark.parametrize(
    "call,expected_filter,expected_group",
    [
        (lambda on, f: on(), None, 0),
        (lambda on, f: on(f), "f", 0),
        (lambda on, f: on(f, 2), "f", 2),
        (lambda on, f: on(f, group=2), "f", 2),
        (lambda on, f: on(filters=f), "f", 0),
        (lambda on, f: on(filters=f, group=2), "f", 2),
        (lambda on, f: on(group=2), None, 2),
        (lambda on, f: on(None, 2), None, 2),
    ],
)
def test_an_unbound_decorator_keeps_its_filter_and_group(name, call, expected_filter, expected_group):
    f = pyrogram.filters.create(lambda *args: True)

    handler, group = _unbound_registration(call(getattr(pyrogram.Client, name), f))

    assert handler.filters is (f if expected_filter else None)
    assert group == expected_group


def test_an_unbound_decorator_keeps_an_empty_set_filter():
    empty = pyrogram.filters.user([])

    handler, group = _unbound_registration(pyrogram.Client.on_message(filters=empty))

    assert handler.filters is empty
    assert group == 0


@pytest.mark.parametrize(
    "call,expected_exceptions,expected_filter,expected_group",
    [
        (lambda on, f: on(), None, None, 0),
        (lambda on, f: on(ValueError), ValueError, None, 0),
        (lambda on, f: on([ValueError, KeyError]), [ValueError, KeyError], None, 0),
        (lambda on, f: on(ValueError, f), ValueError, "f", 0),
        (lambda on, f: on(ValueError, f, 2), ValueError, "f", 2),
        (lambda on, f: on(ValueError, f, group=2), ValueError, "f", 2),
        (lambda on, f: on(ValueError, filters=f), ValueError, "f", 0),
        (lambda on, f: on(ValueError, group=2), ValueError, None, 2),
        (lambda on, f: on(ValueError, None, 2), ValueError, None, 2),
        (lambda on, f: on(exceptions=ValueError, filters=f, group=2), ValueError, "f", 2),
        (lambda on, f: on(filters=f), None, "f", 0),
        (lambda on, f: on(group=2), None, None, 2),
        (lambda on, f: on(None, f, 2), None, "f", 2),
        (lambda on, f: on(None, None, 2), None, None, 2),
        (lambda on, f: on(ValueError, None, f), ValueError, "f", 0),
    ],
)
def test_an_unbound_error_decorator_keeps_its_exceptions_filter_and_group(
    call, expected_exceptions, expected_filter, expected_group
):
    f = pyrogram.filters.create(lambda *args: True)

    handler, group = _unbound_registration(call(pyrogram.Client.on_error, f))

    expected = expected_exceptions if isinstance(expected_exceptions, list) else (
        [expected_exceptions] if expected_exceptions else [Exception]
    )
    assert list(handler.exceptions) == expected
    assert handler.filters is (f if expected_filter else None)
    assert group == expected_group


def test_a_plugin_registered_with_a_keyword_filter_is_loaded(tmp_path, monkeypatch):
    package = tmp_path / "kwplugins"
    package.mkdir()
    (package / "handlers.py").write_text(
        "from pyrogram import Client, filters\n"
        "\n"
        "@Client.on_message(filters=filters.private, group=4)\n"
        "async def private(client, message):\n"
        "    pass\n"
        "\n"
        "@Client.on_error(ValueError, filters.private, 5)\n"
        "async def failed(client, error, handler, update):\n"
        "    pass\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    client = pyrogram.Client("kw", in_memory=True, plugins={"root": "kwplugins"})
    added = []
    client.add_handler = lambda handler, group=0: added.append((type(handler).__name__, group, handler))

    client.load_plugins()

    by_kind = {kind: (group, handler) for kind, group, handler in added}
    assert by_kind["MessageHandler"][0] == 4
    assert by_kind["MessageHandler"][1].filters is pyrogram.filters.private
    assert by_kind["ErrorHandler"][0] == 5
    assert list(by_kind["ErrorHandler"][1].exceptions) == [ValueError]


def _bare(cls, **fields):
    import inspect

    obj = cls.__new__(cls)
    for name in inspect.signature(cls.__init__).parameters:
        if name not in {"self", "client"}:
            setattr(obj, name, None)
    for name, value in fields.items():
        setattr(obj, name, value)
    return obj


def _sender_filter_cases():
    t = pyrogram.types
    someone = t.User(id=5, username="Someone", is_self=False, is_bot=False)
    me = t.User(id=6, is_self=True, is_bot=False)
    robot = t.User(id=7, is_self=False, is_bot=True)
    group = t.Chat(id=-100)

    return [
        ("message", _bare(t.Message, from_user=someone, chat=group, outgoing=False), someone, None),
        ("channel post", _bare(t.Message, sender_chat=group, chat=group, outgoing=False), None, group),
        ("user status", t.User(id=5, username="Someone", is_self=False, is_bot=False), someone, None),
        ("own status", t.User(id=6, is_self=True, is_bot=False), me, None),
        ("bot status", t.User(id=7, is_self=False, is_bot=True), robot, None),
        ("reaction", _bare(t.MessageReactionUpdated, user=someone, chat=group), someone, None),
        ("own reaction", _bare(t.MessageReactionUpdated, user=me, chat=group), me, None),
        ("anonymous reaction", _bare(t.MessageReactionUpdated, actor_chat=group, chat=group), None, group),
        ("boost", _bare(t.ChatBoostUpdated, boost=_bare(t.ChatBoost, from_user=someone), chat=group), someone, None),
        ("boost without booster", _bare(t.ChatBoostUpdated, boost=_bare(t.ChatBoost), chat=group), None, None),
        ("removed boost", _bare(t.ChatBoostUpdated, chat=group), None, None),
        ("business connection", _bare(t.BusinessConnection, user=someone), someone, None),
        ("managed bot", _bare(t.ManagedBotUpdated, user=someone, bot=robot), someone, None),
        ("callback query", _bare(t.CallbackQuery, from_user=robot), robot, None),
        ("poll", _bare(t.Poll), None, None),
        ("reaction count", _bare(t.MessageReactionCountUpdated, chat=group), None, None),
        ("generation stopped", _bare(t.MessageGenerationStopped, chat=group), None, None),
    ]


@pytest.mark.parametrize(
    "label,update,sender,sender_chat", _sender_filter_cases(), ids=[c[0] for c in _sender_filter_cases()]
)
@pytest.mark.asyncio
async def test_the_sender_filters_read_every_update_type(label, update, sender, sender_chat):
    f = pyrogram.filters

    assert bool(await f.user(5)(None, update)) == bool(sender and sender.id == 5)
    assert bool(await f.user("@someone")(None, update)) == bool(sender and sender.id == 5)
    assert bool(await f.user("me")(None, update)) == bool(sender and sender.is_self)
    assert bool(await f.me(None, update)) == bool(sender and sender.is_self)
    assert bool(await f.bot(None, update)) == bool(sender and sender.is_bot)
    assert bool(await f.sender_chat(None, update)) == bool(sender_chat)

    if getattr(update, "chat", None) is not None:
        assert bool(await f.chat("me")(None, update)) == bool(sender and sender.is_self)


def _chat_filter_cases():
    t = pyrogram.types
    someone = t.User(id=5, is_self=False, is_bot=False)
    private = t.Chat(id=5, type=pyrogram.enums.ChatType.PRIVATE)
    group = t.Chat(id=-100, type=pyrogram.enums.ChatType.SUPERGROUP, is_forum=True, is_admin=True)
    channel = t.Chat(id=-200, type=pyrogram.enums.ChatType.CHANNEL)

    return [
        ("incoming message", _bare(t.Message, from_user=someone, chat=private, outgoing=False), private, False),
        ("outgoing message", _bare(t.Message, from_user=someone, chat=group, outgoing=True), group, True),
        ("channel post", _bare(t.Message, chat=channel, outgoing=False), channel, False),
        ("callback query", _bare(t.CallbackQuery, from_user=someone, message=_bare(t.Message, chat=group)), group, False),
        ("inline callback query", _bare(t.CallbackQuery, from_user=someone), None, False),
        ("inline query", _bare(t.InlineQuery, from_user=someone), None, False),
        ("chosen inline result", _bare(t.ChosenInlineResult, from_user=someone), None, False),
        ("user status", t.User(id=5, is_self=False), None, False),
        ("poll", _bare(t.Poll), None, False),
        ("pre checkout query", _bare(t.PreCheckoutQuery, from_user=someone), None, False),
        ("shipping query", _bare(t.ShippingQuery, from_user=someone), None, False),
        ("purchased paid media", _bare(t.PurchasedPaidMedia, from_user=someone), None, False),
        ("business connection", _bare(t.BusinessConnection, user=someone), None, False),
        ("managed bot", _bare(t.ManagedBotUpdated, user=someone), None, False),
        ("chat member", _bare(t.ChatMemberUpdated, from_user=someone, chat=group), group, False),
        ("reaction", _bare(t.MessageReactionUpdated, user=someone, chat=private), private, False),
        ("boost", _bare(t.ChatBoostUpdated, chat=channel), channel, False),
    ]


@pytest.mark.parametrize(
    "label,update,chat,outgoing", _chat_filter_cases(), ids=[c[0] for c in _chat_filter_cases()]
)
@pytest.mark.asyncio
async def test_the_chat_and_direction_filters_read_every_update_type(label, update, chat, outgoing):
    f = pyrogram.filters
    types = pyrogram.enums.ChatType
    kind = chat.type if chat else None

    assert bool(await f.incoming(None, update)) is (not outgoing)
    assert bool(await f.outgoing(None, update)) is outgoing
    assert bool(await f.private(None, update)) is (kind in {types.PRIVATE, types.BOT})
    assert bool(await f.direct(None, update)) is (kind == types.PRIVATE)
    assert bool(await f.group(None, update)) is (kind in {types.GROUP, types.SUPERGROUP, types.FORUM})
    assert bool(await f.channel(None, update)) is (kind == types.CHANNEL)
    assert bool(await f.forum(None, update)) is bool(chat and chat.is_forum)
    assert bool(await f.admin(None, update)) is bool(chat and chat.is_admin)
    assert bool(await f.chat(-100)(None, update)) is bool(chat and chat.id == -100)
    assert bool(await f.chat([5, -200])(None, update)) is bool(chat and chat.id in (5, -200))


def _restartable_session(monkeypatch, connect=None, send=None):
    from pyrogram.session.session import Session

    from tests.test_session import DummyClient

    made = []

    class _Connection:
        def __init__(self, *args, **kwargs):
            made.append(self)

        async def connect(self):
            if connect is not None:
                await connect(len(made))

        async def close(self):
            pass

    async def _send(self, query, *args, **kwargs):
        if send is not None:
            return await send(query)

    class _Storage:
        conn = object()
        opened = 0

        async def api_id(self):
            return 1

        async def open(self):
            self.opened += 1

    monkeypatch.setattr(DummyClient, "connection_factory", _Connection)
    monkeypatch.setattr(Session, "send", _send)
    monkeypatch.setattr(Session, "recv_worker", lambda self: asyncio.sleep(3600))

    client = DummyClient()
    client.storage = _Storage()

    return Session(client, 1, b"\x00" * 256, False, crypto_executor=None), made, client.storage


@pytest.mark.parametrize("stop_during", ["storage", "handshake", "backoff"])
async def test_a_stop_during_a_restart_keeps_the_session_stopped(monkeypatch, stop_during):
    reached = asyncio.Event()
    release = asyncio.Event()

    async def connect(attempt):
        if attempt == 2 and stop_during == "handshake":
            reached.set()
            await release.wait()

        if attempt == 2 and stop_during == "backoff":
            reached.set()
            raise OSError("down")

    session, made, storage = _restartable_session(monkeypatch, connect)
    await session.start()

    if stop_during == "storage":
        async def open_storage():
            reached.set()
            await release.wait()

        storage.conn = None
        storage.open = open_storage

    restarting = asyncio.ensure_future(session.restart())

    await reached.wait()
    await session.stop()

    release.set()
    await asyncio.wait_for(restarting, 5)

    assert not session.is_started.is_set()
    assert len(made) == (1 if stop_during == "storage" else 2)
    assert session.ping_task.done()
    assert session.recv_task.done()


@pytest.mark.parametrize("in_flight", [False, True])
async def test_a_request_on_a_stopped_session_does_not_reconnect(monkeypatch, in_flight):
    from pyrogram import raw

    sending = asyncio.Event()
    stopped = asyncio.Event()

    async def send(query):
        if isinstance(query, raw.functions.help.GetConfig):
            sending.set()
            await stopped.wait()
            raise ConnectionResetError("Connection lost while awaiting a response")

    session, made, storage = _restartable_session(monkeypatch, send=send)
    await session.start()

    if in_flight:
        request = asyncio.ensure_future(session.invoke(raw.functions.help.GetConfig()))
        await sending.wait()

    await session.stop()
    stopped.set()
    storage.conn = None

    if not in_flight:
        request = asyncio.ensure_future(session.invoke(raw.functions.help.GetConfig()))

    with pytest.raises(ConnectionError, match="Session is stopped"):
        await asyncio.wait_for(request, 5)

    assert len(made) == 1
    assert storage.opened == 0
    assert not session.is_started.is_set()


async def test_a_media_session_handed_out_is_not_reaped_before_its_first_request():
    import time

    class _MediaSession:
        results = {}
        is_restarting = False

        def __init__(self):
            self.last_used = time.monotonic() - 10_000
            self.is_started = asyncio.Event()
            self.is_started.set()
            self.stopped = False

        async def stop(self):
            self.stopped = True

    class _Client:
        _get_media_session_pool = pyrogram.Client._get_media_session_pool
        reap_media_sessions = pyrogram.Client.reap_media_sessions
        MEDIA_SESSION_IDLE_TIMEOUT = 300

        def __init__(self):
            self.media_session_pools = {2: [_MediaSession()]}
            self._media_sessions_locks = {}
            self.media_sessions = {}
            self.sessions = {}
            self._session_locks = {}
            self.session = None

    client = _Client()
    session = client.media_session_pools[2][0]

    assert await client._get_media_session_pool(2, 1) == [session]
    assert await client.reap_media_sessions() == 0
    assert not session.stopped
_EPHEMERAL_SHORTCUTS = ["reply", "answer", "reply_rich", "answer_rich"] + [
    f"{prefix}_{kind}"
    for kind in (
        "animation", "audio", "contact", "document", "location", "live_photo", "photo",
        "sticker", "venue", "video", "video_note", "voice", "cached_media",
    )
    for prefix in ("reply", "answer")
]


def _shortcut_message(ephemeral, outgoing=False):
    from unittest.mock import AsyncMock

    from pyrogram import enums, types

    return types.Message(
        id=11,
        chat=types.Chat(id=-100, type=enums.ChatType.SUPERGROUP),
        from_user=types.User(id=5),
        receiver_user=types.User(id=7) if ephemeral else None,
        ephemeral_message_id=11 if ephemeral else None,
        outgoing=outgoing,
        client=AsyncMock(),
    )


async def _call_shortcut(message, name):
    import inspect

    method = getattr(message, name)
    required = [
        p.name for p in inspect.signature(method).parameters.values()
        if p.default is inspect.Parameter.empty and p.kind is p.POSITIONAL_OR_KEYWORD
    ]

    await method(**{p: 1 if p in ("latitude", "longitude") else "x" for p in required})

    return next(
        c.kwargs for c in message._client.method_calls
        if c[0].startswith("send_")
    )


@pytest.mark.parametrize("name", _EPHEMERAL_SHORTCUTS)
@pytest.mark.parametrize("outgoing, receiver", [(False, 5), (True, 7)])
async def test_a_reply_to_an_ephemeral_message_stays_ephemeral(name, outgoing, receiver):
    kwargs = await _call_shortcut(_shortcut_message(True, outgoing), name)

    assert kwargs["ephemeral_message_parameters"].receiver_user_id == receiver

    if name.startswith("reply") and outgoing:
        assert kwargs["reply_parameters"] is None
    elif name.startswith("reply"):
        assert kwargs["reply_parameters"].ephemeral_message_id == 11
        assert kwargs["reply_parameters"].message_id is None


@pytest.mark.parametrize("name", _EPHEMERAL_SHORTCUTS)
async def test_a_reply_to_an_ordinary_message_is_not_ephemeral(name):
    kwargs = await _call_shortcut(_shortcut_message(False), name)

    assert kwargs["ephemeral_message_parameters"] is None

    if name.startswith("reply"):
        assert kwargs["reply_parameters"].message_id == 11
        assert kwargs["reply_parameters"].ephemeral_message_id is None


@pytest.mark.parametrize("outgoing, receiver", [(False, 5), (True, 7)])
async def test_an_ephemeral_reply_to_an_ephemeral_message_goes_to_the_other_side(outgoing, receiver):
    message = _shortcut_message(True, outgoing)

    await message.reply_ephemeral_text("only you")

    kwargs = message._client.send_ephemeral_message.await_args.kwargs

    assert kwargs["receiver_id"] == receiver

    if outgoing:
        assert kwargs["reply_parameters"] is None
    else:
        assert kwargs["reply_parameters"].ephemeral_message_id == 11
        assert kwargs["reply_parameters"].message_id is None


async def test_an_ephemeral_message_keeps_a_receiver_missing_from_the_users():
    from unittest.mock import MagicMock

    from pyrogram import raw, types

    message = await types.Message._parse(
        MagicMock(),
        raw.types.EphemeralMessage(
            id=3,
            from_id=raw.types.PeerUser(user_id=5),
            peer_id=raw.types.PeerChannel(channel_id=100),
            receiver_id=7,
            date=0,
            message="hi",
            out=True,
        ),
        {5: raw.types.User(id=5, bot=True, first_name="bot", usernames=[], restriction_reason=[])},
        {100: raw.types.Channel(
            id=100, title="g", photo=raw.types.ChatPhotoEmpty(), date=0, megagroup=True,
            usernames=[], restriction_reason=[]
        )},
    )

    assert message.receiver_user.id == 7
    assert message._ephemeral_target() == 7
    assert message._reply_receiver_id() == 7
_REFUSED_EPHEMERAL_SHORTCUTS = [
    f"{prefix}_{kind}"
    for kind in (
        "poll", "dice", "game", "invoice", "paid_media", "checklist", "media_group",
        "inline_bot_result",
    )
    for prefix in ("reply", "answer")
]


@pytest.mark.parametrize("name", _REFUSED_EPHEMERAL_SHORTCUTS)
async def test_a_shortcut_that_cannot_be_ephemeral_refuses_an_ephemeral_message(name):
    message = _shortcut_message(True)

    with pytest.raises(ValueError, match="cannot be sent as an ephemeral message"):
        await _call_shortcut(message, name)

    assert not message._client.method_calls


@pytest.mark.parametrize("name", _REFUSED_EPHEMERAL_SHORTCUTS)
async def test_a_shortcut_that_cannot_be_ephemeral_still_answers_an_ordinary_message(name):
    await _call_shortcut(_shortcut_message(False), name)


async def test_cached_media_can_be_sent_as_an_ephemeral_message():
    from unittest.mock import AsyncMock, Mock

    from pyrogram import raw, types
    from pyrogram.file_id import FileId, FileType

    client = AsyncMock()
    client.rnd_id = Mock(return_value=1)
    client.parser.parse = AsyncMock(return_value={"message": "cap", "entities": None})
    client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerUser(user_id=7, access_hash=0))
    client.invoke.return_value = Mock(
        updates=[raw.types.UpdateNewEphemeralMessage(message=raw.types.EphemeralMessage(
            id=3, from_id=raw.types.PeerUser(user_id=5), receiver_id=7, date=0,
            message="cap", out=True,
        ))],
        users=[raw.types.User(id=5, first_name="b", usernames=[], restriction_reason=[])],
        chats=[],
    )
    file_id = FileId(
        file_type=FileType.DOCUMENT, dc_id=2, media_id=11, access_hash=12, file_reference=b"r"
    ).encode()

    sent = await pyrogram.Client.send_cached_media(
        client, 1, file_id, caption="cap",
        ephemeral_message_parameters=types.EphemeralMessageParameters(receiver_user_id=7),
    )

    request = client.invoke.await_args.args[0]

    assert isinstance(request, raw.functions.ephemeral.SendMessage)
    assert request.media.id.id == 11
    assert request.message == "cap"
    assert sent.ephemeral_message_id == 3


def _ephemeral_media_cases():
    from pyrogram import raw

    photo = raw.types.Photo(
        id=1, access_hash=2, file_reference=b"r", date=0, dc_id=2,
        sizes=[raw.types.PhotoSize(type="x", w=10, h=10, size=5)],
    )

    def document(*attributes, mime="application/octet-stream"):
        return raw.types.MessageMediaDocument(document=raw.types.Document(
            id=3, access_hash=4, file_reference=b"r", date=0, mime_type=mime, size=9, dc_id=2,
            attributes=[raw.types.DocumentAttributeFilename(file_name="f"), *attributes],
        ))

    return {
        "photo": raw.types.MessageMediaPhoto(photo=photo),
        "document": document(),
        "video": document(raw.types.DocumentAttributeVideo(duration=1, w=2, h=3), mime="video/mp4"),
        "voice": document(raw.types.DocumentAttributeAudio(duration=1, voice=True), mime="audio/ogg"),
        "location": raw.types.MessageMediaGeo(geo=raw.types.GeoPoint(long=1.0, lat=2.0, access_hash=0)),
        "contact": raw.types.MessageMediaContact(
            phone_number="1", first_name="a", last_name="", vcard="", user_id=0
        ),
        "dice": raw.types.MessageMediaDice(value=3, emoticon="🎲"),
    }


@pytest.mark.parametrize("kind", list(_ephemeral_media_cases()))
async def test_an_ephemeral_message_reads_its_media_like_an_ordinary_one(kind):
    from unittest.mock import MagicMock

    from pyrogram import raw, types

    media = _ephemeral_media_cases()[kind]
    users = {
        5: raw.types.User(id=5, first_name="b", usernames=[], restriction_reason=[]),
        7: raw.types.User(id=7, first_name="u", usernames=[], restriction_reason=[]),
    }

    ephemeral = await types.Message._parse(MagicMock(), raw.types.EphemeralMessage(
        id=3, from_id=raw.types.PeerUser(user_id=5), receiver_id=7, date=0,
        message="cap", out=True, media=media,
    ), dict(users), {})
    ordinary = await types.Message._parse(MagicMock(), raw.types.Message(
        id=3, from_id=raw.types.PeerUser(user_id=5), peer_id=raw.types.PeerUser(user_id=7),
        date=0, message="cap", out=True, media=media, entities=[], restriction_reason=[],
    ), dict(users), {})

    assert ephemeral.media is ordinary.media is not None
    assert getattr(ephemeral, kind) is not None
    assert repr(getattr(ephemeral, kind)) == repr(getattr(ordinary, kind))

    if kind == "dice":
        assert ephemeral.text == ordinary.text
    else:
        assert ephemeral.caption == "cap" and ephemeral.text is None


async def test_an_ephemeral_message_without_media_keeps_its_text():
    from unittest.mock import MagicMock

    from pyrogram import raw, types

    message = await types.Message._parse(MagicMock(), raw.types.EphemeralMessage(
        id=3, from_id=raw.types.PeerUser(user_id=5), receiver_id=7, date=0, message="hi", out=True,
    ), {5: raw.types.User(id=5, first_name="b", usernames=[], restriction_reason=[])}, {})

    assert message.text == "hi"
    assert message.caption is None and message.media is None


class _GapClient:
    def __init__(self, states, replies):
        from pyrogram.methods.advanced.recover_gaps import RecoverGaps

        self.recover_gaps = RecoverGaps.recover_gaps.__get__(self)
        self._save_update_state = pyrogram.Client._save_update_state.__get__(self)
        self._state_marks = {}
        self.skip_updates = False
        self.sent = []
        self.written = []
        self.enqueued = []
        self.replies = list(replies)

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                if value is object:
                    return list(states)
                outer.written.append(value)

        class _Dispatcher:
            async def enqueue_update(self, update, users, chats):
                outer.enqueued.append(update)
                return True

        self.storage = _Storage()
        self.dispatcher = _Dispatcher()

    async def resolve_peer(self, peer_id):
        from pyrogram import raw

        return raw.types.InputChannel(channel_id=1, access_hash=0)

    async def invoke(self, query, **kwargs):
        self.sent.append(query)

        return self.replies.pop(0)


def _channel_message(message_id):
    from pyrogram import raw

    return raw.types.Message(
        id=message_id, peer_id=raw.types.PeerChannel(channel_id=1), date=0, message="m",
        entities=[], restriction_reason=[],
    )


async def test_a_partial_channel_difference_is_fetched_to_the_end():
    from pyrogram import raw

    client = _GapClient([(-1000000000001, 100, None, 7, 1)], [
        raw.types.updates.ChannelDifference(
            final=False, pts=200, new_messages=[_channel_message(1)], other_updates=[], chats=[], users=[]
        ),
        raw.types.updates.ChannelDifference(
            final=True, pts=300, new_messages=[_channel_message(2)], other_updates=[], chats=[], users=[]
        ),
    ])

    assert await client.recover_gaps() == (2, 0)
    assert [query.pts for query in client.sent] == [100, 200]
    assert client.written[-1][:2] == (-1000000000001, 300)


async def test_a_partial_channel_difference_that_does_not_move_stops():
    from pyrogram import raw

    client = _GapClient([(-1000000000001, 100, None, 7, 1)], [
        raw.types.updates.ChannelDifference(
            final=False, pts=100, new_messages=[], other_updates=[], chats=[], users=[]
        ),
    ])

    await asyncio.wait_for(client.recover_gaps(), timeout=5)

    assert len(client.sent) == 1


def _state(pts, qts):
    from pyrogram import raw

    return raw.types.updates.State(pts=pts, qts=qts, date=9, seq=3, unread_count=0)


async def test_the_common_difference_asks_from_the_stored_qts_and_keeps_the_new_one():
    from pyrogram import raw

    client = _GapClient([(0, 10, 50, 7, 1)], [
        raw.types.updates.Difference(
            new_messages=[], new_encrypted_messages=[], other_updates=[raw.types.UpdateBotStopped(
                user_id=1, date=0, stopped=True, qts=60
            )], chats=[], users=[], state=_state(10, 60)
        ),
    ])

    assert await client.recover_gaps() == (0, 1)
    assert client.sent[0].qts == 50
    assert client.written[-1] == (0, 10, 60, 9, 3)


async def test_an_empty_common_difference_keeps_the_stored_qts():
    from pyrogram import raw

    client = _GapClient([(0, 10, 50, 7, 1)], [raw.types.updates.DifferenceEmpty(date=8, seq=2)])

    await client.recover_gaps()

    assert all(state[2] == 50 for state in client.written)


async def test_a_difference_slice_that_only_moves_qts_is_followed():
    from pyrogram import raw

    client = _GapClient([(0, 10, 50, 7, 1)], [
        raw.types.updates.DifferenceSlice(
            new_messages=[], new_encrypted_messages=[], other_updates=[], chats=[], users=[],
            intermediate_state=_state(10, 55),
        ),
        raw.types.updates.Difference(
            new_messages=[], new_encrypted_messages=[], other_updates=[], chats=[], users=[],
            state=_state(10, 60),
        ),
    ])

    await client.recover_gaps()

    assert [query.qts for query in client.sent] == [50, 55]
    assert client.written[-1][2] == 60


async def test_a_difference_slice_that_does_not_move_is_read_once():
    from pyrogram import raw

    client = _GapClient([(0, 10, 50, 7, 1)], [
        raw.types.updates.DifferenceSlice(
            new_messages=[_channel_message(1)], new_encrypted_messages=[], other_updates=[], chats=[],
            users=[], intermediate_state=_state(10, 50),
        ),
    ])

    assert await asyncio.wait_for(client.recover_gaps(), timeout=5) == (1, 0)
    assert len(client.sent) == 1


async def test_a_common_state_known_only_by_qts_is_recovered_from_the_current_pts():
    from pyrogram import raw

    client = _GapClient([(0, None, 50, None, None)], [
        _state(40, 70),
        raw.types.updates.DifferenceEmpty(date=8, seq=2),
    ])

    await client.recover_gaps()

    assert isinstance(client.sent[0], raw.functions.updates.GetState)
    assert (client.sent[1].pts, client.sent[1].qts) == (40, 50)


async def test_a_channel_state_without_pts_is_still_skipped():
    client = _GapClient([(-1000000000001, None, 50, None, None)], [])

    await client.recover_gaps()

    assert client.sent == []


class _QtsClient:
    handle_updates = pyrogram.Client.handle_updates
    _save_update_state = pyrogram.Client._save_update_state

    def __init__(self):
        self.states = []
        self._state_marks = {}

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                outer.states.append(value)

        class _Dispatcher:
            async def enqueue_update(self, update, users, chats):
                return True

        self.storage = _Storage()
        self.dispatcher = _Dispatcher()

    async def fetch_peers(self, peers):
        return False


async def test_the_highest_qts_of_a_batch_is_stored_in_the_common_state():
    from pyrogram import raw

    client = _QtsClient()

    await client.handle_updates(raw.types.Updates(
        updates=[
            raw.types.UpdateBotStopped(user_id=1, date=0, stopped=True, qts=41),
            raw.types.UpdateChannelParticipant(
                channel_id=5, date=0, actor_id=1, user_id=2, qts=43
            ),
            raw.types.UpdateBotStopped(user_id=1, date=0, stopped=False, qts=42),
            raw.types.UpdateNewMessage(message=raw.types.MessageEmpty(id=1), pts=9, pts_count=1),
        ],
        users=[], chats=[], date=1700000000, seq=4,
    ))

    assert client.states == [(0, 9, 43, 1700000000, 4)]


async def test_a_short_update_with_qts_is_stored_in_the_common_state():
    from pyrogram import raw

    client = _QtsClient()

    await client.handle_updates(raw.types.UpdateShort(
        update=raw.types.UpdateBotStopped(user_id=1, date=0, stopped=True, qts=77), date=1700000000
    ))

    assert client.states == [(0, None, 77, 1700000000, None)]


def _pts_batch(pts):
    from pyrogram import raw

    return raw.types.Updates(
        updates=[raw.types.UpdateNewMessage(message=raw.types.MessageEmpty(id=pts), pts=pts, pts_count=1)],
        users=[], chats=[], date=1700000000 + pts, seq=0,
    )


async def test_a_batch_that_arrives_late_does_not_move_the_state_back():
    client = _QtsClient()

    await client.handle_updates(_pts_batch(12))
    await client.handle_updates(_pts_batch(11))
    await client.handle_updates(_pts_batch(13))

    assert [state[1] for state in client.states] == [12, 13]


async def test_a_short_message_that_arrives_late_does_not_move_the_state_back():
    from pyrogram import raw

    client = _QtsClient()

    async def invoke(query, **kwargs):
        return raw.types.updates.Difference(
            new_messages=[], new_encrypted_messages=[], other_updates=[], chats=[], users=[],
            state=_state(query.pts + 1, 0),
        )

    client.invoke = invoke

    for pts in (5946, 5945):
        await client.handle_updates(raw.types.UpdateShortMessage(
            id=pts, user_id=1, message="m", pts=pts, pts_count=1, date=0
        ))

    assert [state[1] for state in client.states] == [5946]


async def test_a_qts_that_arrives_late_does_not_move_the_state_back():
    from pyrogram import raw

    client = _QtsClient()

    for qts in (41, 40):
        await client.handle_updates(raw.types.UpdateShort(
            update=raw.types.UpdateBotStopped(user_id=1, date=0, stopped=True, qts=qts), date=0
        ))

    assert [state[2] for state in client.states] == [41]


async def test_a_late_qts_still_stores_a_newer_pts_of_the_same_batch():
    from pyrogram import raw

    client = _QtsClient()

    await client.handle_updates(raw.types.Updates(
        updates=[raw.types.UpdateBotStopped(user_id=1, date=0, stopped=True, qts=50)],
        users=[], chats=[], date=0, seq=0,
    ))
    await client.handle_updates(raw.types.Updates(
        updates=[
            raw.types.UpdateBotStopped(user_id=1, date=0, stopped=True, qts=49),
            raw.types.UpdateNewMessage(message=raw.types.MessageEmpty(id=1), pts=7, pts_count=1),
        ],
        users=[], chats=[], date=0, seq=0,
    ))

    assert client.states[-1][:3] == (0, 7, None)


async def test_recovery_does_not_move_back_a_state_seen_since():
    from pyrogram import raw

    client = _GapClient([(0, 90, 5, 7, 1)], [raw.types.updates.DifferenceEmpty(date=8, seq=2)])
    client._state_marks[0] = (100, 5)

    await client.recover_gaps()

    assert all(state[1] is None or state[1] >= 100 for state in client.written)


async def test_a_dropped_state_starts_over():
    from pyrogram.errors import ChannelPrivate

    client = _GapClient([(-1000000000001, 100, None, 7, 1)], [])
    client._state_marks[-1000000000001] = (100, None)

    async def invoke(query, **kwargs):
        raise ChannelPrivate()

    client.invoke = invoke

    await client.recover_gaps()
    await client._save_update_state((-1000000000001, 3, None, 8, 1))

    assert client.written == [-1000000000001, (-1000000000001, 3, None, 8, 1)]


async def test_recover_gaps_called_by_hand_recovers_with_skip_updates_on():
    from pyrogram import raw

    client = _GapClient([(0, 10, 50, 7, 1)], [
        raw.types.updates.Difference(
            new_messages=[_channel_message(1)], new_encrypted_messages=[], other_updates=[], chats=[],
            users=[], state=_state(11, 50),
        ),
    ])
    client.skip_updates = True

    assert await client.recover_gaps() == (1, 0)
    assert len(client.sent) == 1


class _SkipWatchdogClient:
    UPDATES_WATCHDOG_INTERVAL = 0.01
    updates_watchdog = pyrogram.Client.updates_watchdog

    def __init__(self, skip_updates):
        import time

        self.skip_updates = skip_updates
        self.updates_watchdog_event = asyncio.Event()
        self._last_update_monotonic = time.monotonic() - 86400
        self.polls = 0
        self.recoveries = 0

    async def invoke(self, query, **kwargs):
        self.polls += 1

    async def recover_gaps(self):
        self.recoveries += 1
        return (0, 0)


@pytest.mark.parametrize("skip_updates", [True, False])
async def test_the_watchdog_recovers_on_its_own_only_when_updates_are_not_skipped(skip_updates):
    client = _SkipWatchdogClient(skip_updates)

    task = asyncio.ensure_future(client.updates_watchdog())
    await asyncio.sleep(0.1)
    client.updates_watchdog_event.set()
    await asyncio.wait_for(task, timeout=5)

    assert client.polls > 0
    assert (client.recoveries == 0) is skip_updates


@pytest.mark.parametrize("skip_updates", [True, False])
async def test_start_recovers_on_its_own_only_when_updates_are_not_skipped(skip_updates):
    client = _DispatcherClient()
    client.skip_updates = skip_updates
    recoveries = []

    async def recover_gaps():
        recoveries.append(1)
        return (0, 0)

    client.recover_gaps = recover_gaps
    dispatcher = Dispatcher(client)

    await dispatcher.start()
    await dispatcher.stop()

    assert bool(recoveries) is not skip_updates
_PLUGIN_SOURCE = (
    "import logging, logging.handlers\n"
    "from pyrogram import Client, filters\n"
    "\n"
    "log = logging.getLogger('plugin_under_test')\n"
    "log.addHandler(logging.NullHandler())\n"
    "\n"
    "class Mongoish:\n"
    "    def __getattr__(self, name):\n"
    "        return Mongoish()\n"
    "\n"
    "class Lazy:\n"
    "    @property\n"
    "    def handlers(self):\n"
    "        raise RuntimeError('settings are not configured')\n"
    "\n"
    "db = Mongoish()\n"
    "settings = Lazy()\n"
    "pairs_of_something_else = type('P', (), {'handlers': [('a', 1)]})()\n"
    "\n"
    "@Client.on_message(filters.command('ping'))\n"
    "async def ping(client, message):\n"
    "    pass\n"
    "\n"
    "@Client.on_message(filters.command('cfg'), group='2')\n"
    "async def from_config(client, message):\n"
    "    pass\n"
)


def _plugin_client(tmp_path, monkeypatch, name, plugins, cls=None):
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "bot.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    return (cls or pyrogram.Client)(name, in_memory=True, plugins=dict(plugins, root=name))


@pytest.mark.parametrize("package, include", [
    ("badgroup_scan", None),
    ("badgroup_module", ["bot"]),
    ("badgroup_named", ["bot ping from_config"]),
])
def test_a_plugin_handler_with_a_bad_group_is_reported(tmp_path, monkeypatch, caplog, package, include):
    plugins = {"include": include} if include else {}
    client = _plugin_client(tmp_path, monkeypatch, package, plugins)
    added = []
    client.add_handler = lambda handler, group=0: added.append((handler.callback.__name__, group))

    with caplog.at_level("WARNING", logger="pyrogram.client"):
        client.load_plugins()

    assert added == [("ping", 0)]
    assert any("from_config" in r.getMessage() and "'2'" in r.getMessage() for r in caplog.records)


def test_objects_that_only_look_like_plugin_handlers_are_passed_over(tmp_path, monkeypatch, caplog):
    client = _plugin_client(tmp_path, monkeypatch, "lookalikes", {})
    added = []
    client.add_handler = lambda handler, group=0: added.append(handler.callback.__name__)

    with caplog.at_level("WARNING", logger="pyrogram.client"):
        client.load_plugins()

    assert added == ["ping"]
    assert not any(
        word in r.getMessage() for r in caplog.records for word in ("log", "db", "settings", "pairs_of")
    )


def test_an_error_while_registering_a_plugin_handler_is_raised(tmp_path, monkeypatch):
    class Strict(pyrogram.Client):
        def add_handler(self, handler, group=0):
            raise ValueError("refused")

    for index, include in enumerate((None, ["bot ping"])):
        plugins = {"include": include} if include else {}
        client = _plugin_client(tmp_path, monkeypatch, f"strict{index}", plugins, Strict)

        with pytest.raises(ValueError, match="refused"):
            client.load_plugins()


def test_a_named_plugin_object_that_is_not_a_handler_is_still_reported(tmp_path, monkeypatch, caplog):
    client = _plugin_client(tmp_path, monkeypatch, "named", {"include": ["bot ping db missing"]})
    client.add_handler = lambda handler, group=0: None

    with caplog.at_level("WARNING", logger="pyrogram.client"):
        client.load_plugins()

    warned = " ".join(r.getMessage() for r in caplog.records)
    assert '"db"' in warned and '"missing"' in warned and '"ping"' not in warned


def test_excluding_a_plugin_handler_removes_it(tmp_path, monkeypatch):
    client = _plugin_client(tmp_path, monkeypatch, "excluded", {"exclude": ["bot ping"]})
    added, removed = [], []
    client.add_handler = lambda handler, group=0: added.append((handler, group))
    client.remove_handler = lambda handler, group=0: removed.append((handler, group))

    client.load_plugins()

    assert [h.callback.__name__ for h, _ in added] == ["ping"]
    assert removed == added


def test_loading_plugins_again_does_not_register_handlers_twice(tmp_path, monkeypatch):
    client = _plugin_client(tmp_path, monkeypatch, "reloaded", {})

    client.load_plugins()
    client.load_plugins()

    assert [h.callback.__name__ for h in client.dispatcher.groups[0]] == ["ping"], (
        "a restart that keeps handlers must not make plugin handlers run twice"
    )


async def test_adding_a_handler_twice_under_a_running_loop_keeps_one():
    client = _DispatcherClient()
    dispatcher = Dispatcher(client)
    handler = MessageHandler(lambda c, m: None)

    dispatcher.add_handler(handler, 0)
    dispatcher.add_handler(handler, 0)
    await asyncio.sleep(0.05)

    assert dispatcher.groups[0] == [handler]


@pytest.mark.parametrize("name", [n for n in _EPHEMERAL_SHORTCUTS if n.startswith("reply")])
@pytest.mark.parametrize("is_bot, deadline", [(True, 1700000013), (False, None)])
async def test_a_bot_reply_to_an_ephemeral_message_carries_the_quote_deadline(name, is_bot, deadline):
    import datetime

    message = _shortcut_message(True)
    message.date = datetime.datetime.fromtimestamp(1700000000)
    message._client.me = pyrogram.types.User(id=1, is_bot=is_bot)

    kwargs = await _call_shortcut(message, name)

    assert kwargs["ephemeral_message_parameters"].receiver_user_id == 5
    assert kwargs["reply_parameters"].ephemeral_message_id == 11
    assert kwargs["reply_parameters"]._ephemeral_quote_deadline == deadline


@pytest.mark.parametrize("now, thread, expected", [
    (1700000012, None, ("ephemeral", 11)),
    (1700000013, None, None),
    (1700000013, 3, ("thread", 3)),
    (1800000000, None, None),
])
async def test_an_ephemeral_quote_is_dropped_once_its_deadline_passes(now, thread, expected):
    from types import SimpleNamespace

    from pyrogram import raw, types, utils

    parameters = types.ReplyParameters(ephemeral_message_id=11)
    parameters._ephemeral_quote_deadline = 1700000013

    reply_to = await utils.get_reply_to(SimpleNamespace(server_time=now), parameters, thread)

    if expected is None:
        assert reply_to is None
    elif expected[0] == "ephemeral":
        assert isinstance(reply_to, raw.types.InputReplyToEphemeralMessage) and reply_to.id == 11
    else:
        assert isinstance(reply_to, raw.types.InputReplyToMessage) and reply_to.reply_to_msg_id == 3


async def test_an_ephemeral_quote_given_by_hand_is_always_sent():
    from types import SimpleNamespace

    from pyrogram import raw, types, utils

    reply_to = await utils.get_reply_to(
        SimpleNamespace(server_time=1800000000), types.ReplyParameters(ephemeral_message_id=11)
    )

    assert isinstance(reply_to, raw.types.InputReplyToEphemeralMessage)


def test_the_quote_deadline_is_not_part_of_the_reply_parameters_seen_by_users():
    from pyrogram import types

    parameters = types.ReplyParameters(ephemeral_message_id=11)
    parameters._ephemeral_quote_deadline = 5

    assert parameters == types.ReplyParameters(ephemeral_message_id=11)
    assert "deadline" not in repr(parameters) and "deadline" not in str(parameters)


def _ephemeral_client(cached=()):
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock()
    client.message_cache = pyrogram.client.Cache(10)
    client.topic_cache = pyrogram.client.Cache(10)
    client.fetch_replies = True
    client.fetch_topics = True
    client.me = pyrogram.types.User(id=7, is_bot=False)
    client.get_messages = AsyncMock(return_value="fetched")
    client.get_forum_topics_by_id = AsyncMock(return_value=None)

    for key, value in cached:
        client.message_cache[key] = value

    return client


def _raw_ephemeral(reply_to=None, sender=5, receiver=7, message_id=900, top_msg_id=None):
    from pyrogram import raw

    return raw.types.EphemeralMessage(
        id=message_id, from_id=raw.types.PeerUser(user_id=sender), receiver_id=receiver, date=0,
        message="hi", peer_id=raw.types.PeerChannel(channel_id=100), reply_to=reply_to,
        top_msg_id=top_msg_id,
    )


def _ephemeral_parties(forum=False):
    from pyrogram import raw

    users = {
        5: raw.types.User(id=5, first_name="a", usernames=[], restriction_reason=[]),
        7: raw.types.User(id=7, first_name="b", usernames=[], restriction_reason=[]),
    }
    chats = {100: raw.types.Channel(
        id=100, title="g", photo=raw.types.ChatPhotoEmpty(), date=0, megagroup=True, forum=forum,
        access_hash=1, usernames=[], restriction_reason=[],
    )}

    return users, chats


async def test_an_ephemeral_reply_to_an_ordinary_message_fetches_that_message():
    from pyrogram import raw, types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    message = await types.Message._parse(
        client, _raw_ephemeral(raw.types.MessageReplyHeader(reply_to_msg_id=1099)), users, chats
    )

    assert message.reply_to_message_id == 1099
    assert message.reply_to_message == "fetched"
    assert client.get_messages.await_args.kwargs == {"replies": 0, "chat_id": -1000000000100, "message_ids": 1099}


async def test_an_ephemeral_reply_to_an_ephemeral_message_finds_it_when_it_is_known():
    from pyrogram import raw, types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    sent = await types.Message._parse(client, _raw_ephemeral(sender=7, receiver=5, message_id=110), users, chats)
    reply = await types.Message._parse(client, _raw_ephemeral(
        raw.types.MessageReplyHeader(reply_to_msg_id=110, reply_to_ephemeral=True)
    ), users, chats)

    assert reply.reply_to_message is sent
    assert reply.reply_to_message_id is None
    client.get_messages.assert_not_awaited()


async def test_a_reply_chain_does_not_keep_every_message_alive():
    import gc
    import weakref
    from pyrogram import raw, types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()
    refs = []

    for i in range(1, 41):
        message = await types.Message._parse(client, raw.types.Message(
            id=i, peer_id=raw.types.PeerChannel(channel_id=100), from_id=raw.types.PeerUser(user_id=5),
            date=0, message="x", entities=[], restriction_reason=[],
            reply_to=raw.types.MessageReplyHeader(reply_to_msg_id=i - 1) if i > 1 else None,
        ), users, chats)
        chat_id = message.chat.id
        refs.append(weakref.ref(message))
        del message

    gc.collect()
    newest = client.message_cache[(chat_id, 40)]

    assert newest.reply_to_message.id == 39
    assert newest.reply_to_message.reply_to_message is None
    assert newest.reply_to_message._client is client
    assert client.message_cache[(chat_id, 39)].reply_to_message.id == 38, (
        "cutting the chain on the link must not touch the cached message itself"
    )
    assert sum(r() is not None for r in refs) == client.message_cache.capacity, (
        "evicted messages must be collectable, not pinned by the reply chain"
    )
    client.get_messages.assert_not_awaited()


@pytest.mark.parametrize("sender, receiver", [(5, 7), (7, 9)])
async def test_an_ephemeral_reply_is_not_matched_to_a_message_between_other_users(sender, receiver):
    from pyrogram import raw, types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    await types.Message._parse(client, _raw_ephemeral(sender=sender, receiver=receiver, message_id=110), users, chats)
    reply = await types.Message._parse(client, _raw_ephemeral(
        raw.types.MessageReplyHeader(reply_to_msg_id=110, reply_to_ephemeral=True)
    ), users, chats)

    assert reply.reply_to_message is None
    client.get_messages.assert_not_awaited()


async def test_an_ephemeral_message_is_cached_apart_from_ordinary_messages():
    from pyrogram import types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    message = await types.Message._parse(client, _raw_ephemeral(message_id=42), users, chats)

    assert client.message_cache[(-1000000000100, "ephemeral", 42)] is message
    assert client.message_cache[(-1000000000100, 42)] is None


async def test_an_ephemeral_message_in_a_forum_reads_its_topic():
    from pyrogram import types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties(forum=True)
    topic = types.ForumTopic(id=33, title="t")
    client.topic_cache[(-1000000000100, 33)] = topic

    message = await types.Message._parse(client, _raw_ephemeral(top_msg_id=33), users, chats)

    assert message.message_thread_id == 33
    assert message.topic is topic
    assert message.is_topic_message is True


async def test_an_ephemeral_message_in_the_general_topic_is_not_a_topic_message():
    from pyrogram import types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties(forum=True)
    general = types.ForumTopic(id=1, title="General")
    client.topic_cache[(-1000000000100, 1)] = general

    message = await types.Message._parse(client, _raw_ephemeral(), users, chats)

    assert message.topic is general
    assert not message.is_topic_message


async def test_an_ephemeral_message_outside_a_forum_is_not_a_topic_message():
    from pyrogram import types

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    message = await types.Message._parse(client, _raw_ephemeral(top_msg_id=33), users, chats)

    assert message.topic is None and not message.is_topic_message


async def test_a_deleted_ephemeral_message_is_reported_as_ephemeral():
    from pyrogram import raw, types, utils

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()
    sent = await types.Message._parse(client, _raw_ephemeral(sender=7, receiver=5, message_id=86), users, chats)

    deleted = utils.parse_deleted_messages(client, raw.types.UpdateDeleteEphemeralMessages(
        peer=raw.types.PeerChannel(channel_id=100), ids=[86, 87]
    ), users, chats)

    assert [(m.id, m.ephemeral_message_id, m.is_ephemeral) for m in deleted] == [(86, 86, True), (87, 87, True)]
    assert deleted[0].chat.id == -1000000000100
    assert (deleted[0].from_user.id, deleted[0].receiver_user.id) == (sent.from_user.id, sent.receiver_user.id)
    assert deleted[1].from_user is None and deleted[1].receiver_user is None
    assert client.message_cache[(-1000000000100, "ephemeral", 86)] is None


def test_a_deleted_ordinary_message_is_not_reported_as_ephemeral():
    from pyrogram import raw, utils

    client = _ephemeral_client()
    users, chats = _ephemeral_parties()

    deleted = utils.parse_deleted_messages(client, raw.types.UpdateDeleteChannelMessages(
        channel_id=100, messages=[86], pts=1, pts_count=1
    ), users, chats)

    assert [(m.id, m.is_ephemeral) for m in deleted] == [(86, False)]


def test_payment_form_photo_url_comes_from_the_web_document():
    form = raw.types.payments.PaymentFormStars(
        form_id=1,
        bot_id=2,
        title="t",
        description="d",
        photo=raw.types.WebDocumentNoProxy(
            url="https://example.org/p.jpg", size=1, mime_type="image/jpeg", attributes=[]
        ),
        invoice=raw.types.Invoice(currency="XTR", prices=[]),
        users=[],
    )

    parsed = types.PaymentForm._parse(None, form)

    assert parsed.photo_url == "https://example.org/p.jpg"


def _user_full(bot_info):
    return raw.types.users.UserFull(
        full_user=raw.types.UserFull(
            id=1,
            settings=raw.types.PeerSettings(),
            notify_settings=raw.types.PeerNotifySettings(),
            common_chats_count=0,
            bot_info=bot_info,
        ),
        chats=[],
        users=[],
    )


class _MenuClient(GetChatMenuButton):
    def __init__(self, bot_info):
        self.bot_info = bot_info

    async def invoke(self, query, *args, **kwargs):
        assert isinstance(query, raw.functions.users.GetFullUser)
        return _user_full(self.bot_info)


async def test_get_chat_menu_button_on_a_user_account_raises_a_clear_error():
    with pytest.raises(ValueError, match="not a bot"):
        await _MenuClient(None).get_chat_menu_button()


async def test_get_chat_menu_button_falls_back_to_default_when_unset():
    result = await _MenuClient(raw.types.BotInfo()).get_chat_menu_button()

    assert isinstance(result, types.MenuButtonDefault)


def test_sent_web_app_message_without_inline_keyboard_has_no_id():
    parsed = types.SentWebAppMessage._parse(raw.types.WebViewMessageSent())

    assert parsed.inline_message_id is None


async def test_story_privacy_survives_a_disallow_rule_after_the_public_rule():
    client = SimpleNamespace(me=None, fetch_stories=False)
    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )}
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[
            raw.types.PrivacyValueAllowAll(),
            raw.types.PrivacyValueDisallowUsers(users=[7]),
        ],
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), users, {})

    assert parsed.privacy is enums.StoriesPrivacyRules.PUBLIC
    assert [u.id for u in parsed.disallowed_users] == [7]


async def test_story_privacy_maps_an_allow_list_to_selected_users():
    client = SimpleNamespace(me=None, fetch_stories=False)
    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )}
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[raw.types.PrivacyValueAllowUsers(users=[7])],
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), users, {})

    assert parsed.privacy is enums.StoriesPrivacyRules.SELECTED_USERS
    assert [u.id for u in parsed.allowed_users] == [7]


async def test_story_privacy_keeps_close_friends_with_extra_users():
    client = SimpleNamespace(me=None, fetch_stories=False)
    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )}
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[
            raw.types.PrivacyValueAllowCloseFriends(),
            raw.types.PrivacyValueAllowUsers(users=[7]),
            raw.types.PrivacyValueDisallowAll(),
        ],
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), users, {})

    assert parsed.privacy is enums.StoriesPrivacyRules.CLOSE_FRIENDS
    assert [u.id for u in parsed.allowed_users] == [7]


async def test_story_privacy_reports_disallow_all_as_selected_users():
    client = SimpleNamespace(me=None, fetch_stories=False)
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[raw.types.PrivacyValueDisallowAll()],
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), {7: raw.types.User(id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1)}, {})

    assert parsed.privacy is enums.StoriesPrivacyRules.SELECTED_USERS
    assert parsed.allowed_users is None


async def test_story_privacy_reads_the_story_flags():
    client = SimpleNamespace(me=None, fetch_stories=False)
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[],
        contacts=True,
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), {7: raw.types.User(id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1)}, {})

    assert parsed.privacy is enums.StoriesPrivacyRules.CONTACTS


async def test_story_privacy_keeps_allowed_users_and_chats():
    client = SimpleNamespace(me=None, fetch_stories=False)
    users = {7: raw.types.User(
        id=7, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )}
    chats = {9: raw.types.Chat(
        id=9, title="G", photo=raw.types.ChatPhotoEmpty(), participants_count=1, date=0, version=1
    )}
    story = raw.types.StoryItem(
        id=1,
        date=0,
        expire_date=0,
        media=raw.types.MessageMediaUnsupported(),
        entities=[],
        media_areas=[],
        privacy=[
            raw.types.PrivacyValueAllowUsers(users=[7, 8]),
            raw.types.PrivacyValueAllowChatParticipants(chats=[9]),
            raw.types.PrivacyValueDisallowAll(),
        ],
    )

    parsed = await types.Story._parse(client, story, raw.types.PeerUser(user_id=7), users, chats)

    assert parsed.privacy is enums.StoriesPrivacyRules.SELECTED_USERS
    assert [u.id for u in parsed.allowed_users] == [7, -9]


async def test_parse_full_user_populates_bot_admin_rights():
    from pyrogram.types.user_and_chats.user import User

    full_user = raw.types.UserFull(
        id=1,
        settings=raw.types.PeerSettings(),
        notify_settings=raw.types.PeerNotifySettings(),
        common_chats_count=0,
        bot_group_admin_rights=raw.types.ChatAdminRights(change_info=True, ban_users=True),
        bot_broadcast_admin_rights=raw.types.ChatAdminRights(post_messages=True),
    )
    users = {1: raw.types.User(
        id=1, first_name="B", usernames=[], restriction_reason=[], access_hash=1
    )}

    class _Client:
        me = None

        async def get_messages(self, *args, **kwargs):
            return None

    parsed = await User._parse_full(_Client(), full_user, users, {})

    assert parsed.chat_admin_rights.can_change_info is True
    assert parsed.chat_admin_rights.can_restrict_members is True
    assert parsed.channel_admin_rights.can_post_messages is True


def _message(chat_id, user_id, outgoing):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
        id=100,
        outgoing=outgoing,
        scheduled=False,
    )


def test_identify_keeps_an_outgoing_message_in_saved_messages():
    identified = registry_module._identify(
        enums.ListenerTypes.MESSAGE, _message(chat_id=10, user_id=10, outgoing=True)
    )

    assert identified is not None
    assert identified[1] == 10 and identified[2] == 10


def test_identify_still_drops_an_outgoing_message_elsewhere():
    assert registry_module._identify(
        enums.ListenerTypes.MESSAGE, _message(chat_id=1, user_id=10, outgoing=True)
    ) is None


def test_restart_docstring_no_longer_promises_a_connection_error():
    assert "ConnectionError" not in pyrogram.Client.restart.__doc__


def test_invoice_photo_url():
    from pyrogram import raw, types

    photo = raw.types.WebDocument(url="https://example.com/p.jpg", access_hash=1, size=1, mime_type="image/jpeg", attributes=[])
    media = raw.types.MessageMediaInvoice(
        title="t", description="d", currency="USD", total_amount=100, start_param="", photo=photo
    )
    assert types.Invoice._parse(None, media).photo_url == "https://example.com/p.jpg"
    assert types.Invoice._parse(None, raw.types.Invoice(currency="XTR", prices=[])).photo_url is None


def _user(user_id):
    return raw.types.User(
        id=user_id, first_name="U", usernames=[], restriction_reason=[], access_hash=1
    )


async def test_get_users_refuses_a_peer_that_is_not_a_user():
    from pyrogram.methods.users.get_users import GetUsers

    class _Client(GetUsers):
        async def resolve_peer(self, peer_id):
            if peer_id == "channel":
                return raw.types.InputPeerChannel(channel_id=1, access_hash=1)

            return raw.types.InputPeerUser(user_id=2, access_hash=1)

        async def invoke(self, query, *args, **kwargs):
            return [_user(p.user_id) for p in query.id]

    client = _Client()

    with pytest.raises(ValueError, match="channel"):
        await client.get_users("channel")

    with pytest.raises(ValueError):
        await client.get_users(["someone", "channel"])

    assert (await client.get_users("someone")).id == 2


def test_accepted_gift_types_only_disallows_what_was_set_to_false():
    written = types.AcceptedGiftTypes(limited_gifts=False).write()

    assert written.disallow_limited_stargifts is True
    assert not any((
        written.disallow_unlimited_stargifts,
        written.disallow_unique_stargifts,
        written.disallow_stargifts_from_channels,
        written.disallow_premium_gifts,
    )), "a field left as None is not a refusal"


async def test_update_birthday_refuses_a_partial_date_and_removes_on_no_arguments():
    from pyrogram.methods.users.update_birthday import UpdateBirthday

    class _Client(UpdateBirthday):
        sent = None

        async def invoke(self, query, *args, **kwargs):
            self.sent = query
            return True

    client = _Client()

    with pytest.raises(ValueError):
        await client.update_birthday(year=2000)

    assert client.sent is None, "a partial date must not reach the server as a removal"

    assert await client.update_birthday() is True
    assert client.sent.birthday is None

    await client.update_birthday(day=1, month=2)
    assert (client.sent.birthday.day, client.sent.birthday.month) == (1, 2)


async def test_set_profile_photo_without_a_file_is_refused_before_the_request():
    from pyrogram.methods.users.set_profile_photo import SetProfilePhoto

    class _Client(SetProfilePhoto):
        async def save_file(self, *args, **kwargs):
            raise AssertionError("nothing to upload")

        async def invoke(self, query, *args, **kwargs):
            raise AssertionError("an empty request must not go out")

    with pytest.raises(ValueError):
        await _Client().set_profile_photo()


def _bot_channel_client(chat_photo):
    class _Client:
        me = SimpleNamespace(is_bot=True)
        queries = []

        async def resolve_peer(self, chat_id):
            return raw.types.InputPeerChannel(channel_id=1, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            self.queries.append(query)

            if isinstance(query, raw.functions.channels.GetFullChannel):
                return SimpleNamespace(full_chat=SimpleNamespace(chat_photo=chat_photo))

            raise AssertionError(f"{query.QUALNAME} is user-only")

    return _Client()


async def test_a_bot_reads_a_channels_photo_from_the_full_chat(monkeypatch):
    from pyrogram.methods.users.get_chat_photos import GetChatPhotos
    from pyrogram.methods.users.get_chat_photos_count import GetChatPhotosCount

    photo = raw.types.Photo(
        id=1, access_hash=1, file_reference=b"", date=0, sizes=[], dc_id=2
    )
    parsed = SimpleNamespace(file_id="id", file_unique_id="current")

    monkeypatch.setattr(
        types.Photo, "_parse", staticmethod(lambda _c, p: parsed if p is photo else None)
    )

    client = _bot_channel_client(photo)
    got = [p async for p in GetChatPhotos.get_chat_photos(client, 1)]
    assert got == [parsed]
    assert await GetChatPhotosCount.get_chat_photos_count(client, 1) == 1

    client = _bot_channel_client(raw.types.PhotoEmpty(id=0))
    assert [p async for p in GetChatPhotos.get_chat_photos(client, 1)] == []
    assert await GetChatPhotosCount.get_chat_photos_count(client, 1) == 0


def test_get_welcome_messages_is_documented_for_users():
    from pyrogram.methods.ephemeral.get_welcome_messages import GetWelcomeMessages

    assert "usable-by/users.rst" in GetWelcomeMessages.get_welcome_messages.__doc__


async def test_get_bot_info_asks_for_the_default_localisation():
    from pyrogram.methods.bots.get_bot_info import GetBotInfo

    class _Client(GetBotInfo):
        async def invoke(self, query, *args, **kwargs):
            return query

    assert (await _Client().get_bot_info()).lang_code == ""


def test_set_bot_name_is_annotated_as_bool():
    from pyrogram.methods.bots.set_bot_name import SetBotName

    assert inspect.signature(SetBotName.set_bot_name).return_annotation is bool


def _empty_updates():
    return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)


class _Client(SendMediaGroup, SendMessage, SendVenue, EditMessageText,
              GetScheduledMessages, DeleteScheduledMessages):
    parse_mode = enums.ParseMode.MARKDOWN
    link_preview_options = None
    me = None

    def __init__(self, reply=None):
        self.sent = []
        self.reply = reply if reply is not None else _empty_updates()
        self.parser = Parser(self)

    async def resolve_peer(self, peer_id):
        return raw.types.InputPeerSelf()

    def rnd_id(self):
        return 1

    def guess_mime_type(self, filename):
        return None

    async def save_file(self, path, *args, **kwargs):
        return raw.types.InputFile(id=1, parts=1, name="x", md5_checksum="") if path else None

    async def invoke(self, query, *args, **kwargs):
        self.sent.append(query)

        if isinstance(query, raw.functions.messages.UploadMedia):
            return raw.types.MessageMediaDocument(
                document=raw.types.Document(
                    id=1, access_hash=2, file_reference=b"", date=0, mime_type="",
                    size=1, dc_id=2, attributes=[], thumbs=[], video_thumbs=[]
                )
            )

        return self.reply


def _message_audit_sept_sending(client):
    message = types.Message(id=7, chat=object.__new__(type("C", (), {"id": -100})))
    message._client = client

    return message


async def test_a_reply_shortcut_forwards_its_legacy_reply_and_quote_kwargs():
    client = type("C", (), {"send_message": AsyncMock()})()
    message = _message_audit_sept_sending(client)

    await message.reply("hi", reply_to_message_id=5, quote_text="q")

    params = client.send_message.call_args.kwargs["reply_parameters"]
    assert (params.message_id, params.quote) == (5, "q"), (
        "the default ReplyParameters must carry the legacy kwargs; send_message "
        "ignores them once reply_parameters is set"
    )

    await message.reply("hi")
    assert client.send_message.call_args.kwargs["reply_parameters"].message_id == 7


async def test_a_grouped_audio_or_document_keeps_its_file_name():
    client = _Client()

    await client.send_media_group("me", [
        types.InputMediaAudio(io.BytesIO(b"a"), file_name="song.ogg"),
        types.InputMediaDocument(io.BytesIO(b"d"), file_name="notes.txt"),
    ])

    uploads = [q.media for q in client.sent if isinstance(q, raw.functions.messages.UploadMedia)]
    names = [
        a.file_name for m in uploads for a in m.attributes
        if isinstance(a, raw.types.DocumentAttributeFilename)
    ]
    assert names == ["song.ogg", "notes.txt"]


async def test_a_grouped_document_is_forced_to_stay_a_file():
    client = _Client()

    await client.send_media_group("me", [
        types.InputMediaDocument(io.BytesIO(b"d")),
        types.InputMediaDocument(io.BytesIO(b"d"), disable_content_type_detection=False),
    ])

    uploads = [q.media for q in client.sent if isinstance(q, raw.functions.messages.UploadMedia)]
    assert [m.force_file for m in uploads] == [True, False]


async def test_a_link_preview_url_is_sent_and_edited_as_a_web_page():
    client = _Client()
    options = types.LinkPreviewOptions(url="https://example.com", prefer_large_media=True)

    await client.send_message("me", "hi", link_preview_options=options)
    await client.edit_message_text("me", 1, "hi", link_preview_options=options)

    sent, edited = client.sent
    assert isinstance(sent, raw.functions.messages.SendMedia)
    assert sent.media == raw.types.InputMediaWebPage(
        url="https://example.com", force_large_media=True, force_small_media=None, optional=True
    )
    assert sent.message == "hi"
    assert edited.media == sent.media

    client.sent.clear()
    await client.send_message("me", "hi")
    assert isinstance(client.sent[0], raw.functions.messages.SendMessage)


async def test_edit_story_media_without_media_does_not_crash():
    from pyrogram.methods.stories.edit_story_media import EditStoryMedia

    class _StoryClient(EditStoryMedia):
        parse_mode = enums.ParseMode.MARKDOWN

        def __init__(self):
            self.sent = []
            self.parser = Parser(self)

        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

        async def save_file(self, path, *args, **kwargs):
            return raw.types.InputFile(id=1, parts=1, name="x", md5_checksum="") if path else None

        async def invoke(self, query, *args, **kwargs):
            self.sent.append(query)
            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    client = _StoryClient()

    result = await client.edit_story_media("me", 5, media=None)

    assert result is None
    assert isinstance(client.sent[0], raw.functions.stories.EditStory)
    assert client.sent[0].media is None


async def test_a_venue_with_a_foursquare_id_names_its_provider():
    client = _Client()

    await client.send_venue("me", 0.0, 0.0, "t", "a", foursquare_id="4a")
    await client.send_venue("me", 0.0, 0.0, "t", "a")

    assert [q.media.provider for q in client.sent] == ["foursquare", ""]


async def test_a_markdown_code_fence_drops_its_own_newlines():
    markdown = Markdown(None)
    text = "a\n```py\nx\n```\nb"

    result = await markdown.parse(text)
    entity = result["entities"][0]

    assert result["message"] == "a\nx\nb"
    assert (entity.offset, entity.length, entity.language) == (2, 1, "py")

    class Entity:
        type = enums.MessageEntityType.PRE
        offset = 2
        length = 1
        language = "py"

    assert Markdown.unparse(result["message"], [Entity()]) == text, (
        "the round trip must give the text back; a newline kept inside the "
        "entity grows the text on every pass"
    )


async def test_scheduled_history_is_parsed_as_scheduled(monkeypatch):
    seen = {}

    async def fake_parse(client, message, users, chats, **kwargs):
        seen.update(kwargs)

        return types.Message(id=message.id)

    monkeypatch.setattr(types.Message, "_parse", fake_parse)
    client = _Client(raw.types.messages.Messages(
        messages=[raw.types.MessageEmpty(id=1)], topics=[], chats=[], users=[]
    ))

    await client.get_scheduled_messages("me")

    assert seen.get("is_scheduled") is True


async def test_copying_media_uses_the_callers_effect():
    client = type("C", (), {"send_cached_media": AsyncMock()})()
    message = _message_audit_sept_sending(client)
    message.media = enums.MessageMediaType.PHOTO
    message.photo = object.__new__(type("P", (), {"file_id": "f"}))
    message.effect_id = 1

    await message.copy(chat_id="me", effect_id=2)

    assert client.send_cached_media.call_args.kwargs["effect_id"] == 2


async def test_deleting_scheduled_messages_reports_the_servers_answer():
    deleted = raw.types.Updates(
        updates=[raw.types.UpdateDeleteScheduledMessages(
            peer=raw.types.PeerUser(user_id=1), messages=[1]
        )],
        users=[], chats=[], date=0, seq=0
    )

    assert await _Client(deleted).delete_scheduled_messages("me", [1]) is True
    assert await _Client().delete_scheduled_messages("me", [1]) is False


def _channel(**kwargs):
    kwargs.setdefault("usernames", [])
    kwargs.setdefault("restriction_reason", [])

    return raw.types.Channel(id=7, title="t", photo=raw.types.ChatPhotoEmpty(), date=0, **kwargs)


def _user_audit_sept_chats(uid):
    return raw.types.User(id=uid, first_name=f"u{uid}", usernames=[], restriction_reason=[])


def _chat_full(participants, users):
    return raw.types.messages.ChatFull(
        full_chat=raw.types.ChatFull(
            id=5,
            about="",
            participants=raw.types.ChatParticipants(chat_id=5, participants=participants, version=1),
            notify_settings=raw.types.PeerNotifySettings(),
        ),
        chats=[],
        users=users,
    )


async def test_an_expired_custom_emoji_id_is_skipped_not_crashed():
    from pyrogram.methods.messages.get_custom_emoji_stickers import GetCustomEmojiStickers

    class _Client(GetCustomEmojiStickers):
        async def invoke(self, query, *args, **kwargs):
            return [raw.types.DocumentEmpty(id=1)]

    assert await _Client().get_custom_emoji_stickers([1]) == []


async def test_pinning_in_a_private_chat_is_documented_to_return_none():
    from pyrogram.methods.chats.pin_chat_message import PinChatMessage

    class _Client(PinChatMessage):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

        async def invoke(self, query, *args, **kwargs):
            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    assert await _Client().pin_chat_message("me", 1) is None
    assert "None" in PinChatMessage.pin_chat_message.__doc__


async def test_translating_without_a_target_language_is_a_clear_error():
    from pyrogram.methods.messages.translate_text import TranslateText

    class _Client(TranslateText):
        async def invoke(self, query, *args, **kwargs):
            raise AssertionError("must not reach the server")

    with pytest.raises(ValueError):
        await _Client().translate_text(text="hi")


def test_join_by_request_is_parsed_for_a_channel():
    assert types.Chat._parse_channel_chat(None, _channel(join_request=True)).join_by_request is True
    assert types.Chat._parse_channel_chat(None, _channel()).join_by_request is None


async def test_migrated_from_max_message_id_is_populated():
    from pyrogram.types.user_and_chats.chat import Chat

    class _Client:
        me = None

        async def get_messages(self, *args, **kwargs):
            return None

        async def invoke(self, query, *args, **kwargs):
            return raw.types.messages.ChatFull(
                full_chat=raw.types.ChannelFull(
                    id=7,
                    about="",
                    read_inbox_max_id=0,
                    read_outbox_max_id=0,
                    unread_count=0,
                    chat_photo=raw.types.PhotoEmpty(id=0),
                    notify_settings=raw.types.PeerNotifySettings(),
                    bot_info=[],
                    pts=0,
                    migrated_from_chat_id=5,
                    migrated_from_max_id=42,
                ),
                chats=[_channel(megagroup=True)],
                users=[],
            )

    chat = await Chat._parse_full(_Client(), await _Client().invoke(None))

    assert chat.migrated_from_max_message_id == 42
    assert not hasattr(chat, "migrated_from_max_id")


async def test_banning_from_a_basic_group_by_username_uses_the_resolved_id():
    from pyrogram.methods.chats.ban_chat_member import BanChatMember

    class _Client(BanChatMember):
        sent = None

        async def resolve_peer(self, peer_id):
            if peer_id == "@group":
                return raw.types.InputPeerChat(chat_id=5)

            return raw.types.InputPeerUser(user_id=9, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            self.sent = query

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    client = _Client()

    assert await client.ban_chat_member("@group", 9) is True
    assert client.sent.chat_id == 5


async def test_a_non_user_peer_in_a_basic_group_is_not_a_participant():
    from pyrogram.methods.chats.get_chat_member import GetChatMember

    class _Client(GetChatMember):
        async def resolve_peer(self, peer_id):
            if peer_id == "@group":
                return raw.types.InputPeerChat(chat_id=5)

            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            raise AssertionError("must not reach the server")

    with pytest.raises(UserNotParticipant):
        await _Client().get_chat_member("@group", "@somechannel")


async def test_basic_group_members_honour_the_limit():
    from pyrogram.methods.chats.get_chat_members import GetChatMembers

    participants = [raw.types.ChatParticipant(user_id=i, inviter_id=1, date=0) for i in (1, 2, 3)]

    class _Client(GetChatMembers):
        me = None

        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChat(chat_id=5)

        async def invoke(self, query, *args, **kwargs):
            return _chat_full(participants, [_user_audit_sept_chats(i) for i in (1, 2, 3)])

    async def ids(**kwargs):
        return [m.user.id async for m in _Client().get_chat_members(5, **kwargs)]

    assert await ids(limit=2) == [1, 2]
    assert await ids() == [1, 2, 3]
    assert await ids(limit=0) == [1, 2, 3]


async def test_the_pinned_archive_folder_is_not_a_dialog():
    from pyrogram.methods.chats.get_dialogs_count import GetDialogsCount

    def dialog(uid):
        return raw.types.Dialog(
            peer=raw.types.PeerUser(user_id=uid),
            top_message=1,
            read_inbox_max_id=0,
            read_outbox_max_id=0,
            unread_count=0,
            unread_mentions_count=0,
            unread_reactions_count=0,
            unread_poll_votes_count=0,
            notify_settings=raw.types.PeerNotifySettings(),
        )

    folder = raw.types.DialogFolder(
        folder=raw.types.Folder(id=1, title="Archived"),
        peer=raw.types.PeerUser(user_id=1),
        top_message=1,
        unread_muted_peers_count=0,
        unread_unmuted_peers_count=0,
        unread_muted_messages_count=0,
        unread_unmuted_messages_count=0,
    )

    class _Client(GetDialogsCount):
        async def invoke(self, query, *args, **kwargs):
            return raw.types.messages.PeerDialogs(
                dialogs=[folder, dialog(1), dialog(2)],
                messages=[],
                chats=[],
                users=[],
                state=raw.types.updates.State(pts=0, qts=0, date=0, seq=0, unread_count=0),
            )

    assert await _Client().get_dialogs_count(pinned_only=True) == 2


async def test_unbanning_in_a_basic_group_does_not_ask_a_channel_rpc():
    """unban_chat_member always sent channels.EditBanned, which the server
    rejects with CHANNEL_INVALID for a basic group. Basic groups keep no ban
    list, so there is nothing to undo and the call succeeds without a request.
    """

    from pyrogram.methods.chats.unban_chat_member import UnbanChatMember

    sent = []

    class _Client(UnbanChatMember):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChat(chat_id=5) if peer_id == -5 else raw.types.InputPeerUser(user_id=1, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            sent.append(query)
            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    assert await _Client().unban_chat_member(-5, 1) is True
    assert sent == []


def test_run_works_without_a_current_event_loop(monkeypatch):
    import threading

    from pyrogram.methods.utilities import run as run_module

    calls = []

    async def fake_idle():
        calls.append("idle")

    monkeypatch.setattr(run_module, "idle", fake_idle)

    class _Client(pyrogram.Client):
        async def start(self, *args, **kwargs):
            calls.append("start")

        async def stop(self, *args, **kwargs):
            calls.append("stop")

    async def main():
        calls.append("main")

    errors = []

    def target():
        try:
            app = _Client("run", api_id=1, api_hash="a" * 32, in_memory=True)
            app.run(main())
            app.run()
            app.loop.close()
        except Exception as e:
            errors.append(e)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    assert errors == []
    assert calls == ["main", "start", "idle", "stop"]


@pytest.mark.parametrize("scheduled", [True, False])
async def test_shortcuts_on_a_scheduled_message_act_on_the_scheduled_one(scheduled):
    from datetime import datetime

    when = datetime(2030, 1, 1, 12, 0)
    client = AsyncMock()
    message = types.Message(
        id=2,
        chat=types.Chat(id=-100, type=enums.ChatType.SUPERGROUP),
        date=when,
        scheduled=scheduled,
        client=client,
    )

    await message.delete()
    await message.edit_text("x")
    await message.edit_caption("x")
    await message.edit_media(types.InputMediaPhoto("x"))
    await message.edit_checklist(types.InputChecklist(title="x", tasks=[]))
    await message.edit_reply_markup(None)

    if scheduled:
        client.delete_scheduled_messages.assert_awaited_once_with(-100, [2])
        client.delete_messages.assert_not_awaited()
    else:
        client.delete_messages.assert_awaited_once()
        client.delete_scheduled_messages.assert_not_awaited()

    for name in ("edit_message_text", "edit_message_caption", "edit_message_media",
                 "edit_message_checklist", "edit_message_reply_markup"):
        kwargs = getattr(client, name).await_args.kwargs
        assert kwargs["message_id"] == 2
        assert kwargs["schedule_date"] == (when if scheduled else None), name


async def test_editing_a_scheduled_message_returns_it():
    reply = raw.core.TLObject.read(BytesIO(raw.types.Updates(
        updates=[raw.types.UpdateNewScheduledMessage(message=raw.types.Message(
            id=2, peer_id=raw.types.PeerUser(user_id=1), date=1893499200,
            message="edited", out=True,
        ))],
        users=[raw.types.User(id=1, first_name="a")], chats=[], date=0, seq=0,
    ).write()))

    client = _Client(reply)
    client.message_cache = {}

    edited = await client.edit_message_text("me", 2, "edited")

    assert edited is not None
    assert edited.id == 2
    assert edited.text == "edited"
    assert edited.scheduled is True


_SCHEDULED_REFUSED = sorted(
    name for name, _ in inspect.getmembers(types.Message, inspect.iscoroutinefunction)
    if name.startswith("reply") and name != "reply_chat_action"
) + [
    "forward", "copy_media_group", "pin", "unpin", "react", "vote", "retract_vote", "click", "read",
    "view", "get_media_group", "edit_live_location", "stop_live_location", "pay",
    "accept_gift_purchase_offer", "reject_gift_purchase_offer", "summarize", "wait_for_click",
]


def _scheduled_message(scheduled):
    from datetime import datetime

    return types.Message(
        id=2,
        chat=types.Chat(id=-100, type=enums.ChatType.SUPERGROUP),
        from_user=types.User(id=5),
        date=datetime(2030, 1, 1),
        scheduled=scheduled,
        client=AsyncMock(),
    )


async def _call_with_placeholders(message, name):
    method = getattr(message, name)
    required = [
        p.name for p in inspect.signature(method).parameters.values()
        if p.default is inspect.Parameter.empty and p.kind is p.POSITIONAL_OR_KEYWORD
    ]

    await method(**{p: 1 if p in ("latitude", "longitude", "heading") else "x" for p in required})


@pytest.mark.parametrize("name", _SCHEDULED_REFUSED)
async def test_a_scheduled_message_refuses_shortcuts_that_would_hit_a_sent_message(name):
    message = _scheduled_message(True)

    with pytest.raises(ValueError, match="scheduled message"):
        await _call_with_placeholders(message, name)

    assert message._client.method_calls == []


@pytest.mark.parametrize("name", ["reply_text", "forward", "pin", "react", "answer", "answer_photo"])
async def test_the_scheduled_guard_leaves_sent_messages_and_answers_alone(name):
    await _call_with_placeholders(_scheduled_message(False), name)

    if name.startswith("answer"):
        await _call_with_placeholders(_scheduled_message(True), name)


async def test_a_scheduled_message_is_not_cached_under_a_sent_message_id():
    client = _Client()
    client.message_cache = {}

    await types.Message._parse(
        client,
        raw.core.TLObject.read(BytesIO(raw.types.Message(
            id=2, peer_id=raw.types.PeerUser(user_id=1), date=1893499200, message="later", out=True,
        ).write())),
        {1: raw.core.TLObject.read(BytesIO(raw.types.User(id=1, first_name="a").write()))},
        {},
        is_scheduled=True,
    )

    assert client.message_cache == {}


class _ResolveStorage:
    def __init__(self, peers):
        self.peers = peers
        self.asked = []

    async def get_peer_by_id(self, peer_id):
        self.asked.append(peer_id)
        return self.peers[peer_id]

    async def get_peer_by_username(self, username):
        return self.peers[username]

    async def get_peer_by_phone_number(self, phone):
        return self.peers[phone]


def _resolve_client(peers, answer=None):
    client = pyrogram.Client("resolve", api_id=1, api_hash="a" * 32, in_memory=True)
    client.storage = _ResolveStorage(peers)
    client.is_connected = True
    client.sent = []

    async def invoke(query, *args, **kwargs):
        client.sent.append(query)
        for key, value in (answer or {}).items():
            client.storage.peers[key] = value
        return raw.types.contacts.ResolvedPeer(peer=raw.types.PeerUser(user_id=42), chats=[], users=[])

    client.invoke = invoke
    return client


@pytest.mark.parametrize("link", [
    "https://t.me/Telegram", "t.me/telegram", "http://www.t.me/telegram/5", "https://telegram.me/telegram?start=x",
])
async def test_resolve_peer_reads_the_username_out_of_a_link(link):
    peer = raw.types.InputPeerChannel(channel_id=1, access_hash=2)

    assert await _resolve_client({"telegram": peer}).resolve_peer(link) == peer


async def test_resolve_peer_reads_the_channel_id_out_of_a_private_link():
    peer = raw.types.InputPeerChannel(channel_id=1234, access_hash=2)
    client = _resolve_client({utils.get_channel_id(1234): peer})

    assert await client.resolve_peer("https://t.me/c/1234/56") == peer
    assert client.sent == []


async def test_resolve_peer_asks_telegram_for_an_unknown_phone_number():
    peer = raw.types.InputPeerUser(user_id=42, access_hash=7)
    client = _resolve_client({}, answer={42: peer})

    assert await client.resolve_peer("+1 202 555 0123") == peer
    assert [type(q) for q in client.sent] == [raw.functions.contacts.ResolvePhone]
    assert client.sent[0].phone == "12025550123"


async def test_resolve_peer_does_not_ask_for_a_phone_that_is_not_one():
    client = _resolve_client({})

    with pytest.raises(pyrogram.errors.PeerIdInvalid):
        await client.resolve_peer("-100123")

    assert client.sent == []


async def test_resolve_peer_keeps_peer_id_invalid_for_a_phone_telegram_does_not_know():
    client = _resolve_client({})

    async def invoke(query, *args, **kwargs):
        raise pyrogram.errors.BadRequest("[400 PHONE_NOT_OCCUPIED]")

    client.invoke = invoke

    with pytest.raises(pyrogram.errors.PeerIdInvalid):
        await client.resolve_peer("+999 000 0000")


def _photo_file_id():
    from pyrogram.file_id import FileId, FileType, ThumbnailSource

    return FileId(file_type=FileType.PHOTO, dc_id=2, media_id=1, access_hash=2, file_reference=b"r",
                  thumbnail_source=ThumbnailSource.THUMBNAIL, volume_id=0, local_id=0,
                  thumbnail_file_type=FileType.PHOTO, thumbnail_size="y").encode()


def test_live_photo_by_file_id_sends_the_video_as_an_input_document():
    from pyrogram.file_id import FileId, FileType

    video = FileId(file_type=FileType.VIDEO, dc_id=2, media_id=3, access_hash=4, file_reference=b"v").encode()
    media = utils.get_input_media_from_file_id(
        _photo_file_id(), FileType.PHOTO, live_photo=True, live_photo_video_file_id=video
    )

    assert media.video == raw.types.InputDocument(id=3, access_hash=4, file_reference=b"v")
    assert raw.core.TLObject.read(BytesIO(media.write())).video == media.video


@pytest.mark.parametrize("make, expected", [
    (lambda path: types.InputMediaPhoto(path, has_spoiler=True), raw.types.InputMediaPhoto),
    (lambda path: types.InputMediaVideo(path, has_spoiler=True), raw.types.InputMediaDocument),
    (lambda path: types.InputMediaPhoto(_photo_file_id(), has_spoiler=True), raw.types.InputMediaPhoto),
])
async def test_edit_inline_media_sends_the_right_media_with_its_spoiler(monkeypatch, tmp_path, make, expected):
    import pyrogram.methods.messages.edit_inline_media as module

    path = tmp_path / "a.jpg"
    path.write_bytes(b"\xff\xd8\xff")
    client = pyrogram.Client("inline", api_id=1, api_hash="x", in_memory=True)
    sent = []

    async def save_file(*args, **kwargs):
        return raw.types.InputFile(id=1, parts=1, name="a.jpg", md5_checksum="")

    async def invoke(query, *args, **kwargs):
        if isinstance(query.media, raw.types.InputMediaUploadedPhoto):
            return raw.types.MessageMediaPhoto(
                photo=raw.types.Photo(id=5, access_hash=6, file_reference=b"r", date=0, sizes=[], dc_id=2)
            )
        return raw.types.MessageMediaDocument(
            document=raw.types.Document(id=7, access_hash=8, file_reference=b"r", date=0,
                                        mime_type="video/mp4", size=1, dc_id=2, attributes=[])
        )

    async def invoke_inline(client, dc_id, query, business_connection_id=None):
        sent.append(query)
        return True

    monkeypatch.setattr(client, "save_file", save_file)
    monkeypatch.setattr(client, "invoke", invoke)
    monkeypatch.setattr(module, "invoke_inline", invoke_inline)
    inline_message_id = utils.pack_inline_message_id(
        raw.types.InputBotInlineMessageID(dc_id=2, id=1, access_hash=2)
    )

    assert await client.edit_inline_media(inline_message_id, make(str(path))) is True
    assert isinstance(sent[0].media, expected)
    assert sent[0].media.spoiler is True


def _roundtrip(obj):
    return raw.core.TLObject.read(BytesIO(obj.write()))


def _business_client():
    client = pyrogram.Client("business", api_id=1, api_hash="x", in_memory=True)
    client.me = SimpleNamespace(id=222, is_bot=True, is_premium=False)
    client.sent = []

    async def resolve_peer(peer):
        return raw.types.InputPeerUser(user_id=111, access_hash=1)

    async def invoke(query, *args, **kwargs):
        client.sent.append(query)
        count = len(query.multi_media) if isinstance(query, raw.functions.messages.SendMultiMedia) else 1
        media = None
        if isinstance(getattr(query, "media", None), raw.types.InputMediaPoll):
            media = raw.types.MessageMediaPoll(
                poll=raw.types.Poll(id=9, question=raw.types.TextWithEntities(text="q", entities=[]),
                                    answers=[], hash=0, closed=True),
                results=raw.types.PollResults()
            )
        return raw.types.Updates(
            updates=[
                raw.types.UpdateBotNewBusinessMessage(connection_id="BC", qts=1, message=_roundtrip(raw.types.Message(
                    id=n + 1, peer_id=raw.types.PeerUser(user_id=111), date=1700000000, message="hi",
                    from_id=raw.types.PeerUser(user_id=222), out=True, media=media
                )))
                for n in range(count)
            ],
            users=[_roundtrip(raw.types.User(id=111, access_hash=1, first_name="Ann")),
                   _roundtrip(raw.types.User(id=222, access_hash=2, first_name="Bot", bot=True,
                                             bot_info_version=1))],
            chats=[], date=1700000000, seq=0
        )

    client.resolve_peer = resolve_peer
    client.invoke = invoke
    return client


@pytest.mark.parametrize("call", [
    lambda c: c.send_message(111, "hi", business_connection_id="BC"),
    lambda c: c.send_dice(111, business_connection_id="BC"),
    lambda c: c.send_location(111, 1.0, 2.0, business_connection_id="BC"),
    lambda c: c.send_cached_media(111, _photo_file_id(), business_connection_id="BC"),
    lambda c: c.send_game(111, "game", business_connection_id="BC"),
    lambda c: c.edit_message_text(111, 1, "x", business_connection_id="BC"),
    lambda c: c.pin_chat_message(111, 1, business_connection_id="BC"),
])
async def test_business_sends_and_edits_return_the_message(call):
    message = await call(_business_client())

    assert isinstance(message, types.Message)
    assert message.business_connection_id == "BC"


async def test_business_forward_and_media_group_return_every_message():
    client = _business_client()

    forwarded = await client.forward_messages(111, 111, [1], business_connection_id="BC")
    group = await client.send_media_group(
        111, [types.InputMediaPhoto(_photo_file_id()), types.InputMediaPhoto(_photo_file_id())],
        business_connection_id="BC"
    )

    assert [m.business_connection_id for m in forwarded] == ["BC"]
    assert [m.business_connection_id for m in group] == ["BC", "BC"]


async def test_business_stop_poll_closes_the_poll_without_reading_the_chat():
    client = _business_client()

    poll = await client.stop_poll(111, 1, business_connection_id="BC")

    assert poll.is_closed is True
    assert [type(q) for q in client.sent] == [raw.functions.messages.EditMessage]
    assert client.sent[0].media.poll.closed is True


async def test_set_game_score_on_an_inline_message_returns_true_and_edits_by_default():
    client = pyrogram.Client("game", api_id=1, api_hash="x", in_memory=True)
    sent = []

    async def resolve_peer(peer):
        return raw.types.InputPeerUser(user_id=111, access_hash=1)

    async def invoke(query, *args, **kwargs):
        sent.append(query)
        return True

    client.resolve_peer = resolve_peer
    client.invoke = invoke
    inline_message_id = utils.pack_inline_message_id(
        raw.types.InputBotInlineMessageID(dc_id=2, id=1, access_hash=2)
    )

    assert await client.set_game_score(111, 10, inline_message_id=inline_message_id) is True
    await client.set_game_score(111, 10, inline_message_id=inline_message_id, disable_edit_message=True)

    assert [q.edit_message for q in sent] == [True, None]


def _dialog(user_id, top_message):
    return raw.types.Dialog(
        peer=raw.types.PeerUser(user_id=user_id), top_message=top_message, read_inbox_max_id=0,
        read_outbox_max_id=0, unread_count=0, unread_mentions_count=0, unread_reactions_count=0,
        unread_poll_votes_count=0, notify_settings=raw.types.PeerNotifySettings()
    )


@pytest.mark.parametrize("with_message, offset_id", [(True, 5), (False, 0)])
async def test_get_dialogs_pages_past_a_dialog_without_a_top_message(with_message, offset_id):
    client = pyrogram.Client("dialogs", api_id=1, api_hash="x", in_memory=True)
    sent = []
    messages = [_roundtrip(raw.types.Message(
        id=5, peer_id=raw.types.PeerUser(user_id=111), date=1700000000, message="a"
    ))] if with_message else []

    async def resolve_peer(peer):
        return raw.types.InputPeerUser(user_id=peer, access_hash=1)

    async def invoke(query, *args, **kwargs):
        sent.append(query)
        if len(sent) > 1:
            return raw.types.messages.Dialogs(dialogs=[], messages=[], chats=[], users=[])
        return raw.types.messages.DialogsSlice(
            count=50, dialogs=[_dialog(111, 5), _dialog(333, 9)], messages=messages, chats=[],
            users=[_roundtrip(raw.types.User(id=111, access_hash=1, first_name="Ann")),
                   _roundtrip(raw.types.User(id=333, access_hash=3, first_name="Cy"))]
        )

    client.resolve_peer = resolve_peer
    client.invoke = invoke

    assert [d.chat.id async for d in client.get_dialogs()] == [111, 333]
    assert len(sent) == 2
    assert (sent[1].offset_id, sent[1].offset_peer.user_id) == (offset_id, 333)


async def test_get_call_members_stops_when_there_is_no_next_page():
    client = pyrogram.Client("call", api_id=1, api_hash="x", in_memory=True)
    sent = []

    async def resolve_peer(peer):
        return raw.types.InputPeerChannel(channel_id=1, access_hash=1)

    async def invoke(query, *args, **kwargs):
        if isinstance(query, raw.functions.channels.GetFullChannel):
            return SimpleNamespace(full_chat=SimpleNamespace(call=raw.types.InputGroupCall(id=1, access_hash=1)))
        sent.append(query.offset)
        return raw.types.phone.GroupParticipants(
            count=1, next_offset="", chats=[], version=1,
            participants=[raw.types.GroupCallParticipant(peer=raw.types.PeerUser(user_id=111), date=1700000000,
                                                         source=1)],
            users=[_roundtrip(raw.types.User(id=111, access_hash=1, first_name="Ann"))]
        )

    client.resolve_peer = resolve_peer
    client.invoke = invoke

    members = [m async for m in client.get_call_members(-1001)]

    assert len(members) == 1
    assert sent == [""]


async def _received_rich_message(client, part=False):
    blocks = [raw.types.PageBlockParagraph(text=raw.types.TextConcat(texts=[
        raw.types.TextPlain(text="Hi "),
        raw.types.TextMentionName(text=raw.types.TextPlain(text="you"), user_id=111),
    ]))]
    photo = raw.types.Photo(id=5, access_hash=6, file_reference=b"r", date=0, sizes=[], dc_id=2)
    rich = raw.types.RichMessage(blocks=blocks, photos=[photo], documents=[], part=part)
    users = {111: _roundtrip(raw.types.User(id=111, access_hash=9, first_name="Ann"))}
    return blocks, await types.RichMessage._parse(client, rich, users, {})


@pytest.mark.parametrize("partial", [False, True])
async def test_a_received_rich_message_can_be_copied(partial):
    client = pyrogram.Client("rich", api_id=1, api_hash="x", in_memory=True)
    blocks, rich = await _received_rich_message(client, part=partial)
    full_blocks, full = await _received_rich_message(client)
    sent, fetched = [], []

    async def send_message(chat_id, **kwargs):
        sent.append(await utils.build_input_rich_message(client, kwargs["rich_text"]))
        return "copied"

    async def get_rich_message(chat_id, message_id):
        fetched.append((chat_id, message_id))
        return SimpleNamespace(rich_message=full)

    client.send_message = send_message
    client.get_rich_message = get_rich_message
    message = types.Message(id=7, chat=types.Chat(id=-1001, type=enums.ChatType.SUPERGROUP),
                            rich_message=rich, client=client)

    assert await message.copy(42) == "copied"
    assert fetched == ([(-1001, 7)] if partial else [])
    assert sent[0].blocks == (full_blocks if partial else blocks)
    assert sent[0].photos == [raw.types.InputPhoto(id=5, access_hash=6, file_reference=b"r")]
    assert sent[0].users == [raw.types.InputUser(user_id=111, access_hash=9)]


def _mention(uid):
    return raw.types.TextMentionName(text=raw.types.TextPlain(text="you"), user_id=uid)


def test_a_mention_inside_a_list_item_is_collected():
    from pyrogram.types.input_content.input_rich_block import (
        InputRichBlockList,
        InputRichBlockListItem,
        _collect_mentioned_user_ids,
    )

    blocks = [InputRichBlockList(items=[InputRichBlockListItem(text=_mention(111))])]

    assert _collect_mentioned_user_ids(blocks) == [111]


def test_a_mention_inside_a_table_cell_is_collected():
    from pyrogram.types.input_content.input_rich_block import (
        InputRichBlockTable,
        InputRichBlockTableCell,
        _collect_mentioned_user_ids,
    )

    blocks = [InputRichBlockTable(title="t", rows=[[InputRichBlockTableCell(text=_mention(222))]])]

    assert _collect_mentioned_user_ids(blocks) == [222]


def test_mentions_are_deduplicated_across_blocks():
    from pyrogram.types.input_content.input_rich_block import (
        InputRichBlockList,
        InputRichBlockListItem,
        InputRichBlockParagraph,
        _collect_mentioned_user_ids,
    )

    blocks = [
        InputRichBlockParagraph(text=_mention(333)),
        InputRichBlockList(items=[
            InputRichBlockListItem(text=_mention(444)),
            InputRichBlockListItem(text=_mention(333)),
        ]),
    ]

    assert _collect_mentioned_user_ids(blocks) == [333, 444]


def test_a_mention_inside_received_rich_text_is_collected():
    from pyrogram.types.input_content.input_rich_block import (
        InputRichBlockParagraph,
        _collect_mentioned_user_ids,
    )

    text = raw.types.TextConcat(texts=raw.core.List([raw.types.TextPlain(text="hi "), _mention(555)]))

    assert _collect_mentioned_user_ids([InputRichBlockParagraph(text=text)]) == [555]


class _TooLongClient:
    handle_updates = pyrogram.Client.handle_updates
    _save_update_state = pyrogram.Client._save_update_state
    _recover_too_long = pyrogram.Client._recover_too_long
    _recover_too_long_state = pyrogram.Client._recover_too_long_state

    def __init__(self, states=(), replies=()):
        self.states = []
        self._state_marks = {}
        self._recovering = set()
        self.skip_updates = False
        self.loop = None
        self.recovered = []
        self.fetched = []
        self.sent = []
        self.replies = list(replies)

        outer = self

        class _Storage:
            async def update_state(self, value=object):
                if value is object:
                    return list(states)
                outer.states.append(value)

        class _Dispatcher:
            async def enqueue_update(self, update, users, chats):
                return True

        self.storage = _Storage()
        self.dispatcher = _Dispatcher()

    async def fetch_peers(self, peers):
        self.fetched.extend(peers)
        return any(getattr(p, "min", False) for p in peers)

    async def resolve_peer(self, peer_id):
        return raw.types.InputChannel(channel_id=1, access_hash=0)

    async def invoke(self, query, **kwargs):
        self.sent.append(query)
        return self.replies.pop(0)

    async def recover_gaps(self, ids=None):
        self.recovered.append(ids)
        return (0, 0)


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


def _too_long_batch(*updates):
    return raw.types.Updates(updates=list(updates), users=[], chats=[], date=1700000000, seq=4)


async def test_a_channel_too_long_update_recovers_from_the_state_seen_in_this_run():
    client = _TooLongClient()
    client._state_marks[-1000000000005] = (10, None)

    await client.handle_updates(_too_long_batch(raw.types.UpdateChannelTooLong(channel_id=5, pts=30)))
    await _settle()

    assert client.recovered == [-1000000000005]
    assert client.states == []
    assert client._recovering == set()


async def test_a_channel_too_long_update_for_a_channel_not_seen_in_this_run_only_records_its_pts():
    client = _TooLongClient(states=[(-1000000000005, 10, None, None, None)])

    await client.handle_updates(_too_long_batch(raw.types.UpdateChannelTooLong(channel_id=5, pts=30)))
    await _settle()

    assert client.recovered == []
    assert client.states == [(-1000000000005, 30, None, None, None)]
    assert client._state_marks[-1000000000005] == (30, None)


async def test_a_channel_too_long_update_behind_the_known_pts_is_ignored():
    client = _TooLongClient()
    client._state_marks[-1000000000005] = (30, None)

    await client.handle_updates(_too_long_batch(raw.types.UpdateChannelTooLong(channel_id=5, pts=30)))
    await _settle()

    assert client.recovered == []


async def test_updates_too_long_recovers_the_common_state_seen_in_this_run():
    client = _TooLongClient()
    client._state_marks[0] = (10, 50)

    await client.handle_updates(raw.types.UpdatesTooLong())
    await _settle()

    assert client.recovered == [0]


async def test_updates_too_long_before_any_update_records_the_server_state():
    client = _TooLongClient(replies=[_state(40, 50)])

    await client.handle_updates(raw.types.UpdatesTooLong())
    await _settle()

    assert client.recovered == []
    assert isinstance(client.sent[0], raw.functions.updates.GetState)
    assert client.states == [(0, 40, 50, 9, 3)]


async def test_repeated_too_long_updates_recover_once_at_a_time():
    client = _TooLongClient()
    client._state_marks[0] = (10, 50)
    gate = asyncio.Event()

    async def recover_gaps(ids=None):
        client.recovered.append(ids)
        await gate.wait()
        return (0, 0)

    client.recover_gaps = recover_gaps

    await client.handle_updates(raw.types.UpdatesTooLong())
    await client.handle_updates(raw.types.UpdatesTooLong())
    await _settle()
    gate.set()
    await _settle()

    assert client.recovered == [0]
    assert client._recovering == set()


async def test_a_failing_too_long_recovery_is_logged_and_releases_the_key(caplog):
    client = _TooLongClient()
    client._state_marks[0] = (10, 50)

    async def recover_gaps(ids=None):
        raise RuntimeError("boom")

    client.recover_gaps = recover_gaps

    with caplog.at_level("ERROR"):
        await client.handle_updates(raw.types.UpdatesTooLong())
        await _settle()

    assert "Recovery after too long update failed" in caplog.text
    assert client._recovering == set()



async def test_peers_fetched_for_a_min_channel_message_are_stored():
    full_user = raw.types.User(id=7, access_hash=99, first_name="x")
    client = _TooLongClient(replies=[
        raw.types.updates.ChannelDifference(
            pts=12, new_messages=[], other_updates=[], chats=[], users=[full_user], final=True
        )
    ])

    await client.handle_updates(raw.types.Updates(
        updates=[raw.types.UpdateNewChannelMessage(
            message=raw.types.Message(
                id=3, peer_id=raw.types.PeerChannel(channel_id=5), date=0, message="hi",
                from_id=raw.types.PeerUser(user_id=7)
            ),
            pts=12, pts_count=1
        )],
        users=[raw.types.User(id=7, min=True, first_name="x")], chats=[], date=1700000000, seq=4,
    ))

    assert isinstance(client.sent[0], raw.functions.updates.GetChannelDifference)
    assert full_user in client.fetched
