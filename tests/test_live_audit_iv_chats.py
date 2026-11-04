import asyncio
import io
from types import SimpleNamespace

import pytest

from pyrogram import enums, raw, types
from pyrogram.methods.advanced.invoke import Invoke
from pyrogram.methods.advanced.save_file import SaveFile
from pyrogram.methods.chats.toggle_anti_spam import ToggleAntiSpam
from pyrogram.methods.chats.toggle_forum import ToggleForum
from pyrogram.methods.chats.toggle_pre_history_hidden import TogglePreHistoryHidden
from pyrogram.methods.chats.toggle_signatures import ToggleSignatures
from pyrogram.methods.chats.toggle_slow_mode import ToggleSlowMode
from pyrogram.methods.chats.toggle_view_forum_as_messages import ToggleViewForumAsMessages
from pyrogram.methods.invite_links.create_chat_invite_link import CreateChatInviteLink
from pyrogram.methods.messages.get_custom_emoji_stickers import GetCustomEmojiStickers
from pyrogram.methods.users.get_chat_photos import GetChatPhotos
from pyrogram.methods.users.get_chat_photos_count import GetChatPhotosCount


class _Recorder:
    def __init__(self, result=None, is_bot=False):
        self.queries = []
        self.result = result
        self.me = SimpleNamespace(is_bot=is_bot, id=1)

    async def invoke(self, query, *args, **kwargs):
        self.queries.append(query)
        return self.result

    async def resolve_peer(self, chat_id):
        return self.peer


def _raw_user(user_id):
    return raw.types.User(id=user_id, access_hash=0, first_name=f"u{user_id}", usernames=[], restriction_reason=[])


class _InvokeClient(Invoke):
    is_connected = True
    takeout_id = None
    rate_limiter = None
    retries = 3
    timeout = 40
    sleep_threshold = 10

    def __init__(self, no_updates, auto_no_updates):
        self.no_updates = no_updates
        self.auto_no_updates = auto_no_updates
        self.sent = []
        self.args = []
        self.session = SimpleNamespace(invoke=self._send)

    async def _send(self, query, *args):
        self.sent.append(query)
        self.args.append(args)
        return raw.types.Pong(msg_id=0, ping_id=0)

    async def fetch_peers(self, peers):
        return False


@pytest.mark.parametrize("no_updates,auto_no_updates", [(False, True), (True, False)])
async def test_invoke_never_wraps_a_service_function(no_updates, auto_no_updates):
    client = _InvokeClient(no_updates, auto_no_updates)

    await client.invoke(raw.functions.Ping(ping_id=1))
    await client.invoke(raw.functions.PingDelayDisconnect(ping_id=1, disconnect_delay=75))
    await client.invoke(raw.functions.help.GetConfig())

    assert isinstance(client.sent[0], raw.functions.Ping)
    assert isinstance(client.sent[1], raw.functions.PingDelayDisconnect)
    assert isinstance(client.sent[2], raw.functions.InvokeWithoutUpdates)


async def test_invoke_falls_back_to_the_retries_and_timeout_of_the_client():
    client = _InvokeClient(False, False)

    await client.invoke(raw.functions.help.GetConfig())
    await client.invoke(raw.functions.help.GetConfig(), retries=0, timeout=5)

    assert client.args == [(3, 40, 10), (0, 5, 10)]


class _PhotosClient(_Recorder, GetChatPhotos, GetChatPhotosCount):
    pass


async def test_get_chat_photos_on_a_basic_group_reads_the_chat():
    client = _PhotosClient(
        SimpleNamespace(full_chat=SimpleNamespace(chat_photo=raw.types.PhotoEmpty(id=0))),
        is_bot=True,
    )
    client.peer = raw.types.InputPeerChat(chat_id=5)

    assert [p async for p in client.get_chat_photos(-5)] == []
    assert isinstance(client.queries[0], raw.functions.messages.GetFullChat)
    assert client.queries[0].chat_id == 5


async def test_get_chat_photos_count_on_a_basic_group_reads_the_chat():
    client = _PhotosClient([SimpleNamespace(count=3)])
    client.peer = raw.types.InputPeerChat(chat_id=5)

    assert await client.get_chat_photos_count(-5) == 3
    assert isinstance(client.queries[0], raw.functions.messages.GetSearchCounters)
    assert client.queries[0].peer == client.peer

    client = _PhotosClient(
        SimpleNamespace(full_chat=SimpleNamespace(chat_photo=raw.types.PhotoEmpty(id=0))),
        is_bot=True,
    )
    client.peer = raw.types.InputPeerChat(chat_id=5)

    assert await client.get_chat_photos_count(-5) == 0
    assert isinstance(client.queries[0], raw.functions.messages.GetFullChat)


class _EmojiClient(_Recorder, GetCustomEmojiStickers):
    pass


async def test_get_custom_emoji_stickers_takes_string_ids():
    client = _EmojiClient([])

    await client.get_custom_emoji_stickers(["5368324170671202286", 7])

    query = client.queries[0]
    assert query.document_id == [5368324170671202286, 7]
    query.write()


class _SaveClient(SaveFile):
    save_file_semaphore = asyncio.Semaphore(1)


async def test_save_file_rejects_a_text_stream():
    with pytest.raises(ValueError, match="binary"):
        await _SaveClient().save_file(io.StringIO("hello"))


class _ToggleClient(
    _Recorder,
    ToggleSlowMode,
    ToggleViewForumAsMessages,
    TogglePreHistoryHidden,
    ToggleSignatures,
    ToggleAntiSpam,
    ToggleForum,
):
    pass


async def test_toggle_methods_return_true():
    client = _ToggleClient(raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0))
    client.peer = raw.types.InputPeerChannel(channel_id=1, access_hash=0)

    assert await client.toggle_slow_mode(-1001, 10) is True
    assert await client.toggle_view_forum_as_messages(-1001, True) is True
    assert await client.toggle_pre_history_hidden(-1001, True) is True
    assert await client.toggle_signatures(-1001, True, True) is True
    assert await client.toggle_anti_spam(-1001, True) is True
    assert await client.toggle_forum(-1001, True) is True


class _LinkClient(_Recorder, CreateChatInviteLink):
    pass


async def test_create_chat_invite_link_has_a_creator():
    client = _LinkClient(
        raw.types.ChatInviteExported(link="https://t.me/+x", admin_id=1, date=0)
    )
    client.peer = raw.types.InputPeerChannel(channel_id=1, access_hash=0)
    client.me = types.User(id=1, first_name="me")

    link = await client.create_chat_invite_link(-1001)

    assert link.creator is client.me


def _banned(until_date):
    return raw.types.ChannelParticipantBanned(
        peer=raw.types.PeerUser(user_id=2),
        kicked_by=1,
        date=0,
        banned_rights=raw.types.ChatBannedRights(until_date=until_date, view_messages=True),
    )


def test_chat_member_permanent_ban_has_no_until_date():
    users = {1: _raw_user(1), 2: _raw_user(2)}

    assert types.ChatMember._parse(None, _banned(2 ** 31 - 1), users, {}).until_date is None
    assert types.ChatMember._parse(None, _banned(1700000000), users, {}).until_date is not None


async def _event(action):
    return await types.ChatEvent._parse(
        None,
        raw.types.ChannelAdminLogEvent(id=1, date=0, user_id=1, action=action),
        [_raw_user(1), _raw_user(2)],
        [],
    )


async def test_chat_event_parses_new_actions():
    e = await _event(raw.types.ChannelAdminLogEventActionToggleNoForwards(new_value=True))
    assert e.action is enums.ChatEventAction.PROTECTED_CONTENT_ENABLED
    assert e.protected_content_enabled is True

    e = await _event(raw.types.ChannelAdminLogEventActionToggleForum(new_value=False))
    assert e.action is enums.ChatEventAction.FORUM_ENABLED
    assert e.forum_enabled is False

    e = await _event(raw.types.ChannelAdminLogEventActionToggleAntiSpam(new_value=True))
    assert e.action is enums.ChatEventAction.ANTI_SPAM_ENABLED
    assert e.anti_spam_enabled is True

    e = await _event(raw.types.ChannelAdminLogEventActionToggleSignatureProfiles(new_value=True))
    assert e.action is enums.ChatEventAction.SIGNATURE_PROFILES_ENABLED
    assert e.signature_profiles_enabled is True

    e = await _event(raw.types.ChannelAdminLogEventActionToggleAutotranslation(new_value=True))
    assert e.action is enums.ChatEventAction.AUTO_TRANSLATION_ENABLED
    assert e.auto_translation_enabled is True

    e = await _event(raw.types.ChannelAdminLogEventActionChangeUsernames(prev_value=["a"], new_value=["a", "b"]))
    assert e.action is enums.ChatEventAction.USERNAMES_CHANGED
    assert (e.old_usernames, e.new_usernames) == (["a"], ["a", "b"])

    e = await _event(raw.types.ChannelAdminLogEventActionChangeAvailableReactions(
        prev_value=raw.types.ChatReactionsNone(),
        new_value=raw.types.ChatReactionsAll(allow_custom=True),
    ))
    assert e.action is enums.ChatEventAction.AVAILABLE_REACTIONS_CHANGED
    assert e.new_available_reactions.all_are_enabled is True

    e = await _event(raw.types.ChannelAdminLogEventActionParticipantEditRank(user_id=2, prev_rank="a", new_rank="b"))
    assert e.action is enums.ChatEventAction.MEMBER_TAG_CHANGED
    assert (e.tagged_user.id, e.old_tag, e.new_tag) == (2, "a", "b")

    invite = raw.types.ChatInviteExported(link="https://t.me/+x", admin_id=1, date=0)

    e = await _event(raw.types.ChannelAdminLogEventActionParticipantJoinByInvite(invite=invite))
    assert e.action is enums.ChatEventAction.MEMBER_JOINED_BY_LINK
    assert e.invite_link.invite_link == "https://t.me/+x"

    e = await _event(raw.types.ChannelAdminLogEventActionParticipantJoinByRequest(invite=invite, approved_by=2))
    assert e.action is enums.ChatEventAction.MEMBER_JOINED_BY_REQUEST
    assert e.approver_user.id == 2

    e = await _event(raw.types.ChannelAdminLogEventActionPinTopic(new_topic=raw.types.ForumTopicDeleted(id=3)))
    assert e.action is enums.ChatEventAction.PINNED_FORUM_TOPIC
    assert e.new_forum_topic.id == 3


async def test_chat_event_unknown_action_is_the_enum_and_keeps_raw():
    action = raw.types.ChannelAdminLogEventActionToggleGroupCallSetting(join_muted=True)

    e = await _event(action)

    assert e.action is enums.ChatEventAction.UNKNOWN
    assert e.raw is action
