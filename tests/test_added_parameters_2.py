import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyrogram
from pyrogram import raw, types, utils
from pyrogram.filters import create

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_added_parameters import FakeClient, VIEW_ONCE_TTL, no_text  # noqa: F401


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

