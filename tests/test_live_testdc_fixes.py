import asyncio
from types import FunctionType, SimpleNamespace

import pytest

import pyrogram
from pyrogram import enums, errors, raw, types
from pyrogram.methods.listeners.ask import Ask
from pyrogram.types.listeners import registry as registry_module

from tests.test_listeners import FakeClient, message

MESSAGE = enums.ListenerTypes.MESSAGE


def _client(answer, peers=None, me=None):
    client = pyrogram.Client("testdc-fixes", api_id=1, api_hash="a" * 32, in_memory=True)
    client.sent = []
    client.me = me

    async def invoke(query, *args, **kwargs):
        client.sent.append(query)
        return answer(query) if isinstance(answer, FunctionType) else answer

    async def resolve_peer(peer_id):
        return (peers or {}).get(peer_id, raw.types.InputPeerUser(user_id=5, access_hash=6))

    client.invoke = invoke
    client.resolve_peer = resolve_peer
    return client


def _updates(*updates):
    return raw.types.Updates(updates=list(updates), users=[], chats=[], date=0, seq=0)


BASIC = raw.types.InputPeerChat(chat_id=77)
CHANNEL = raw.types.InputPeerChannel(channel_id=88, access_hash=1)
BOT = raw.types.InputPeerUser(user_id=9, access_hash=2)


@pytest.mark.parametrize("privileges,is_admin", [
    (None, True),
    (types.ChatPrivileges(can_manage_chat=False, can_pin_messages=True), True),
    (types.ChatPrivileges(can_manage_chat=False), False),
])
async def test_a_basic_group_promotion_uses_the_basic_group_call(privileges, is_admin):
    client = _client(True, {-77: BASIC, 9: BOT})

    assert await client.promote_chat_member(-77, 9, privileges) is True

    [query] = client.sent
    assert isinstance(query, raw.functions.messages.EditChatAdmin)
    assert query.chat_id == 77
    assert query.user_id == BOT
    assert query.is_admin is is_admin


async def test_a_supergroup_promotion_still_edits_admin_rights():
    def answer(query):
        if isinstance(query, raw.functions.channels.GetParticipant):
            raise errors.UserNotParticipant()

        return _updates()

    client = _client(answer, {-10088: CHANNEL, 9: BOT})

    await client.promote_chat_member(-10088, 9, types.ChatPrivileges(can_pin_messages=True))

    assert isinstance(client.sent[-1], raw.functions.channels.EditAdmin)
    assert client.sent[-1].admin_rights.pin_messages is True


@pytest.mark.parametrize("is_bot,both_sides,pm_oneside", [
    (True, None, False),
    (False, None, True),
    (True, False, True),
    (False, True, False),
])
async def test_bots_pin_for_both_sides_unless_told_otherwise(is_bot, both_sides, pm_oneside):
    client = _client(_updates(), me=SimpleNamespace(is_bot=is_bot))

    await client.pin_chat_message(1, 2, both_sides=both_sides)

    assert client.sent[0].pm_oneside is pm_oneside


async def test_the_message_pin_shortcut_leaves_the_side_choice_to_the_client():
    client = _client(_updates(), me=SimpleNamespace(is_bot=True))
    msg = types.Message(id=2, chat=types.Chat(id=1), client=client)

    await msg.pin()

    assert client.sent[0].pm_oneside is False


@pytest.mark.parametrize("option", [
    "2",
    types.PollOption(persistent_id="2", text=types.FormattedText(text="c")),
])
async def test_a_poll_option_is_deleted_by_its_persistent_id(option):
    client = _client(_updates())

    await client.delete_poll_option(1, 2, option)

    assert client.sent[0].option == b"2"


def _sent_messages(*ids):
    return _updates(*[
        raw.types.UpdateNewMessage(
            message=raw.types.Message(id=i, peer_id=raw.types.PeerUser(user_id=5), date=0, message="m"),
            pts=0, pts_count=0,
        )
        for i in ids
    ])


@pytest.fixture
def parsed_by_id(monkeypatch):
    async def parse(client, message, users, chats, *args, **kwargs):
        return types.Message(id=message.id)

    monkeypatch.setattr(types.Message, "_parse", parse)


async def test_one_scheduled_message_sent_now_returns_that_message(parsed_by_id):
    client = _client(_sent_messages(5))

    result = await client.send_scheduled_messages("me", 5)

    assert client.sent[0].id == [5]
    assert result.id == 5


@pytest.mark.parametrize("ids", [[5, 6], (5, 6)])
async def test_several_scheduled_messages_sent_now_are_all_returned(parsed_by_id, ids):
    client = _client(_sent_messages(5, 6))

    result = await client.send_scheduled_messages("me", ids)

    assert client.sent[0].id == [5, 6]
    assert [m.id for m in result] == [5, 6]


@pytest.mark.parametrize("ids,sent", [(5, [5]), ([5, 6], [5, 6])])
async def test_translate_text_takes_one_id_or_a_list(ids, sent):
    client = _client(raw.types.messages.TranslateResult(result=[]))

    await client.translate_text("me", ids, to_lang="de")

    assert client.sent[0].id == sent


@pytest.mark.parametrize("error_id,error_class", [
    ("ADD_ANSWER_FORBIDDEN", errors.AddAnswerForbidden),
    ("BOOSTS_REQUIRED", errors.BoostsRequired),
    ("CONTACT_MISSING", errors.ContactMissing),
    ("DELETE_ANSWER_FORBIDDEN", errors.DeleteAnswerForbidden),
    ("DISCUSSION_CHAT_REQUIRED", errors.DiscussionChatRequired),
    ("FORUM_ENABLED", errors.ForumEnabled),
    ("GIFT_SLUG_EXPIRED", errors.GiftSlugExpired),
    ("INPUT_TEXT_TOO_LONG", errors.InputTextTooLong),
    ("PARENT_PEER_INVALID", errors.ParentPeerInvalid),
    ("RICH_MESSAGE_UNSUPPORTED", errors.RichMessageUnsupported),
    ("RIGHTS_NOT_MODIFIED", errors.RightsNotModified),
    ("SEND_AS_PEER_INVALID", errors.SendAsPeerInvalid),
])
def test_errors_seen_on_the_test_server_have_their_own_class(error_id, error_class):
    with pytest.raises(error_class):
        errors.RPCError.raise_it(
            raw.types.RpcError(error_code=400, error_message=error_id),
            raw.functions.Ping,
        )


class AskClient(FakeClient, Ask):
    def __init__(self, reply_during_send=True, fail_send=False):
        super().__init__()
        self.reply_during_send = reply_during_send
        self.fail_send = fail_send

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail_send:
            raise errors.PeerIdInvalid()

        if self.reply_during_send:
            await self.listeners.feed(self, MESSAGE, message(chat_id=chat_id, message_id=101))

        return SimpleNamespace(id=100, chat=SimpleNamespace(id=chat_id))


@pytest.fixture(autouse=True)
def fresh_budget():
    registry_module._budgets.clear()
    yield
    registry_module._budgets.clear()


async def test_ask_catches_a_reply_that_arrives_while_the_question_is_being_sent():
    client = AskClient()

    answer = await asyncio.wait_for(client.ask(1, "q", timeout=5), 5)

    assert answer.id == 101
    assert answer.sent_message.id == 100
    assert not client.listeners


async def test_ask_stops_listening_when_the_question_cannot_be_sent():
    client = AskClient(fail_send=True)

    with pytest.raises(errors.PeerIdInvalid):
        await client.ask(1, "q", timeout=5)

    assert not client.listeners
