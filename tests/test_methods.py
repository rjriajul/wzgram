import asyncio
import inspect
import io
import logging
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import pyrogram
from pyrogram import enums, raw, types, utils
from pyrogram.connection.transport.tcp.tcp import TCP
from pyrogram.filters import create
from pyrogram.methods.auth.terminate import Terminate
from pyrogram.methods.utilities.stop import Stop
from pyrogram.session import Session
from pyrogram.types import ListenerRegistry
from pyrogram.types.input_content import input_sticker


VIEW_ONCE_TTL = (1 << 31) - 1


class FakeClient:
    def __init__(self, answers=None):
        self.sent = []
        self.answers = list(answers or [])
        self.parse_mode = enums.ParseMode.DEFAULT
        self.sleep_threshold = 10

    async def invoke(self, query, *args, **kwargs):
        self.sent.append(query)

        if self.answers:
            return self.answers.pop(0)

        return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    async def resolve_peer(self, peer_id):
        if isinstance(peer_id, int) and peer_id < 0:
            return raw.types.InputPeerChannel(channel_id=-peer_id, access_hash=0)

        return raw.types.InputPeerUser(user_id=peer_id or 1, access_hash=0)

    async def save_file(self, *args, **kwargs):
        return raw.types.InputFile(id=1, parts=1, name="f", md5_checksum="")

    def guess_mime_type(self, name):
        return None

    def rnd_id(self):
        return 1


@pytest.fixture
def no_text(monkeypatch):
    async def parse_text_entities(client, text, parse_mode, entities):
        return {"message": text or "", "entities": None}

    async def get_reply_to(*args, **kwargs):
        return None

    monkeypatch.setattr(utils, "parse_text_entities", parse_text_entities)
    monkeypatch.setattr(utils, "get_reply_to", get_reply_to)


@pytest.mark.asyncio
async def test_a_view_once_photo_gets_the_ttl_that_means_view_once(tmp_path, no_text):
    client = FakeClient()
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")

    await pyrogram.Client.send_photo(client, 7, str(photo), view_once=True)

    assert client.sent[0].media.ttl_seconds == VIEW_ONCE_TTL


@pytest.mark.asyncio
async def test_a_voice_carries_its_waveform_and_ttl(tmp_path, no_text):
    client = FakeClient()
    voice = tmp_path / "v.ogg"
    voice.write_bytes(b"x")

    await pyrogram.Client.send_voice(
        client, 7, str(voice), waveform=b"\x01\x02", view_once=True
    )

    media = client.sent[0].media

    assert media.ttl_seconds == VIEW_ONCE_TTL
    assert media.attributes[0].waveform == b"\x01\x02"


@pytest.mark.asyncio
async def test_a_video_note_without_view_once_keeps_no_ttl(tmp_path, no_text):
    client = FakeClient()
    note = tmp_path / "n.mp4"
    note.write_bytes(b"x")

    await pyrogram.Client.send_video_note(client, 7, str(note))

    assert client.sent[0].media.ttl_seconds is None


@pytest.mark.asyncio
async def test_a_sticker_carries_its_emoji_and_caption(tmp_path, monkeypatch):
    client = FakeClient()
    sticker = tmp_path / "s.webp"
    sticker.write_bytes(b"x")

    async def parse_text_entities(client, text, parse_mode, entities):
        return {"message": text, "entities": None}

    async def get_reply_to(*args, **kwargs):
        return None

    monkeypatch.setattr(utils, "parse_text_entities", parse_text_entities)
    monkeypatch.setattr(utils, "get_reply_to", get_reply_to)

    await pyrogram.Client.send_sticker(
        client, 7, str(sticker), emoji="🔥", caption="hi"
    )

    query = client.sent[0]

    assert query.message == "hi"
    assert any(
        isinstance(a, raw.types.DocumentAttributeSticker) and a.alt == "🔥"
        for a in query.media.attributes
    )


@pytest.mark.asyncio
async def test_history_boundaries_reach_the_request(monkeypatch):
    client = FakeClient()

    async def parse_messages(client, messages, replies=1):
        return []

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    async for _ in pyrogram.Client.get_chat_history(
        client, 7, min_id=10, max_id=20, reverse=True
    ):
        pass

    query = client.sent[0]

    assert (query.min_id, query.max_id) == (9, 21)
    assert query.offset_id == 10


@pytest.mark.asyncio
async def test_a_reversed_chunk_comes_back_oldest_first(monkeypatch):
    from pyrogram.methods.messages import get_chat_history

    made = [types.Message(id=i) for i in (3, 2, 1)]

    async def parse_messages(client, messages, replies=1):
        return list(made)

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    messages = await get_chat_history.get_chunk(
        client=FakeClient(), chat_id=7, reverse=True
    )

    assert [m.id for m in messages] == [1, 2, 3]


@pytest.mark.asyncio
async def test_search_boundaries_reach_the_request(monkeypatch):
    client = FakeClient()

    async def parse_messages(client, messages, replies=1):
        return []

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    when = datetime(2026, 9, 1, tzinfo=timezone.utc)

    async for _ in pyrogram.Client.search_messages(
        client, 7, offset_id=5, min_id=1, max_id=9, min_date=when, max_date=when
    ):
        pass

    query = client.sent[0]

    assert (query.offset_id, query.min_id, query.max_id) == (5, 1, 9)
    assert query.min_date == query.max_date == utils.datetime_to_timestamp(when)


@pytest.mark.asyncio
async def test_the_pinned_message_is_asked_for_by_its_own_type(monkeypatch):
    client = FakeClient([raw.types.messages.Messages(
        messages=[], chats=[], users=[], topics=[]
    )])

    async def parse_messages(client, messages, replies=1, business_connection_id=None):
        return types.List()

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    await pyrogram.Client.get_messages(client, -7, pinned=True)

    assert isinstance(client.sent[0].id[0], raw.types.InputMessagePinned)


@pytest.mark.asyncio
async def test_the_archive_is_a_folder_id(monkeypatch):
    client = FakeClient([raw.types.messages.Dialogs(
        dialogs=[], messages=[], chats=[], users=[]
    )])

    async for _ in pyrogram.Client.get_dialogs(
        client, exclude_pinned=True, from_archive=True
    ):
        pass

    query = client.sent[0]

    assert (query.exclude_pinned, query.folder_id) == (True, 1)


@pytest.mark.asyncio
async def test_banning_can_also_drop_the_messages_and_the_reactions():
    client = FakeClient()

    await pyrogram.Client.ban_chat_member(
        client, -7, 9, revoke_messages=True, revoke_reactions=True
    )

    kinds = [type(q) for q in client.sent]

    assert raw.functions.channels.DeleteParticipantHistory in kinds
    assert raw.functions.messages.DeleteParticipantReactions in kinds


@pytest.mark.asyncio
async def test_a_chat_without_force_full_asks_for_the_short_one(monkeypatch):
    client = FakeClient([raw.types.messages.Chats(chats=[raw.types.ChatEmpty(id=7)])])
    client.INVITE_LINK_RE = pyrogram.Client.INVITE_LINK_RE

    def parse_chat(client, chat):
        return "short"

    monkeypatch.setattr(types.Chat, "_parse_chat", parse_chat)

    assert await pyrogram.Client.get_chat(client, -7, force_full=False) == "short"
    assert isinstance(client.sent[0], raw.functions.channels.GetChannels)


@pytest.mark.asyncio
async def test_an_emoji_status_for_a_channel_goes_to_the_channel_request():
    client = FakeClient([True])

    await pyrogram.Client.set_emoji_status(client, chat_id=-7)

    assert isinstance(client.sent[0], raw.functions.channels.UpdateEmojiStatus)

    client = FakeClient([True])

    await pyrogram.Client.set_emoji_status(client)

    assert isinstance(client.sent[0], raw.functions.account.UpdateEmojiStatus)


@pytest.mark.asyncio
async def test_a_recaptcha_token_wraps_the_query(monkeypatch):
    class Session:
        def __init__(self):
            self.query = None

        async def invoke(self, query, *args, **kwargs):
            self.query = query

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

    client = pyrogram.Client("t", in_memory=True, api_id=1, api_hash="x")
    client.is_connected = True
    client.session = Session()
    client.rate_limiter = None

    await pyrogram.Client.invoke(
        client, raw.functions.help.GetConfig(), recaptcha_token="tok"
    )

    assert isinstance(client.session.query, raw.functions.InvokeWithReCaptcha)
    assert client.session.query.token == "tok"


@pytest.mark.asyncio
async def test_a_video_is_view_once_too(tmp_path, no_text):
    client = FakeClient()
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    await pyrogram.Client.send_video(client, 7, str(video), view_once=True)

    assert client.sent[0].media.ttl_seconds == VIEW_ONCE_TTL


@pytest.mark.asyncio
async def test_gaps_are_recovered_only_for_the_chats_asked_for(monkeypatch):
    class Storage:
        async def update_state(self, value=None):
            if value is not None:
                return None

            return [(0, 1, 1, 1, 1), (-100, 1, 1, 1, 1)]

    class Client(FakeClient):
        skip_updates = False
        storage = Storage()
        _save_update_state = pyrogram.Client._save_update_state
        _state_marks = {}

    client = Client([raw.types.updates.DifferenceEmpty(date=0, seq=0)])

    await pyrogram.Client.recover_gaps(client, ids=[0])

    assert isinstance(client.sent[0], raw.functions.updates.GetDifference)
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_no_matching_chat_recovers_nothing():
    class Storage:
        async def update_state(self, value=None):
            return [(0, 1, 1, 1, 1)] if value is None else None

    class Client(FakeClient):
        skip_updates = False
        storage = Storage()
        _save_update_state = pyrogram.Client._save_update_state
        _state_marks = {}

    client = Client()

    assert await pyrogram.Client.recover_gaps(client, ids=[-999]) == (0, 0)
    assert client.sent == []


@pytest.mark.asyncio
async def test_stopping_can_keep_the_handlers():
    seen = {}

    class Dispatcher:
        async def stop(self, clear_handlers=True):
            seen["clear_handlers"] = clear_handlers

    client = pyrogram.Client("t", in_memory=True, api_id=1, api_hash="x")
    client.is_initialized = True
    client.dispatcher = Dispatcher()

    await client.storage.open()
    await pyrogram.Client.terminate(client, clear_handlers=False)

    assert seen["clear_handlers"] is False


def test_a_raw_update_decorator_carries_its_filters():
    handlers = []

    class Client(pyrogram.Client):
        def add_handler(self, handler, group):
            handlers.append((handler, group))

    client = Client.__new__(Client)
    wanted = create(lambda *args: True)

    @pyrogram.Client.on_raw_update(client, wanted, group=3)
    def handler(*args):
        pass

    assert handlers[0][0].filters is wanted
    assert handlers[0][1] == 3


@pytest.mark.asyncio
async def test_a_contact_note_is_sent_as_formatted_text(monkeypatch):
    client = FakeClient([raw.types.contacts.ImportedContacts(
        imported=[], popular_invites=[], retry_contacts=[],
        users=[raw.types.UserEmpty(id=7)]
    )])

    async def write(self, client):
        return raw.types.TextWithEntities(text=self.text, entities=[])

    monkeypatch.setattr(types.FormattedText, "write", write)
    monkeypatch.setattr(types.User, "_parse", staticmethod(lambda *a: None))

    await pyrogram.Client.add_contact(client, 7, "Foo", note="a note")

    assert client.sent[0].note.text == "a note"


@pytest.mark.asyncio
async def test_a_public_profile_photo_is_the_fallback_one(tmp_path):
    client = FakeClient([True])
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")

    await pyrogram.Client.set_profile_photo(client, photo=str(photo), is_public=True)

    assert client.sent[0].fallback is True


@pytest.mark.asyncio
async def test_a_supergroup_can_be_born_a_forum(monkeypatch):
    client = FakeClient([raw.types.Updates(
        updates=[], users=[], chats=[raw.types.ChatEmpty(id=1)], date=0, seq=0
    )])

    monkeypatch.setattr(types.Chat, "_parse_chat", lambda *a: None)

    await pyrogram.Client.create_supergroup(
        client, "t", is_forum=True, message_auto_delete_time=60, for_import=True
    )

    query = client.sent[0]

    assert (query.forum, query.ttl_period, query.for_import) == (True, 60, True)


@pytest.mark.asyncio
async def test_an_edited_caption_can_be_scheduled(monkeypatch):
    seen = {}

    class Client(FakeClient):
        async def edit_message_text(self, **kwargs):
            seen.update(kwargs)

    when = datetime(2026, 9, 1, tzinfo=timezone.utc)

    await pyrogram.Client.edit_message_caption(Client(), 7, 1, "c", schedule_date=when)

    assert seen["schedule_date"] is when


@pytest.mark.asyncio
async def test_edited_media_carries_the_schedule_and_the_caption_side(tmp_path):
    client = FakeClient()
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")

    client.answers = [
        raw.types.MessageMediaPhoto(
            photo=raw.types.Photo(
                id=1, access_hash=1, file_reference=b"", date=0, sizes=[], dc_id=1
            )
        ),
        raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0),
    ]

    class Parser:
        async def parse(self, text, parse_mode=None):
            return {"message": text or "", "entities": None}

    client.parser = Parser()

    await pyrogram.Client.edit_message_media(
        client, 7, 1, types.InputMediaPhoto(str(photo)),
        schedule_date=when, show_caption_above_media=True
    )

    query = client.sent[-1]

    assert isinstance(query, raw.functions.messages.EditMessage)
    assert query.schedule_date == utils.datetime_to_timestamp(when)
    assert query.invert_media is True


@pytest.mark.asyncio
async def test_a_screenshot_notification_can_reply_through_parameters(monkeypatch):
    client = FakeClient()

    async def get_reply_to(client, reply_parameters, *args, **kwargs):
        return raw.types.InputReplyToMessage(
            reply_to_msg_id=reply_parameters.message_id
        )

    monkeypatch.setattr(utils, "get_reply_to", get_reply_to)

    await pyrogram.Client.send_screenshot_notification(
        client, 7, reply_parameters=types.ReplyParameters(message_id=11)
    )

    assert client.sent[0].reply_to.reply_to_msg_id == 11


@pytest.mark.asyncio
async def test_an_ephemeral_edit_can_point_at_a_link_preview(monkeypatch):
    client = FakeClient()

    async def parse_text_entities(client, text, parse_mode, entities):
        return {"message": text, "entities": None}

    monkeypatch.setattr(utils, "parse_text_entities", parse_text_entities)

    await pyrogram.Client.edit_ephemeral_message_text(
        client, 7, 8, 9, "hi",
        link_preview_options=types.LinkPreviewOptions(
            url="https://example.com", prefer_large_media=True
        )
    )

    media = client.sent[0].media

    assert isinstance(media, raw.types.InputMediaWebPage)
    assert media.url == "https://example.com"
    assert media.force_large_media is True


@pytest.mark.asyncio
async def test_a_block_document_lands_in_the_document_vector():
    class Uploading(FakeClient):
        async def invoke(self, query, *args, **kwargs):
            self.sent.append(query)

            return raw.types.MessageMediaDocument(
                document=raw.types.Document(
                    id=222, access_hash=1, file_reference=b"fr", date=0,
                    mime_type="application/pdf", size=1, dc_id=2, attributes=[]
                )
            )

        async def save_file(self, *args, **kwargs):
            return raw.types.InputFile(id=1, parts=1, name="f.pdf", md5_checksum="")

    client = Uploading()

    message = types.InputRichMessage(
        blocks=[types.InputRichBlockDocument(document=types.InputMediaDocument("README.md"))]
    )

    written = await utils.build_input_rich_message(client, message)

    assert written.blocks[0].document_id == 222
    assert [d.id for d in written.documents] == [222]
    assert written.photos is None


@pytest.mark.asyncio
async def test_a_login_code_carries_the_recaptcha_token(monkeypatch):
    seen = {}

    class Client(FakeClient):
        phone_number = "+100"
        api_id = 1
        api_hash = "x"
        app_version = "x"
        device_model = "x"
        system_version = "x"
        lang_code = "en"
        lang_pack = ""
        system_lang_code = "en"

        async def invoke(self, query, *args, **kwargs):
            seen["token"] = kwargs.get("recaptcha_token")

            return raw.types.auth.SentCode(
                type=raw.types.auth.SentCodeTypeApp(length=5),
                phone_code_hash="h"
            )

    monkeypatch.setattr(types.SentCode, "_parse", staticmethod(lambda r: r))

    await pyrogram.Client.send_phone_number_code(
        Client(), "+100", recaptcha_token="tok"
    )

    assert seen["token"] == "tok"


@pytest.mark.parametrize(
    "block,field,kwarg",
    [
        ("InputRichBlockVideo", "video_id", "video"),
        ("InputRichBlockAnimation", "video_id", "animation"),
        ("InputRichBlockAudio", "audio_id", "audio"),
        ("InputRichBlockVoiceNote", "audio_id", "voice"),
    ],
)
@pytest.mark.asyncio
async def test_every_document_block_uploads_what_it_was_given(block, field, kwarg):
    class Uploading(FakeClient):
        async def invoke(self, query, *args, **kwargs):
            self.sent.append(query)

            return raw.types.MessageMediaDocument(
                document=raw.types.Document(
                    id=333, access_hash=1, file_reference=b"fr", date=0,
                    mime_type="video/mp4", size=1, dc_id=2, attributes=[]
                )
            )

        async def save_file(self, *args, **kwargs):
            return raw.types.InputFile(id=1, parts=1, name="f", md5_checksum="")

    client = Uploading()

    message = types.InputRichMessage(
        blocks=[
            getattr(types, block)(**{kwarg: types.InputMediaDocument("README.md")})
        ]
    )

    written = await utils.build_input_rich_message(client, message)

    assert getattr(written.blocks[0], field) == 333
    assert [d.id for d in written.documents] == [333]


def _reply_markup_on_the_wire(client: FakeClient) -> raw.base.ReplyMarkup | None:
    """The captured request's `reply_markup`, read back from the bytes it serializes to."""
    assert client.sent
    payload = BytesIO(client.sent[0].write()[4:])
    return raw.functions.messages.EditMessage.read(payload).reply_markup


@pytest.mark.asyncio
async def test_not_passing_a_reply_markup_leaves_the_field_out_of_the_request():
    client = FakeClient()
    await pyrogram.Client.edit_message_reply_markup(client, chat_id=7, message_id=11)
    assert _reply_markup_on_the_wire(client) is None


@pytest.mark.asyncio
async def test_passing_none_leaves_the_field_out_of_the_request():
    client = FakeClient()
    await pyrogram.Client.edit_message_reply_markup(client, chat_id=7, message_id=11, reply_markup=None)
    assert _reply_markup_on_the_wire(client) is None


@pytest.mark.asyncio
async def test_passing_a_markup_sends_its_buttons():
    client = FakeClient()
    await pyrogram.Client.edit_message_reply_markup(
        client,
        chat_id=7,
        message_id=11,
        reply_markup=types.InlineKeyboardMarkup(
            [[types.InlineKeyboardButton("New button", callback_data="new_data")]]
        ),
    )
    sent = _reply_markup_on_the_wire(client)
    assert isinstance(sent, raw.types.ReplyInlineMarkup)
    assert [button.text for row in sent.rows for button in row.buttons] == ["New button"]


class NewClientMethodsFakeClient:
    def __init__(self, answers=None):
        self.sent = []
        self.answers = list(answers or [])

    async def invoke(self, query, *args, **kwargs):
        self.sent.append(query)

        if self.answers:
            return self.answers.pop(0)

        return None

    async def resolve_peer(self, peer_id):
        return raw.types.InputPeerUser(user_id=peer_id, access_hash=0)

    def rnd_id(self):
        return 1


def posts(count=None, messages=()):
    if count is None:
        return raw.types.messages.Messages(
            messages=list(messages), chats=[], users=[], topics=[]
        )

    return raw.types.messages.MessagesSlice(
        count=count, messages=list(messages), chats=[], users=[], topics=[]
    )


@pytest.mark.asyncio
async def test_a_paid_reaction_carries_the_star_count():
    client = NewClientMethodsFakeClient()

    assert await pyrogram.Client.send_paid_reaction(client, 7, 11, 5) is True

    query = client.sent[0]

    assert isinstance(query, raw.functions.messages.SendPaidReaction)
    assert (query.msg_id, query.count) == (11, 5)
    assert query.private is None


@pytest.mark.asyncio
async def test_an_anonymous_paid_reaction_says_so():
    client = NewClientMethodsFakeClient()

    await pyrogram.Client.send_paid_reaction(
        client, 7, 11, 1, privacy=enums.PaidReactionPrivacy.ANONYMOUS
    )

    assert isinstance(client.sent[0].private, raw.types.PaidReactionPrivacyAnonymous)


@pytest.mark.asyncio
async def test_a_paid_reaction_as_a_chat_needs_that_chat():
    client = NewClientMethodsFakeClient()

    with pytest.raises(ValueError):
        await pyrogram.Client.send_paid_reaction(
            client, 7, 11, 1, privacy=enums.PaidReactionPrivacy.CHAT
        )

    await pyrogram.Client.send_paid_reaction(
        client, 7, 11, 1, privacy=enums.PaidReactionPrivacy.CHAT, send_as=99
    )

    assert isinstance(client.sent[0].private, raw.types.PaidReactionPrivacyPeer)


@pytest.mark.asyncio
async def test_searching_posts_counts_without_fetching_them():
    client = NewClientMethodsFakeClient([posts(count=42)])

    assert await pyrogram.Client.search_posts_count(client, "#wzgram") == 42

    query = client.sent[0]

    assert isinstance(query, raw.functions.channels.SearchPosts)
    assert query.hashtag == "wzgram"
    assert query.limit == 1


@pytest.mark.asyncio
async def test_counting_posts_falls_back_to_the_messages_it_got():
    client = NewClientMethodsFakeClient([posts(messages=[])])

    assert await pyrogram.Client.search_posts_count(client, query="wzgram") == 0
    assert client.sent[0].query == "wzgram"


@pytest.mark.asyncio
async def test_a_post_search_needs_something_to_search_for():
    with pytest.raises(ValueError):
        await pyrogram.Client.search_posts_count(NewClientMethodsFakeClient())

    with pytest.raises(ValueError):
        async for _ in pyrogram.Client.search_posts(NewClientMethodsFakeClient()):
            pass


@pytest.mark.asyncio
async def test_a_post_search_stops_at_the_limit(monkeypatch):
    from pyrogram import utils

    made = [
        types.Message(id=i, chat=types.Chat(id=-100, type=enums.ChatType.CHANNEL))
        for i in range(1, 4)
    ]

    async def parse_messages(client, messages, replies=1):
        return made

    monkeypatch.setattr(utils, "parse_messages", parse_messages)

    client = NewClientMethodsFakeClient([posts(messages=made), posts(messages=made)])
    seen = [m async for m in pyrogram.Client.search_posts(client, "wzgram", limit=2)]

    assert [m.id for m in seen] == [1, 2]
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_gift_colors_are_sent_as_a_collectible():
    client = NewClientMethodsFakeClient([True])

    assert await pyrogram.Client.set_upgraded_gift_colors(client, 123) is True

    query = client.sent[0]

    assert isinstance(query, raw.functions.account.UpdateColor)
    assert isinstance(query.color, raw.types.InputPeerColorCollectible)
    assert query.color.collectible_id == 123


@pytest.mark.asyncio
async def test_a_live_photo_sends_the_media_the_type_built(monkeypatch):
    built = raw.types.InputMediaEmpty()

    async def write(self, **kwargs):
        return built

    monkeypatch.setattr(types.InputMediaLivePhoto, "write", write)

    from pyrogram import utils

    async def parse_text_entities(client, text, parse_mode, entities):
        return {"message": text, "entities": None}

    monkeypatch.setattr(utils, "parse_text_entities", parse_text_entities)

    async def get_reply_to(*args, **kwargs):
        return None

    monkeypatch.setattr(utils, "get_reply_to", get_reply_to)

    client = NewClientMethodsFakeClient([raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)])

    await pyrogram.Client.send_live_photo(client, 7, "clip.mp4", "still.jpg", caption="hi")

    query = client.sent[0]

    assert isinstance(query, raw.functions.messages.SendMedia)
    assert query.media is built
    assert query.message == "hi"


class _Recorder:
    def __init__(self, result=True):
        self.calls = []
        self.result = result

    async def invoke(self, query, *args, **kwargs):
        self.calls.append(query)
        return self.result


async def test_reorder_folders_inserts_the_main_list_and_leaves_the_argument_alone():
    from pyrogram.methods.chats.reorder_folders import ReorderFolders

    class _Client(_Recorder, ReorderFolders):
        pass

    client = _Client()
    folder_ids = [2, 5, 4]

    await client.reorder_folders(folder_ids, main_chat_list_position=1)

    assert client.calls[0].order == [2, 0, 5, 4]
    assert folder_ids == [2, 5, 4]


async def test_reorder_folders_keeps_the_order_when_the_main_list_is_first():
    from pyrogram.methods.chats.reorder_folders import ReorderFolders

    class _Client(_Recorder, ReorderFolders):
        pass

    client = _Client()

    await client.reorder_folders([2, 5])

    assert client.calls[0].order == [2, 5]


async def test_toggle_folder_tags_passes_the_flag_through():
    from pyrogram.methods.chats.toggle_folder_tags import ToggleFolderTags

    class _Client(_Recorder, ToggleFolderTags):
        pass

    client = _Client()

    await client.toggle_folder_tags(False)

    assert client.calls[0].enabled is False


async def test_set_chat_member_tag_clears_the_tag_with_an_empty_rank():
    from pyrogram.methods.chats.set_chat_member_tag import SetChatMemberTag

    class _Client(_Recorder, SetChatMemberTag):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerUser(user_id=1, access_hash=0)

    client = _Client()

    assert await client.set_chat_member_tag(-5, 1) is True
    assert client.calls[0].rank == ""


async def test_set_chat_discussion_group_needs_at_least_one_chat():
    from pyrogram.methods.chats.set_chat_discussion_group import SetChatDiscussionGroup

    class _Client(_Recorder, SetChatDiscussionGroup):
        async def resolve_peer(self, peer_id):
            raise AssertionError("must not resolve anything")

    with pytest.raises(ValueError):
        await _Client().set_chat_discussion_group()


async def test_set_chat_discussion_group_unlinks_with_an_empty_channel():
    from pyrogram.methods.chats.set_chat_discussion_group import SetChatDiscussionGroup

    class _Client(_Recorder, SetChatDiscussionGroup):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

    client = _Client()

    await client.set_chat_discussion_group(chat_id="@channel")

    assert isinstance(client.calls[0].broadcast, raw.types.InputPeerChannel)
    assert isinstance(client.calls[0].group, raw.types.InputChannelEmpty)


async def test_set_chat_discussion_group_rejects_a_user():
    from pyrogram.methods.chats.set_chat_discussion_group import SetChatDiscussionGroup

    class _Client(_Recorder, SetChatDiscussionGroup):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerUser(user_id=1, access_hash=0)

    with pytest.raises(ValueError):
        await _Client().set_chat_discussion_group("@user", "@group")


async def test_set_chat_direct_messages_group_sends_the_star_price():
    from pyrogram.methods.chats.set_chat_direct_messages_group import SetChatDirectMessagesGroup

    class _Client(_Recorder, SetChatDirectMessagesGroup):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

    client = _Client()

    await client.set_chat_direct_messages_group(-100, 25, is_enabled=True)

    assert client.calls[0].send_paid_messages_stars == 25
    assert client.calls[0].broadcast_messages_allowed is True


async def test_set_main_profile_tab_splits_account_from_channel():
    from pyrogram.methods.chats.set_main_profile_tab import SetMainProfileTab

    class _Me(_Recorder, SetMainProfileTab):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

    class _Channel(_Recorder, SetMainProfileTab):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

    me = _Me()
    channel = _Channel()

    await me.set_main_profile_tab("me", enums.ProfileTab.GIFTS)
    await channel.set_main_profile_tab("@channel", enums.ProfileTab.GIFTS)

    assert isinstance(me.calls[0], raw.functions.account.SetMainProfileTab)
    assert isinstance(me.calls[0].tab, raw.types.ProfileTabGifts)
    assert isinstance(channel.calls[0], raw.functions.channels.SetMainProfileTab)


async def test_set_chat_accent_color_uses_the_account_request_for_yourself():
    from pyrogram.methods.chats.set_chat_accent_color import SetChatAccentColor

    class _Client(_Recorder, SetChatAccentColor):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

    client = _Client()

    await client.set_chat_accent_color("me", 5, for_profile=True)

    assert isinstance(client.calls[0], raw.functions.account.UpdateColor)
    assert client.calls[0].color.color == 5
    assert client.calls[0].for_profile is True


async def test_set_chat_accent_color_clears_the_color_when_nothing_is_given():
    from pyrogram.methods.chats.set_chat_accent_color import SetChatAccentColor

    class _Client(_Recorder, SetChatAccentColor):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerSelf()

    client = _Client()

    await client.set_chat_accent_color("me")

    assert client.calls[0].color is None


async def test_set_chat_accent_color_uses_the_channel_request_for_a_channel():
    from pyrogram.methods.chats.set_chat_accent_color import SetChatAccentColor

    class _Client(_Recorder, SetChatAccentColor):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

    client = _Client(raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0))

    await client.set_chat_accent_color("@channel", 5)

    assert isinstance(client.calls[0], raw.functions.channels.UpdateColor)
    assert client.calls[0].color == 5


async def test_set_chat_accent_color_rejects_another_user():
    from pyrogram.methods.chats.set_chat_accent_color import SetChatAccentColor

    class _Client(_Recorder, SetChatAccentColor):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerUser(user_id=1, access_hash=0)

    with pytest.raises(ValueError):
        await _Client().set_chat_accent_color("@user", 5)


async def test_transfer_chat_ownership_rejects_a_chat_that_is_not_a_channel():
    from pyrogram.methods.chats.transfer_chat_ownership import TransferChatOwnership

    class _Client(_Recorder, TransferChatOwnership):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChat(chat_id=5)

    with pytest.raises(ValueError):
        await _Client().transfer_chat_ownership(-5, 1, "password")


async def test_transfer_chat_ownership_accepts_your_own_account_as_the_new_owner():
    from pyrogram.methods.chats.transfer_chat_ownership import TransferChatOwnership

    class _Client(_Recorder, TransferChatOwnership):
        async def resolve_peer(self, peer_id):
            if peer_id == "me":
                return raw.types.InputPeerSelf()
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

        async def invoke(self, query, *args, **kwargs):
            self.calls.append(query)

            if isinstance(query, raw.functions.account.GetPassword):
                raise RuntimeError("reached the password step")

            return True

    with pytest.raises(RuntimeError, match="reached the password step"):
        await _Client().transfer_chat_ownership(-100, "me", "password")


async def test_transfer_chat_ownership_rejects_a_new_owner_that_is_not_a_user():
    from pyrogram.methods.chats.transfer_chat_ownership import TransferChatOwnership

    class _Client(_Recorder, TransferChatOwnership):
        async def resolve_peer(self, peer_id):
            return raw.types.InputPeerChannel(channel_id=7, access_hash=0)

    with pytest.raises(ValueError):
        await _Client().transfer_chat_ownership(-100, "@channel", "password")


class StartBotAndBotPhotoFakeClient:
    def __init__(self, result=True):
        self.sent = None
        self.result = result
        self.messages = []
        self.saved = []
        self.me = Mock(id=999, is_bot=False, is_premium=False)
        self.message_cache = {}
        self.parse_mode = None

    async def invoke(self, query, **kwargs):
        self.sent = query
        return self.result

    async def resolve_peer(self, chat_id):
        return raw.types.InputPeerUser(user_id=777, access_hash=42)

    async def save_file(self, path, *args, **kwargs):
        if path is None:
            return None

        self.saved.append(path)
        return raw.types.InputFile(id=1, parts=1, name=str(path), md5_checksum="")

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.messages.append((chat_id, text))
        return "sent"

    def rnd_id(self):
        return 12345

    async def start_bot(self, chat_id, param=""):
        return await pyrogram.Client.start_bot(self, chat_id, param)

    async def set_bot_profile_photo(self, bot_user_id, **kwargs):
        return await pyrogram.Client.set_bot_profile_photo(self, bot_user_id, **kwargs)


@pytest.fixture
def client():
    return StartBotAndBotPhotoFakeClient()


def bot_user():
    return raw.types.User(
        id=777, first_name="Bot", bot=True, usernames=[], restriction_reason=[],
        access_hash=42
    )


def updates(*update_list):
    return raw.types.Updates(
        updates=list(update_list), users=[bot_user()], chats=[], date=0, seq=0
    )


def raw_message(message_id=55):
    return raw.types.Message(
        id=message_id,
        peer_id=raw.types.PeerUser(user_id=777),
        from_id=raw.types.PeerUser(user_id=777),
        date=1700000000,
        restriction_reason=[],
        message="hi",
        entities=[],
    )


async def test_start_bot_without_a_param_sends_the_plain_command(client):
    assert await client.start_bot("wzgrambot") == "sent"
    assert client.messages == [("wzgrambot", "/start")]
    assert client.sent is None


async def test_start_bot_with_a_param_invokes_start_bot(client):
    client.result = updates()

    await client.start_bot("wzgrambot", "ref123456")

    assert isinstance(client.sent, raw.functions.messages.StartBot)
    assert client.sent.start_param == "ref123456"
    assert client.sent.random_id == 12345
    assert client.sent.bot == client.sent.peer
    assert client.sent.bot.user_id == 777
    assert not client.messages


async def test_start_bot_returns_the_message_the_server_sent(client):
    client.result = updates(
        raw.types.UpdateNewMessage(message=raw_message(), pts=1, pts_count=1)
    )

    message = await client.start_bot("wzgrambot", "ref123456")

    assert isinstance(message, types.Message)
    assert message.id == 55


async def test_start_bot_returns_none_when_no_message_arrives(client):
    client.result = updates(
        raw.types.UpdateMessageID(id=1, random_id=12345)
    )

    assert await client.start_bot("wzgrambot", "ref123456") is None


async def test_set_bot_profile_photo_uploads_a_photo_for_that_bot(client):
    assert await client.set_bot_profile_photo("wzgrambot", photo="new.jpg") is True

    assert isinstance(client.sent, raw.functions.photos.UploadProfilePhoto)
    assert client.sent.bot.user_id == 777
    assert client.sent.file is not None
    assert client.sent.video is None
    assert client.saved == ["new.jpg"]


async def test_set_bot_profile_photo_uploads_a_video_for_that_bot(client):
    assert await client.set_bot_profile_photo("wzgrambot", video="new.mp4") is True

    assert isinstance(client.sent, raw.functions.photos.UploadProfilePhoto)
    assert client.sent.file is None
    assert client.sent.video is not None
    assert client.saved == ["new.mp4"]


async def test_set_bot_profile_photo_with_neither_removes_the_photo(client):
    assert await client.set_bot_profile_photo("wzgrambot") is True

    assert isinstance(client.sent, raw.functions.photos.UpdateProfilePhoto)
    assert isinstance(client.sent.id, raw.types.InputPhotoEmpty)
    assert client.sent.bot.user_id == 777
    assert client.saved == []


async def test_removing_a_bot_photo_never_uploads_anything(client):
    await client.set_bot_profile_photo("wzgrambot")

    assert not hasattr(client.sent, "file")


class InvoiceAndForumFakeClient:
    test_mode = False

    def __init__(self):
        self.sent = None

    async def invoke(self, query, **kwargs):
        self.sent = query
        return True

    async def resolve_peer(self, chat_id):
        return raw.types.InputPeerChannel(channel_id=chat_id, access_hash=0)

    async def pin_forum_topic(self, chat_id, topic_id):
        return await pyrogram.Client.pin_forum_topic(self, chat_id, topic_id)

    async def unpin_forum_topic(self, chat_id, topic_id):
        return await pyrogram.Client.unpin_forum_topic(self, chat_id, topic_id)


@pytest.fixture
def client_invoice_and_forum():
    return InvoiceAndForumFakeClient()


def invoice_content(**kwargs):
    return types.InputInvoiceMessageContent(
        title="t", description="d", payload="p", currency="XTR",
        prices=[types.LabeledPrice("one star", 7)], **kwargs
    )


async def test_an_invoice_photo_without_sizes_still_serialises():
    content = invoice_content(photo_url="https://example.org/a.jpg")

    written = await content.write(InvoiceAndForumFakeClient(), None)

    assert bytes(written.write())
    assert written.photo.size == 0
    assert written.photo.attributes[0].w == 0
    assert written.photo.attributes[0].h == 0


async def test_given_photo_sizes_are_kept():
    content = invoice_content(
        photo_url="https://example.org/a.jpg", photo_size=1024,
        photo_width=64, photo_height=48)

    written = await content.write(InvoiceAndForumFakeClient(), None)

    assert written.photo.size == 1024
    assert written.photo.attributes[0].w == 64
    assert written.photo.attributes[0].h == 48


def test_a_total_amount_is_derived_from_the_prices():
    raw_invoice = raw.types.Invoice(
        currency="XTR",
        prices=[raw.types.LabeledPrice(label="a", amount=7),
                raw.types.LabeledPrice(label="b", amount=3)],
    )

    invoice = types.Invoice._parse(None, raw_invoice)

    assert invoice.total_amount == 10
    assert [price.amount for price in invoice.prices] == [7, 3]


def test_a_reported_total_amount_wins():
    raw_invoice = raw.types.MessageMediaInvoice(
        title="t", description="d", currency="XTR", total_amount=99, start_param="")

    invoice = types.Invoice._parse(None, raw_invoice)

    assert invoice.total_amount == 99


async def test_pinning_a_topic_asks_the_server_to_pin(client_invoice_and_forum):
    assert await client_invoice_and_forum.pin_forum_topic(-100123, 7) is True
    assert isinstance(client_invoice_and_forum.sent, raw.functions.messages.UpdatePinnedForumTopic)
    assert client_invoice_and_forum.sent.topic_id == 7
    assert client_invoice_and_forum.sent.pinned is True


async def test_unpinning_a_topic_asks_the_server_to_unpin(client_invoice_and_forum):
    assert await client_invoice_and_forum.unpin_forum_topic(-100123, 7) is True
    assert client_invoice_and_forum.sent.pinned is False


def raw_set(set_id, name="set"):
    return raw.types.StickerSet(
        id=set_id,
        access_hash=1,
        title=name,
        short_name=name,
        count=0,
        hash=0,
    )


class OwnedClient:
    def __init__(self, pages):
        self.pages = pages
        self.sent = []

    async def invoke(self, query):
        self.sent.append(query)
        page = self.pages[min(len(self.sent), len(self.pages)) - 1]

        return raw.types.messages.MyStickers(
            count=page[0],
            sets=[raw.types.StickerSetNoCovered(set=raw_set(i, f"s{i}")) for i in page[1]],
        )


async def owned(client, **kwargs):
    return [s.id async for s in pyrogram.Client.get_owned_sticker_sets(client, **kwargs)]


@pytest.mark.asyncio
async def test_owned_sets_stop_when_telegram_repeats_the_page():
    client = OwnedClient([(250, list(range(100)))])

    assert await owned(client) == list(range(100))
    assert len(client.sent) == 2


@pytest.mark.asyncio
async def test_owned_sets_page_forward_and_stop_at_the_count():
    client = OwnedClient([(3, [1, 2]), (3, [2, 3]), (3, [3])])

    assert await owned(client, limit=0) == [1, 2]

    client = OwnedClient([(250, list(range(100))), (250, list(range(100, 200))), (250, list(range(200, 250)))])

    assert await owned(client) == list(range(250))
    assert len(client.sent) == 3


@pytest.mark.asyncio
async def test_a_set_without_stickers_parses():
    sticker_set = await types.StickerSet._parse(
        None,
        raw.types.messages.StickerSet(set=raw_set(9, "empty"), packs=[], keywords=[], documents=[]),
    )

    assert sticker_set.stickers == []
    assert sticker_set.thumbs is None
    assert sticker_set.link == "https://t.me/addstickers/empty"


def test_mask_position_writes_back_what_it_read():
    coords = raw.types.MaskCoords(n=2, x=0.5, y=-1.0, zoom=2.0)
    written = types.MaskPosition._parse(coords).write()

    assert (written.n, written.x, written.y, written.zoom) == (2, 0.5, -1.0, 2.0)


def test_urls_and_files_are_uploaded_and_anything_else_is_a_file_id(tmp_path):
    local = tmp_path / "s.png"
    local.write_bytes(b"x")

    def sticker(value):
        return types.InputSticker(value, enums.StickerFormat.STATIC, ["👍"])

    assert sticker("https://example.com/s.png")._is_upload()
    assert sticker(str(local))._is_upload()
    assert sticker(io.BytesIO(b"x"))._is_upload()
    assert not sticker("CAACAgQAAx")._is_upload()
    assert not sticker("ftp://example.com/s.png")._is_url()


def test_a_download_over_the_cap_is_refused(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(input_sticker, "MAX_DOWNLOAD_SIZE", 4)
    monkeypatch.setattr(input_sticker.urllib.request, "urlopen", lambda *a, **k: Response(b"12345"))

    with pytest.raises(ValueError):
        types.InputSticker._download("https://example.com/s.png")

    monkeypatch.setattr(input_sticker.urllib.request, "urlopen", lambda *a, **k: Response(b"1234"))

    assert types.InputSticker._download("https://example.com/s.png") == b"1234"


class FakeSession:
    MAX_RETRIES = 10

    def __init__(self, *args, **kwargs):
        self.auth_key = args[2]
        self.is_media = kwargs.get("is_media", False)
        self.is_started = asyncio.Event()
        self.stopped = False

    async def start(self, *args, **kwargs):
        self.is_started.set()

    async def stop(self):
        self.stopped = True
        self.is_started.clear()

    async def invoke(self, *args, **kwargs):
        return None


class FakeAuth:
    def __init__(self, *args, **kwargs):
        pass

    async def create(self):
        return b"fresh-key"


class TerminateSessionsFakeClient(Terminate):
    get_session = pyrogram.Client.get_session

    def __init__(self):
        self.is_initialized = True
        self.takeout_id = None
        self.ipv6 = False
        self.crypto_executor = None
        self.rate_limiter = None
        self.executor = None
        self.business_connections = {}
        self.sessions = {}
        self.media_sessions = {}
        self.media_session_pools = {}
        self._session_locks = {}
        self._media_sessions_locks = {}
        self._session_creation_gate = asyncio.Semaphore(4)
        self.updates_watchdog_event = asyncio.Event()
        self.updates_watchdog_task = None
        self.media_pool_reaper_event = asyncio.Event()
        self.media_pool_reaper_task = None
        self.listeners = ListenerRegistry(self)
        self.dispatcher = SimpleNamespace(stop=self._noop)
        self.session = FakeSession(self, 1, b"home-key", False)

        class Storage:
            async def save(self):
                pass

            async def test_mode(self):
                return False

            async def dc_id(self):
                return 1

            async def auth_key(self):
                return b"home-key"

        self.storage = Storage()

    async def _noop(self):
        pass

    async def get_dc_option(self, dc_id=None, is_media=False, is_cdn=False, ipv6=False):
        return SimpleNamespace(ip_address=f"10.0.0.{dc_id}", port=443)

    async def invoke(self, query, *args, **kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(id=1, bytes=b"exported")


@pytest.fixture(autouse=True)
def _stub_session(monkeypatch):
    monkeypatch.setattr(pyrogram.client, "Session", FakeSession)
    monkeypatch.setattr(pyrogram.client, "Auth", FakeAuth)


async def test_a_media_session_caches_a_non_media_session_too():
    client = TerminateSessionsFakeClient()
    await client.get_session(4, is_media=True)

    assert list(client.media_sessions) == [4]
    assert list(client.sessions) == [4]


async def test_terminate_stops_every_cached_session():
    client = TerminateSessionsFakeClient()
    await client.get_session(4, is_media=True)
    client.media_session_pools[4] = [FakeSession(client, 4, b"pool-key", False, is_media=True)]

    cached = [
        *client.sessions.values(),
        *client.media_sessions.values(),
        *(s for pool in client.media_session_pools.values() for s in pool),
    ]
    assert len(cached) == 3

    await client.terminate()

    assert all(s.stopped for s in cached)
    assert not client.sessions
    assert not client.media_sessions
    assert not client.media_session_pools


async def test_stopping_a_cached_session_does_not_fire_the_disconnect_handler():
    fired = []

    async def on_disconnect(client):
        fired.append(client)

    client = SimpleNamespace(
        session=None, disconnect_handler=on_disconnect, ipv6=False, proxy=None
    )

    main = Session(client, 1, b"k" * 256, False)
    client.session = main
    cached = Session(client, 4, b"k" * 256, False)

    await cached.stop()
    assert fired == []

    await main.stop()
    assert fired == [client]


class StoppingClient(Stop):
    """A client that connected but never finished starting up.

    A bad session string leaves exactly this state: connect() succeeded, start()
    raised before initialize(), and the caller still has to stop it.
    """

    def __init__(self, is_initialized, is_connected):
        self.is_initialized = is_initialized
        self.is_connected = is_connected
        self.terminated = False
        self.disconnected = False
        self.loop = asyncio.get_event_loop()

    async def terminate(self, clear_handlers: bool = True):
        if not self.is_initialized:
            raise ConnectionError("Client is already terminated")

        self.terminated = True
        self.is_initialized = False

    async def disconnect(self):
        if not self.is_connected:
            raise ConnectionError("Client is already disconnected")

        if self.is_initialized:
            raise ConnectionError("Can not disconnect an initialized client")

        self.disconnected = True
        self.is_connected = False


async def test_stopping_a_half_started_client_still_disconnects_it(caplog):
    client = StoppingClient(is_initialized=False, is_connected=True)

    with caplog.at_level(logging.ERROR):
        await client.stop()

    assert client.disconnected, (
        "terminate raising ConnectionError used to abandon the socket, because "
        "both calls shared one try block"
    )
    assert not caplog.records, (
        "a client that never finished starting up is not an error to report"
    )


async def test_stopping_a_started_client_does_both():
    client = StoppingClient(is_initialized=True, is_connected=True)

    await client.stop()

    assert client.terminated and client.disconnected


async def test_stopping_an_already_stopped_client_is_quiet(caplog):
    client = StoppingClient(is_initialized=False, is_connected=False)

    with caplog.at_level(logging.ERROR):
        await client.stop()

    assert not caplog.records
    assert not client.terminated and not client.disconnected


class HistoryServer:
    """A messages.GetHistory that answers the way Telegram does."""

    def __init__(self, ids):
        self.ids = sorted(ids, reverse=True)
        self.requests = 0

    async def invoke(self, query, *args, **kwargs):
        self.requests += 1

        if self.requests > 50:
            raise AssertionError("get_chat_history is not making progress")

        ordered = self.ids

        if query.offset_id:
            cursor = next(
                (i for i, id in enumerate(ordered) if id < query.offset_id),
                len(ordered)
            )
        else:
            cursor = 0

        start = max(0, cursor + query.add_offset)
        window = ordered[start:start + query.limit]

        return [
            id for id in window
            if id > query.min_id and (not query.max_id or id < query.max_id)
        ]

    async def resolve_peer(self, peer_id):
        return raw.types.InputPeerUser(user_id=1, access_hash=0)


@pytest.fixture
def parsed(monkeypatch):
    async def parse_messages(client, messages, replies=1):
        return [types.Message(id=id) for id in messages]

    monkeypatch.setattr(utils, "parse_messages", parse_messages)


@pytest.mark.asyncio
async def test_a_reversed_history_walks_forward_and_stops(parsed):
    server = HistoryServer(range(1, 11))

    seen = [m.id async for m in pyrogram.Client.get_chat_history(server, 7, reverse=True)]

    assert seen == list(range(1, 11))


@pytest.mark.asyncio
async def test_a_plain_history_still_walks_back_and_stops(parsed):
    server = HistoryServer(range(1, 11))

    seen = [m.id async for m in pyrogram.Client.get_chat_history(server, 7)]

    assert seen == list(range(10, 0, -1))


@pytest.mark.asyncio
async def test_a_reversed_history_crosses_page_boundaries(parsed):
    server = HistoryServer(range(1, 251))

    seen = [m.id async for m in pyrogram.Client.get_chat_history(server, 7, reverse=True)]

    assert seen == list(range(1, 251))
    assert server.requests > 2


@pytest.mark.asyncio
async def test_the_boundaries_are_inclusive_both_ways(parsed):
    forward = [
        m.id async for m in pyrogram.Client.get_chat_history(
            HistoryServer(range(1, 11)), 7, min_id=4, max_id=7, reverse=True
        )
    ]

    backward = [
        m.id async for m in pyrogram.Client.get_chat_history(
            HistoryServer(range(1, 11)), 7, min_id=4, max_id=7
        )
    ]

    assert forward == [4, 5, 6, 7]
    assert backward == [7, 6, 5, 4]


@pytest.mark.asyncio
async def test_a_limit_cuts_a_reversed_walk_short(parsed):
    server = HistoryServer(range(1, 11))

    seen = [
        m.id async for m in pyrogram.Client.get_chat_history(
            server, 7, limit=4, reverse=True
        )
    ]

    assert seen == [1, 2, 3, 4]


# Every one of these forwards the raw result untouched.
PASSTHROUGH = [
    ("can_bot_send_message", {"bot": 1}),
    ("create_business_chat_link", {"link": None}),
    ("delete_business_chat_link", {"slug": "s"}),
    ("update_business_away_message", {"message": None}),
    ("update_business_greeting_message", {"message": None}),
    ("update_business_intro", {"intro": None}),
    ("update_business_location", {"address": "a"}),
    ("update_business_work_hours", {"business_work_hours": None}),
    ("get_bot_info", {"bot": 1}),
    ("resolve_business_chat_link", {"slug": "s"}),
]


@pytest.fixture
def app():
    client = pyrogram.Client("returns", api_id=1, api_hash="x", in_memory=True)

    async def resolve_peer(*args, **kwargs):
        return raw.types.InputPeerSelf()

    client.resolve_peer = resolve_peer
    return client


@pytest.mark.parametrize("name,kwargs", PASSTHROUGH)
async def test_the_raw_result_reaches_the_caller(app, name, kwargs):
    sentinel = object()

    async def invoke(*args, **kwargs):
        return sentinel

    app.invoke = invoke

    assert await getattr(app, name)(**kwargs) is sentinel


async def test_retracting_a_vote_returns_a_poll_not_a_coroutine(app):
    poll = raw.types.Poll(
        id=1,
        hash=0,
        question=raw.types.TextWithEntities(text="q", entities=[]),
        answers=[
            raw.types.PollAnswer(
                text=raw.types.TextWithEntities(text="a", entities=[]), option=b"1"
            )
        ],
    )

    async def invoke(*args, **kwargs):
        return raw.types.Updates(
            updates=[
                raw.types.UpdateMessagePoll(
                    poll_id=1,
                    poll=poll,
                    results=raw.types.PollResults(results=[], total_voters=0),
                )
            ],
            users=[],
            chats=[],
            date=0,
            seq=0,
        )

    app.invoke = invoke

    result = await app.retract_vote(1, 2)

    assert not inspect.iscoroutine(result)
    assert isinstance(result, pyrogram.types.Poll)


async def test_closing_before_a_connection_exists_opens_no_socket_to_leak():
    protocol = TCP(False, None)

    assert protocol.socket is None
    assert protocol.writer is None

    await protocol.close()

    assert protocol.socket is None
    assert protocol.is_connected is False


@pytest.mark.parametrize("kwargs", [{"message_ids": 0}, {"reply_to_message_ids": 0}])
async def test_get_messages_sends_message_id_zero(kwargs):
    from unittest.mock import AsyncMock, MagicMock

    from pyrogram.methods.messages.get_messages import GetMessages

    client = MagicMock()
    client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
    client.invoke = AsyncMock(return_value=raw.types.messages.Messages(messages=[], chats=[], users=[], topics=[]))

    assert await GetMessages.get_messages(client, "me", **kwargs) is None
    assert client.invoke.await_args.args[0].id[0].id == 0


def _wallet_addresses(*user_ids):
    return raw.types.wallet.UserAddresses(
        addresses=[
            raw.types.WalletUserAddress(user_id=i, address=f"UQ{i}", public_key=bytes([i]))
            for i in user_ids
        ],
        users=[raw.types.User(id=i, first_name=str(i), usernames=[], restriction_reason=[]) for i in user_ids]
    )


async def test_wallet_addresses_are_asked_for_by_user():
    client = FakeClient([_wallet_addresses(5, 6)])

    found = await pyrogram.Client.get_user_ton_wallet_addresses(client, [5, 6])

    sent = client.sent[0]
    assert isinstance(sent, raw.functions.wallet.GetUserAddresses)
    assert [p.user_id for p in sent.id] == [5, 6] and sent.addresses == [] and not sent.force
    assert [(a.wallet_address, a.user.id) for a in found] == [("UQ5", 5), ("UQ6", 6)]


async def test_a_single_wallet_user_is_accepted_too():
    client = FakeClient([_wallet_addresses(5)])

    found = await pyrogram.Client.get_user_ton_wallet_addresses(client, 5)

    assert [a.user.id for a in found] == [5]


async def test_creating_a_user_wallet_forces_the_lookup():
    client = FakeClient([_wallet_addresses(5)])

    created = await pyrogram.Client.create_user_wallet(client, 5)

    assert client.sent[0].force is True
    assert created.wallet_address == "UQ5"


async def test_a_wallet_is_looked_up_by_its_address():
    client = FakeClient([_wallet_addresses(5), _wallet_addresses()])

    found = await pyrogram.Client.get_address_ton_wallet(client, "UQ5")
    missing = await pyrogram.Client.get_address_ton_wallet(client, "UQnone")

    assert client.sent[0].addresses == ["UQ5"] and client.sent[0].id == []
    assert found.wallet_address == "UQ5" and found.user.id == 5
    assert missing is None


async def test_the_proof_challenge_keeps_its_expiry():
    client = FakeClient([raw.types.wallet.ProofChallenge(payload="p", expires=1700000000, domain="d")])

    challenge = await pyrogram.Client.get_ton_wallet_ownership_proof_challenge(client)

    assert (challenge.payload, challenge.domain) == ("p", "d")
    assert challenge.expiration_date.timestamp() == 1700000000


async def test_replacing_a_wallet_sends_the_proof_without_a_password():
    state = raw.types.WalletState(address="UQ1", public_key=b"k", balance=7, backup_enabled=True)
    client = FakeClient([state])
    proof = types.TonWalletOwnershipProof(public_key=b"new", timestamp=10, signature=b"sig")

    result = await pyrogram.Client.replace_ton_wallet(client, proof)

    sent = client.sent[0]
    assert isinstance(sent.wallet, raw.types.InputWalletImported)
    assert (sent.wallet.public_key, sent.wallet.proof.timestamp, sent.wallet.proof.signature) == (b"new", 10, b"sig")
    assert sent.password is None
    assert (result.wallet_address, result.gram_amount, result.is_backup_enabled) == ("UQ1", 7, True)


async def test_deleting_a_wallet_asks_for_a_new_one():
    client = FakeClient([raw.types.WalletStateEmpty(creating=True)])

    result = await pyrogram.Client.delete_ton_wallet(client)

    assert isinstance(client.sent[0].wallet, raw.types.InputWalletNew)
    assert result.is_being_created is True and result.wallet_address is None


async def test_deleting_a_gift_sends_the_saved_gift():
    client = FakeClient([True])
    client.SAVED_GIFT_RE = pyrogram.Client.SAVED_GIFT_RE
    client.UPGRADED_GIFT_RE = pyrogram.Client.UPGRADED_GIFT_RE

    assert await pyrogram.Client.delete_gift(client, "https://t.me/nft/abc-1") is True
    assert isinstance(client.sent[0], raw.functions.payments.DeleteStarGift)
    assert client.sent[0].stargift.slug == "abc-1"
