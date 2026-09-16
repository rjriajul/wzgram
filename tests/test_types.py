from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

import pyrogram
from pyrogram import enums, raw, types
from pyrogram.types import Object
from pyrogram.types.messages_and_media.message import Str as MessageStr
from pyrogram.types.user_and_chats.user import Link as UserLink


# ---------------------------------------------------------------------------
# 1.  Test creating each type with the MINIMUM required parameters
# ---------------------------------------------------------------------------

class TestMinimalConstruction:
    def test_object_minimal(self):
        obj = Object()
        assert obj._client is None

    def test_message_minimal(self):
        msg = types.Message(id=1)
        assert msg.id == 1

    def test_user_minimal(self):
        user = types.User(id=123)
        assert user.id == 123

    def test_chat_minimal(self):
        chat = types.Chat()
        assert chat.id is None

    def test_chat_member_minimal(self):
        member = types.ChatMember(status=enums.ChatMemberStatus.MEMBER)
        assert member.status == enums.ChatMemberStatus.MEMBER

    def test_inline_keyboard_button_minimal(self):
        btn = types.InlineKeyboardButton(text="Click")
        assert btn.text == "Click"
        assert btn.callback_data is None

    def test_inline_keyboard_markup_minimal(self):
        btn = types.InlineKeyboardButton(text="A", callback_data="1")
        markup = types.InlineKeyboardMarkup(inline_keyboard=[[btn]])
        assert markup.inline_keyboard == [[btn]]

    def test_callback_query_minimal(self):
        user = types.User(id=1)
        q = types.CallbackQuery(id="cq1", from_user=user, chat_instance="ci1")
        assert q.id == "cq1"
        assert q.from_user.id == 1

    def test_reply_parameters_minimal(self):
        rp = types.ReplyParameters()
        assert rp.message_id is None

    def test_photo_minimal(self):
        dt = datetime(2023, 1, 1)
        photo = types.Photo(
            file_id="fid",
            file_unique_id="fuid",
            width=100,
            height=200,
            file_size=5000,
            date=dt,
        )
        assert photo.file_id == "fid"
        assert photo.width == 100

    def test_audio_minimal(self):
        audio = types.Audio(file_id="fid", file_unique_id="fuid", duration=120)
        assert audio.duration == 120

    def test_document_minimal(self):
        doc = types.Document(file_id="fid", file_unique_id="fuid")
        assert doc.file_id == "fid"

    def test_video_minimal(self):
        video = types.Video(
            file_id="fid",
            file_unique_id="fuid",
            width=640,
            height=480,
            codec="h264",
            duration=60,
        )
        assert video.codec == "h264"

    def test_voice_minimal(self):
        voice = types.Voice(file_id="fid", file_unique_id="fuid", duration=30)
        assert voice.duration == 30

    def test_video_note_minimal(self):
        vn = types.VideoNote(file_id="fid", file_unique_id="fuid", length=240, duration=10)
        assert vn.length == 240

    def test_animation_minimal(self):
        anim = types.Animation(
            file_id="fid",
            file_unique_id="fuid",
            width=320,
            height=240,
            duration=5,
        )
        assert anim.duration == 5

    def test_contact_minimal(self):
        contact = types.Contact(phone_number="+123", first_name="Alice")
        assert contact.phone_number == "+123"
        assert contact.first_name == "Alice"

    def test_location_minimal(self):
        loc = types.Location(latitude=1.0, longitude=2.0)
        assert loc.latitude == 1.0

    def test_venue_minimal(self):
        loc = types.Location(latitude=1.0, longitude=2.0)
        venue = types.Venue(location=loc, title="Cafe", address="123 St")
        assert venue.title == "Cafe"

    def test_poll_minimal(self):
        opt = types.PollOption(persistent_id="opt1")
        poll = types.Poll(
            id="poll1",
            options=[opt],
            is_closed=False,
        )
        assert poll.id == "poll1"
        assert len(poll.options) == 1

    def test_dice_minimal(self):
        dice = types.Dice(emoji="🎲", value=5)
        assert dice.emoji == "🎲"
        assert dice.value == 5

    def test_sticker_minimal(self):
        st = types.Sticker(
            file_id="fid",
            file_unique_id="fuid",
            type=enums.StickerType.REGULAR,
            width=512,
            height=512,
            is_animated=False,
            is_video=False,
        )
        assert st.type == enums.StickerType.REGULAR

    def test_web_page_minimal(self):
        wp = types.WebPage(id="wp1", url="https://example.com")
        assert wp.id == "wp1"
        assert wp.url == "https://example.com"

    def test_game_minimal(self):
        dt = datetime(2023, 1, 1)
        photo = types.Photo(
            file_id="fid", file_unique_id="fuid",
            width=100, height=100, file_size=1000, date=dt,
        )
        game = types.Game(
            id=1,
            title="Test",
            short_name="test",
            description="A game",
            photo=photo,
        )
        assert game.title == "Test"

    def test_message_entity_minimal(self):
        entity = types.MessageEntity(
            type=enums.MessageEntityType.BOLD,
            offset=0,
            length=5,
        )
        assert entity.type == enums.MessageEntityType.BOLD

    def test_forum_topic_minimal(self):
        topic = types.ForumTopic(id=42)
        assert topic.id == 42

    def test_keyboard_button_minimal(self):
        btn = types.KeyboardButton(text="Press")
        assert btn.text == "Press"

    def test_force_reply_minimal(self):
        fr = types.ForceReply()
        assert fr.selective is None

    def test_reply_keyboard_markup_minimal(self):
        btn = types.KeyboardButton(text="Go")
        markup = types.ReplyKeyboardMarkup(keyboard=[[btn]])
        assert markup.keyboard == [[btn]]

    def test_reply_keyboard_remove_minimal(self):
        rkr = types.ReplyKeyboardRemove()
        assert rkr.selective is None


# ---------------------------------------------------------------------------
# 2.  Test common properties / methods
# ---------------------------------------------------------------------------

class TestCommonProperties:
    def test_object_str_repr(self):
        obj = Object()
        s = str(obj)
        assert '"_": "Object"' in s
        r = repr(obj)
        assert r.startswith("pyrogram.types.Object(")

    def test_object_eq(self):
        a = Object()
        b = Object()
        assert a == b

    def test_object_bind(self):
        obj = Object()
        obj.bind(None)
        assert obj._client is None

    def test_object_default_datetime(self):
        result = Object.default(datetime(2023, 6, 15))
        assert isinstance(result, str)

    def test_user_full_name(self):
        user = types.User(id=1, first_name="John", last_name="Doe")
        assert user.full_name == "John Doe"

    def test_user_full_name_none_last(self):
        user = types.User(id=1, first_name="John")
        assert user.full_name == "John"

    def test_user_empty_full_name(self):
        user = types.User(id=1)
        assert user.full_name is None

    def test_user_mention(self):
        user = types.User(id=1, first_name="Alice")
        user._client = Mock()
        user._client.parse_mode = enums.ParseMode.HTML
        mention = user.mention
        assert "tg://user?id=1" in str(mention)

    def test_message_link(self):
        chat = types.Chat(
            id=-100123,
            type=enums.ChatType.SUPERGROUP,
            username="testgroup",
        )
        msg = types.Message(id=5, chat=chat)
        assert "t.me/testgroup/5" in msg.link

    def test_message_content_no_text(self):
        msg = types.Message(id=1)
        assert msg.content == ""

    def test_message_content_text(self):
        msg = types.Message(id=1, text=MessageStr("hello"))
        assert msg.content == "hello"

    def test_message_content_caption(self):
        msg = types.Message(id=1, caption=MessageStr("capt"))
        assert msg.content == "capt"

    def test_message_empty_default(self):
        msg = types.Message(id=1)
        assert msg.empty is None

    def test_message_empty_explicit(self):
        msg = types.Message(id=1, empty=True)
        assert msg.empty is True

    def test_callable_link(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        assert callable(link)


# ---------------------------------------------------------------------------
# 3.  Test that all expected types are exported from pyrogram.types
# ---------------------------------------------------------------------------

class TestExports:
    _expected_types = [
        "Object",
        "Message",
        "User",
        "Chat",
        "ChatMember",
        "InlineKeyboardButton",
        "InlineKeyboardMarkup",
        "CallbackQuery",
        "ReplyParameters",
        "Photo",
        "Audio",
        "Document",
        "Video",
        "Voice",
        "VideoNote",
        "Animation",
        "Contact",
        "Location",
        "Venue",
        "Poll",
        "Dice",
        "Sticker",
        "WebPage",
        "Game",
        "MessageEntity",
        "ForumTopic",
        "KeyboardButton",
        "ForceReply",
        "ReplyKeyboardMarkup",
        "ReplyKeyboardRemove",
        "List",
        "InlineQuery",
        "ChosenInlineResult",
        "SentCode",
        "TermsOfService",
    ]

    def test_expected_types_exported(self):
        for name in self._expected_types:
            assert hasattr(pyrogram.types, name), f"{name} is not exported from pyrogram.types"

    def test_object_base(self):
        assert issubclass(types.Message, Object)
        assert issubclass(types.User, Object)
        assert issubclass(types.Chat, Object)
        assert issubclass(types.CallbackQuery, Object)
        assert issubclass(types.Poll, Object)


# ---------------------------------------------------------------------------
# 4.  Test type conversions / __init__ keyword-only behaviour
# ---------------------------------------------------------------------------

class TestInits:
    def test_message_requires_id(self):
        with pytest.raises(TypeError):
            types.Message()

    def test_user_requires_id(self):
        with pytest.raises(TypeError):
            types.User()

    def test_chat_member_requires_status(self):
        with pytest.raises(TypeError):
            types.ChatMember()

    def test_inline_keyboard_button_requires_text(self):
        with pytest.raises(TypeError):
            types.InlineKeyboardButton()

    def test_inline_keyboard_markup_requires_keyboard(self):
        with pytest.raises(TypeError):
            types.InlineKeyboardMarkup()

    def test_callback_query_requires_id_from_user_chat_instance(self):
        with pytest.raises(TypeError):
            types.CallbackQuery()
        with pytest.raises(TypeError):
            types.CallbackQuery(id="x", from_user=types.User(id=1))
        with pytest.raises(TypeError):
            types.CallbackQuery(id="x", chat_instance="ci")

    def test_photo_requires_file_fields(self):
        with pytest.raises(TypeError):
            types.Photo(file_id="fid")

    def test_audio_requires_duration(self):
        with pytest.raises(TypeError):
            types.Audio(file_id="fid", file_unique_id="fuid")

    def test_video_requires_media_fields(self):
        with pytest.raises(TypeError):
            types.Video(file_id="fid", file_unique_id="fuid", width=100, height=100)

    def test_dice_requires_emoji_and_value(self):
        with pytest.raises(TypeError):
            types.Dice(emoji="🎲")
        with pytest.raises(TypeError):
            types.Dice(value=3)

    def test_sticker_requires_all_required(self):
        with pytest.raises(TypeError):
            types.Sticker(file_id="fid")

    def test_message_entity_requires_type_offset_length(self):
        with pytest.raises(TypeError):
            types.MessageEntity(type=enums.MessageEntityType.BOLD)
        with pytest.raises(TypeError):
            types.MessageEntity(type=enums.MessageEntityType.BOLD, offset=0)

    def test_contact_requires_phone_and_first_name(self):
        with pytest.raises(TypeError):
            types.Contact(phone_number="+1")

    def test_venue_requires_location_title_address(self):
        with pytest.raises(TypeError):
            types.Venue(title="X", address="Y")
        with pytest.raises(TypeError):
            types.Venue(location=types.Location(), title="X")

    def test_poll_missing_is_closed(self):
        with pytest.raises(TypeError):
            types.Poll(id="p1", options=[types.PollOption(persistent_id="o")])

    def test_keyword_only_args(self):
        with pytest.raises(TypeError):
            types.User(123)

    def test_forum_topic_id_required(self):
        with pytest.raises(TypeError):
            types.ForumTopic()


# ---------------------------------------------------------------------------
# 5.  Test __setstate__ / __getstate__ (pickle support)
# ---------------------------------------------------------------------------

class TestPickle:
    def test_object_getstate_no_client(self):
        obj = Object()
        state = obj.__getstate__()
        assert "_client" not in state

    def test_object_pickle_roundtrip(self):
        obj = Object()
        state = obj.__getstate__()
        new_obj = Object()
        new_obj.__setstate__(state)
        assert getattr(new_obj, "_client", None) is None

    def test_object_pickle_datetime(self):
        msg = types.Message(id=1, date=datetime(2023, 1, 1, 12, 0))
        state = msg.__getstate__()
        new_msg = object.__new__(types.Message)
        new_msg.__setstate__(state)
        assert new_msg.date == datetime(2023, 1, 1, 12, 0)

    def test_message_pickle_roundtrip(self):
        msg = types.Message(id=42, text=MessageStr("hello"))
        state = msg.__getstate__()
        new_msg = object.__new__(types.Message)
        new_msg.__setstate__(state)
        assert new_msg.id == 42
        assert new_msg.text == "hello"


# ---------------------------------------------------------------------------
# 6.  Test InlineKeyboardButton customisation
# ---------------------------------------------------------------------------

class TestInlineKeyboardButton:
    def test_button_style_default(self):
        btn = types.InlineKeyboardButton(text="X", callback_data="d")
        assert btn.style == enums.ButtonStyle.DEFAULT

    def test_button_with_callback(self):
        btn = types.InlineKeyboardButton(text="X", callback_data="data")
        assert btn.callback_data == "data"

    def test_button_with_url(self):
        btn = types.InlineKeyboardButton(text="Link", url="https://t.me")
        assert btn.url == "https://t.me"

    def test_button_text_converted_to_str(self):
        btn = types.InlineKeyboardButton(text=123)
        assert isinstance(btn.text, str)
        assert btn.text == "123"


# ---------------------------------------------------------------------------
# 7.  Test ReplyKeyboardButton
# ---------------------------------------------------------------------------

class TestKeyboardButton:
    def test_button_text_converted_to_str(self):
        btn = types.KeyboardButton(text=42)
        assert isinstance(btn.text, str)
        assert btn.text == "42"

    def test_button_request_contact(self):
        btn = types.KeyboardButton(text="Share", request_contact=True)
        assert btn.request_contact is True


# ---------------------------------------------------------------------------
# 8.  Test Location edge cases
# ---------------------------------------------------------------------------

class TestLocation:
    def test_defaults(self):
        loc = types.Location()
        assert loc.longitude is None
        assert loc.latitude is None

    def test_with_coords(self):
        loc = types.Location(latitude=10.0, longitude=20.0)
        assert loc.latitude == 10.0
        assert loc.longitude == 20.0

    def test_live_period(self):
        loc = types.Location(latitude=1.0, longitude=2.0, live_period=60)
        assert loc.live_period == 60

    def test_heading(self):
        loc = types.Location(latitude=1.0, longitude=2.0, heading=90)
        assert loc.heading == 90

    def test_proximity_alert_radius(self):
        loc = types.Location(latitude=1.0, longitude=2.0, proximity_alert_radius=100)
        assert loc.proximity_alert_radius == 100


# ---------------------------------------------------------------------------
# 9.  Test the Link helper
# ---------------------------------------------------------------------------

class TestUserLink:
    def test_link_class(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        assert "tg://user?id=1" in str(link)
        assert link.url == "tg://user?id=1"

    def test_link_format_html(self):
        result = UserLink.format(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        assert 'href=' in result
        assert "tg://user?id=1" in result
        assert "Alice</a>" in result

    def test_link_format_markdown(self):
        result = UserLink.format(url="tg://user?id=1", text="Alice", style=enums.ParseMode.MARKDOWN)
        assert result == "[Alice](tg://user?id=1)"


# ---------------------------------------------------------------------------
# 10.  Test Message.Str helper
# ---------------------------------------------------------------------------

class TestMessageStr:
    def test_str_init(self):
        s = MessageStr("hello")
        assert s == "hello"
        assert s.entities is None

    def test_str_init_entities(self):
        s = MessageStr("hello")
        s.init([])
        assert s.entities == []


# ---------------------------------------------------------------------------
# 11.  Test nested objects
# ---------------------------------------------------------------------------

class TestNestedTypes:
    def test_message_with_reply_markup(self):
        markup = types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="B", callback_data="b")]]
        )
        msg = types.Message(id=1, reply_markup=markup)
        assert msg.reply_markup.inline_keyboard[0][0].text == "B"

    def test_chat_member_with_user(self):
        user = types.User(id=99, first_name="Bob")
        member = types.ChatMember(
            status=enums.ChatMemberStatus.MEMBER,
            user=user,
            joined_date=datetime(2024, 1, 1),
        )
        assert member.user.first_name == "Bob"
        assert member.joined_date == datetime(2024, 1, 1)

    def test_venue_with_location(self):
        loc = types.Location(latitude=40.0, longitude=-3.0)
        venue = types.Venue(location=loc, title="X", address="Y")
        assert venue.location.latitude == 40.0

    def test_poll_with_options(self):
        opt1 = types.PollOption(persistent_id="a")
        opt2 = types.PollOption(persistent_id="b")
        poll = types.Poll(id="p1", options=[opt1, opt2], is_closed=False)
        assert len(poll.options) == 2
        assert poll.options[0].persistent_id == "a"


# ---------------------------------------------------------------------------
# 12.  Test attribute assignment compatibility (no __slots__ used by these types)
# ---------------------------------------------------------------------------

class TestDynamicAttributes:
    def test_message_dynamic_attr(self):
        msg = types.Message(id=1)
        msg.custom_attr = 42
        assert msg.custom_attr == 42

    def test_user_dynamic_attr(self):
        user = types.User(id=1)
        user.custom_attr = "hello"
        assert user.custom_attr == "hello"

    def test_chat_dynamic_attr(self):
        chat = types.Chat(id=1)
        chat.custom_attr = [1, 2, 3]
        assert chat.custom_attr == [1, 2, 3]

    def test_callback_query_dynamic_attr(self):
        q = types.CallbackQuery(id="q", from_user=types.User(id=1), chat_instance="ci")
        q.new_field = True
        assert q.new_field is True

    def test_sticker_dynamic_attr(self):
        st = types.Sticker(
            file_id="fid", file_unique_id="fuid",
            type=enums.StickerType.REGULAR,
            width=100, height=100, is_animated=False, is_video=False,
        )
        st.extra = 1
        assert st.extra == 1


# ---------------------------------------------------------------------------
# 13.  Verify all user-facing types are subclasses of Object
# ---------------------------------------------------------------------------

_OBJECT_SUBCLASS_TYPES = [
    types.Message,
    types.User,
    types.Chat,
    types.ChatMember,
    types.InlineKeyboardButton,
    types.InlineKeyboardMarkup,
    types.CallbackQuery,
    types.ReplyParameters,
    types.Photo,
    types.Audio,
    types.Document,
    types.Video,
    types.Voice,
    types.VideoNote,
    types.Animation,
    types.Contact,
    types.Location,
    types.Venue,
    types.Poll,
    types.Dice,
    types.Sticker,
    types.WebPage,
    types.Game,
    types.MessageEntity,
    types.ForumTopic,
    types.KeyboardButton,
    types.ForceReply,
    types.ReplyKeyboardMarkup,
    types.ReplyKeyboardRemove,
]


class TestObjectSubclass:
    @pytest.mark.parametrize("cls", _OBJECT_SUBCLASS_TYPES, ids=lambda c: c.__name__)
    def test_is_object_subclass(self, cls):
        assert issubclass(cls, Object), f"{cls.__name__} is not a subclass of Object"


# ---------------------------------------------------------------------------
# 14.  Test that Poll.get_vote_percentage works as a static method
# ---------------------------------------------------------------------------

class TestPollVotePercentage:
    def test_all_zero(self):
        result = types.Poll.get_vote_percentage([0, 0, 0], 0)
        assert result == [0, 0, 0]

    def test_single_option(self):
        result = types.Poll.get_vote_percentage([10], 10)
        assert result == [100]

    def test_two_options_equal(self):
        result = types.Poll.get_vote_percentage([5, 5], 10)
        assert result == [50, 50]

    def test_three_options(self):
        result = types.Poll.get_vote_percentage([3, 3, 4], 10)
        assert sum(result) == 100
        assert len(result) == 3

    def test_total_voter_count_differs(self):
        result = types.Poll.get_vote_percentage([5, 5], 8)
        assert len(result) == 2
        assert result[0] == result[1]


# ---------------------------------------------------------------------------
# 15.  Test that the Link class __new__/__str__ work
# ---------------------------------------------------------------------------

class TestLinkStr:
    def test_link_str_html(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        s = str(link)
        assert "tg://user?id=1" in s
        assert "Alice" in s

    def test_link_str_markdown(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.MARKDOWN)
        s = str(link)
        assert s == "[Alice](tg://user?id=1)"

    def test_link_callable(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        result = link("Bob")
        assert "Bob" in result
        assert "tg://user?id=1" in result

    def test_link_callable_with_style(self):
        link = UserLink(url="tg://user?id=1", text="Alice", style=enums.ParseMode.HTML)
        result = link(style=enums.ParseMode.MARKDOWN)
        assert "Alice" in result
        assert result.startswith("[")


# ---------------------------------------------------------------------------
# 16.  Test Message properties (content, md_text, html_text)
# ---------------------------------------------------------------------------

class TestMessageProperties:
    def test_md_text_no_text(self):
        msg = types.Message(id=1)
        assert msg.md_text == ""

    def test_html_text_no_text(self):
        msg = types.Message(id=1)
        assert msg.html_text == ""

    def test_md_text_with_text(self):
        s = MessageStr("hello")
        s.entities = []
        msg = types.Message(id=1, text=s, entities=[])
        assert msg.md_text == "hello"

    def test_html_text_with_text(self):
        s = MessageStr("hello")
        s.entities = []
        msg = types.Message(id=1, text=s, entities=[])
        assert msg.html_text == "hello"


# ---------------------------------------------------------------------------
# 17.  Test Object.__repr__ roundtrip property
# ---------------------------------------------------------------------------

class TestObjectRepr:
    def test_repr_includes_class_name(self):
        msg = types.Message(id=1)
        r = repr(msg)
        assert "Message(" in r

    def test_repr_includes_non_none_attrs(self):
        msg = types.Message(id=42, text=MessageStr("hi"))
        r = repr(msg)
        assert "id=42" in r
        assert "text=" in r


# ---------------------------------------------------------------------------
# 18.  Test Object.default for various types
# ---------------------------------------------------------------------------

class TestObjectDefault:
    def test_default_bytes(self):
        result = Object.default(b"hello")
        assert isinstance(result, str)

    def test_default_enum(self):
        result = Object.default(enums.ChatMemberStatus.MEMBER)
        assert isinstance(result, str)

    def test_default_datetime(self):
        result = Object.default(datetime(2024, 1, 1))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 19.  Test Object.__eq__
# ---------------------------------------------------------------------------

class TestObjectEq:
    def test_eq_same_attrs(self):
        a = types.Message(id=1)
        b = types.Message(id=1)
        assert a == b

    def test_eq_different_attrs(self):
        a = types.Message(id=1)
        b = types.Message(id=2)
        assert a != b

    def test_eq_different_types(self):
        a = types.User(id=1)
        b = types.Message(id=1)
        assert a != b


class TestCommunity:
    def test_minimal(self):
        c = types.Community(id=1, title="Test")
        assert c.id == 1
        assert c.title == "Test"
        assert c.date is None
        assert c.is_creator is None

    def test_chat_type_enum(self):
        assert enums.ChatType.COMMUNITY.value == "community"

    def test_message_service_type_enums(self):
        assert enums.MessageServiceType.COMMUNITY_CHAT_ADDED is not None
        assert enums.MessageServiceType.COMMUNITY_CHAT_REMOVED is not None

    def test_message_has_fields(self):
        msg = types.Message(id=1)
        assert msg.community_chat_added is None
        assert msg.community_chat_removed is None

    def test_chat_full_info(self):
        info = types.ChatFullInfo()
        assert info.community is None

    def test_community_chat_added(self):
        added = types.CommunityChatAdded(community_id=123)
        assert added.community_id == 123

    def test_community_chat_removed(self):
        removed = types.CommunityChatRemoved()
        assert removed.community_id is None


class TestKeyboardButtonRequests:
    """The request_* buttons must survive a write/read round trip.

    Their types were exported long before KeyboardButton could carry them, so a
    constructor argument that never reaches the wire looks correct from the
    outside.
    """

    def test_request_users_round_trips(self):
        button = types.KeyboardButton(
            text="Pick users",
            request_users=types.KeyboardButtonRequestUsers(
                button_id=7,
                user_is_bot=False,
                user_is_premium=True,
                max_quantity=3,
                request_name=True,
                request_username=True
            )
        )

        raw_button = button.write()

        assert isinstance(raw_button.type.peer_type, raw.types.RequestPeerTypeUser)
        assert raw_button.type.button_id == 7
        assert raw_button.type.max_quantity == 3

        parsed = types.KeyboardButton.read(raw_button)

        assert parsed.request_users.button_id == 7
        assert parsed.request_users.user_is_premium is True
        assert parsed.request_users.max_quantity == 3
        assert parsed.request_users.request_name is True

    def test_request_chat_round_trips_a_channel(self):
        button = types.KeyboardButton(
            text="Pick a channel",
            request_chat=types.KeyboardButtonRequestChat(
                button_id=9,
                chat_is_channel=True,
                chat_is_created=True,
                user_administrator_rights=types.ChatAdministratorRights(
                    can_post_messages=True
                )
            )
        )

        raw_button = button.write()

        assert isinstance(raw_button.type.peer_type, raw.types.RequestPeerTypeBroadcast)

        parsed = types.KeyboardButton.read(raw_button)

        assert parsed.request_chat.chat_is_channel is True
        assert parsed.request_chat.chat_is_created is True
        assert parsed.request_chat.user_administrator_rights.can_post_messages is True

    def test_request_chat_round_trips_a_group(self):
        button = types.KeyboardButton(
            text="Pick a group",
            request_chat=types.KeyboardButtonRequestChat(
                button_id=1,
                chat_is_channel=False,
                bot_is_member=True
            )
        )

        raw_button = button.write()

        assert isinstance(raw_button.type.peer_type, raw.types.RequestPeerTypeChat)
        assert types.KeyboardButton.read(raw_button).request_chat.bot_is_member is True

    def test_request_poll_round_trips(self):
        button = types.KeyboardButton(
            text="Make a quiz",
            request_poll=types.KeyboardButtonPollType(is_quiz=True)
        )

        raw_button = button.write()

        assert isinstance(raw_button.type, raw.types.ButtonTypeRequestPoll)
        assert types.KeyboardButton.read(raw_button).request_poll.is_quiz is True

    def test_request_managed_bot_round_trips(self):
        button = types.KeyboardButton(
            text="New bot",
            request_managed_bot=types.KeyboardButtonRequestManagedBot(
                button_id=1,
                suggested_name="Name",
                suggested_username="username"
            )
        )

        raw_button = button.write()

        assert isinstance(raw_button.type.peer_type, raw.types.RequestPeerTypeCreateBot)

        parsed = types.KeyboardButton.read(raw_button)

        assert parsed.request_managed_bot.suggested_username == "username"

    def test_style_and_icon_round_trip(self):
        button = types.KeyboardButton(
            text="Danger",
            style=enums.ButtonStyle.DANGER,
            icon_custom_emoji_id="5555"
        )

        raw_button = button.write()

        assert raw_button.style.bg_danger is True

        parsed = types.KeyboardButton.read(raw_button)

        assert parsed.style == enums.ButtonStyle.DANGER
        assert parsed.icon_custom_emoji_id == "5555"

    def test_a_plain_button_still_reads_back_as_text(self):
        plain = raw.types.KeyboardButton(
            text="hi", type=raw.types.ButtonTypeDefault()
        )

        assert types.KeyboardButton.read(plain) == "hi", (
            "ReplyKeyboardMarkup relies on plain buttons collapsing to a string"
        )

    def test_contact_and_location_are_unchanged(self):
        contact = types.KeyboardButton(text="c", request_contact=True)
        location = types.KeyboardButton(text="l", request_location=True)

        assert isinstance(contact.write().type, raw.types.ButtonTypeRequestPhone)
        assert isinstance(location.write().type, raw.types.ButtonTypeRequestGeoLocation)
        assert types.KeyboardButton.read(contact.write()).request_contact is True
        assert types.KeyboardButton.read(location.write()).request_location is True


class TestChatCoverageFields:
    """Fields added to close Bot API gaps must actually parse, not just exist.

    A constructor argument that no _parse ever populates satisfies a signature
    check while always being None in practice.
    """

    @staticmethod
    def channel(**kwargs):
        kwargs.setdefault("usernames", [])
        kwargs.setdefault("restriction_reason", [])

        return raw.types.Channel(
            id=777,
            title="Test",
            photo=raw.types.ChatPhotoEmpty(),
            date=0,
            **kwargs
        )

    def test_join_to_send_messages_is_parsed(self):
        chat = types.Chat._parse_channel_chat(None, self.channel(join_to_send=True))

        assert chat.join_to_send_messages is True

    def test_emoji_status_is_parsed_for_a_channel(self):
        chat = types.Chat._parse_channel_chat(
            None,
            self.channel(emoji_status=raw.types.EmojiStatus(document_id=555, until=1893456000))
        )

        assert chat.emoji_status.custom_emoji_id == "555"
        assert chat.emoji_status.until_date is not None

    def test_emoji_status_is_parsed_for_a_user(self):
        user = raw.types.User(
            id=42,
            first_name="A",
            usernames=[],
            restriction_reason=[],
            emoji_status=raw.types.EmojiStatus(document_id=999)
        )
        chat = types.Chat._parse_user_chat(None, user)

        assert chat.emoji_status.custom_emoji_id == "999"

    def test_absent_values_stay_none(self):
        chat = types.Chat._parse_channel_chat(None, self.channel())

        assert chat.join_to_send_messages is None
        assert chat.emoji_status is None
        assert chat.location is None


class TestChatLocation:
    def test_it_parses_a_channel_location(self):
        location = types.ChatLocation._parse(
            None,
            raw.types.ChannelLocation(
                geo_point=raw.types.GeoPoint(
                    long=12.5, lat=41.9, access_hash=0, accuracy_radius=50
                ),
                address="Rome, Italy"
            )
        )

        assert location.address == "Rome, Italy"
        assert location.location.latitude == 41.9
        assert location.location.longitude == 12.5

    def test_an_empty_location_is_none(self):
        assert types.ChatLocation._parse(None, raw.types.ChannelLocationEmpty()) is None


class TestInlineResultCaptionPlacement:
    """show_caption_above_media has to reach inputBotInlineMessageMediaAuto.

    MTProto carries it as invert_media on the inline message, and only there:
    inputSingleMedia has no such flag, which is why album items cannot have it.
    """

    PHOTO_FILE_ID = "AgACAgIAAx0CAAGgr9AAAgmZX7b7IPLRl8NcV3EJkzHwI1gwT-oAAq2nMRuBpLlJPJY-URZfhTkgfeqKEAADAQADAgADbQADAZ8BAAEeBA"

    @staticmethod
    def client():
        client = AsyncMock()
        client.parser.parse = AsyncMock(return_value={"message": "cap", "entities": []})

        return client

    @pytest.mark.parametrize("flag,expected", [(True, True), (None, None)])
    async def test_a_url_result_forwards_the_flag(self, flag, expected):
        result = types.InlineQueryResultPhoto(
            photo_url="https://example.com/p.jpg",
            caption="cap",
            show_caption_above_media=flag
        )
        written = await result.write(self.client())

        assert written.send_message.invert_media is expected

    async def test_a_cached_result_forwards_the_flag(self):
        result = types.InlineQueryResultCachedPhoto(
            photo_file_id=self.PHOTO_FILE_ID,
            caption="cap",
            show_caption_above_media=True
        )
        written = await result.write(self.client())

        assert written.send_message.invert_media is True

    @pytest.mark.parametrize(
        "name",
        [
            "InlineQueryResultPhoto",
            "InlineQueryResultVideo",
            "InlineQueryResultCachedPhoto",
            "InlineQueryResultCachedVideo",
        ]
    )
    def test_every_captioned_inline_result_accepts_it(self, name):
        import inspect

        assert "show_caption_above_media" in inspect.signature(
            getattr(types, name).__init__
        ).parameters


class TestInlineKeyboardButtonAdditions:
    """copy_text, pay and switch_inline_query_chosen_chat must reach the wire.

    pay was present in the docstring but its assignment was commented out, so it
    was accepted and silently dropped.
    """

    @staticmethod
    async def written(**kwargs):
        return await types.InlineKeyboardButton(**kwargs).write(AsyncMock())

    async def test_copy_text_round_trips(self):
        written = await self.written(
            text="Copy", copy_text=types.CopyTextButton(text="hello")
        )

        assert isinstance(written.type, raw.types.InlineButtonTypeCopy)
        assert written.type.copy_text == "hello"
        assert types.InlineKeyboardButton.read(written).copy_text.text == "hello"

    async def test_pay_round_trips(self):
        written = await self.written(text="Pay", pay=True)

        assert isinstance(written.type, raw.types.InlineButtonTypeBuy)
        assert types.InlineKeyboardButton.read(written).pay is True

    async def test_chosen_chat_maps_every_peer_type(self):
        written = await self.written(
            text="Pick",
            switch_inline_query_chosen_chat=types.SwitchInlineQueryChosenChat(
                query="hi",
                allow_user_chats=True,
                allow_bot_chats=True,
                allow_group_chats=True,
                allow_channel_chats=True
            )
        )

        assert {type(p).__name__ for p in written.type.peer_types} == {
            "InlineQueryPeerTypePM",
            "InlineQueryPeerTypeBotPM",
            "InlineQueryPeerTypeChat",
            "InlineQueryPeerTypeMegagroup",
            "InlineQueryPeerTypeBroadcast",
        }

        parsed = types.InlineKeyboardButton.read(written).switch_inline_query_chosen_chat

        assert parsed.query == "hi"
        assert parsed.allow_user_chats is True
        assert parsed.allow_bot_chats is True
        assert parsed.allow_group_chats is True
        assert parsed.allow_channel_chats is True

    async def test_a_partial_chosen_chat_leaves_the_rest_unset(self):
        written = await self.written(
            text="Pick",
            switch_inline_query_chosen_chat=types.SwitchInlineQueryChosenChat(
                allow_channel_chats=True
            )
        )
        parsed = types.InlineKeyboardButton.read(written).switch_inline_query_chosen_chat

        assert parsed.allow_channel_chats is True
        assert parsed.allow_user_chats is None
        assert parsed.allow_group_chats is None

    async def test_the_existing_switch_buttons_are_unchanged(self):
        plain = await self.written(text="x", switch_inline_query="q")

        assert isinstance(plain.type, raw.types.InlineButtonTypeSwitchInline)
        assert not plain.type.peer_types

        same_peer = raw.types.KeyboardInlineButton(
            text="x",
            type=raw.types.InlineButtonTypeSwitchInline(
                query="q", same_peer=True
            )
        )

        assert types.InlineKeyboardButton.read(
            same_peer
        ).switch_inline_query_current_chat == "q"


def _raw_user(user_id, first_name):
    return raw.types.User(
        id=user_id, first_name=first_name, usernames=[], restriction_reason=[]
    )


def _ephemeral_message(*, out, peer_id=None):
    return raw.types.EphemeralMessage(
        id=11,
        from_id=raw.types.PeerUser(user_id=1),
        receiver_id=2,
        date=0,
        message="hi",
        out=out,
        peer_id=peer_id
    )


class TestEphemeralMessageWithoutAPeer:
    """Layer 229 made ephemeral.peer_id optional.

    An ephemeral message sent outside a chat carries no peer at all, and the
    chat parser prefers peer_id, so it resolved the chat off a None and handed
    back a Message whose chat was None.
    """

    users = {1: _raw_user(1, "Sender"), 2: _raw_user(2, "Receiver")}

    async def test_an_outgoing_message_is_a_chat_with_the_receiver(self):
        parsed = await types.Message._parse(
            Mock(), _ephemeral_message(out=True), self.users, {}
        )

        assert parsed.chat is not None, "a message with no peer still has a counterpart"
        assert parsed.chat.id == 2
        assert parsed.receiver_user.id == 2

    async def test_an_incoming_message_is_a_chat_with_the_sender(self):
        parsed = await types.Message._parse(
            Mock(), _ephemeral_message(out=False), self.users, {}
        )

        assert parsed.chat is not None
        assert parsed.chat.id == 1

    async def test_a_message_with_a_peer_still_uses_it(self):
        message = _ephemeral_message(out=True, peer_id=raw.types.PeerUser(user_id=1))
        parsed = await types.Message._parse(Mock(), message, self.users, {})

        assert parsed.chat.id == 1


class TestEphemeralCallbackQuery:
    """updateEphemeralBotCallbackQuery is new in layer 229.

    Without it a bot never sees a press on a button it attached to an ephemeral
    message, and its chat_instance is optional, so stringifying it unguarded
    yields the string "None".
    """

    async def test_the_dispatcher_routes_it(self):
        from pyrogram.dispatcher import Dispatcher

        assert raw.types.UpdateEphemeralBotCallbackQuery in Dispatcher.CALLBACK_QUERY_UPDATES

    async def test_it_parses_with_no_chat_instance(self):
        update = raw.types.UpdateEphemeralBotCallbackQuery(
            query_id=5,
            user_id=2,
            msg_id=11,
            data=b"payload",
            message=_ephemeral_message(out=False)
        )
        users = {1: _raw_user(1, "Sender"), 2: _raw_user(2, "Receiver")}

        parsed = await types.CallbackQuery._parse(Mock(), update, users, {})

        assert parsed.id == "5"
        assert parsed.data == "payload"
        assert parsed.chat_instance is None
        assert parsed.message.id == 11


class TestButtonTypeUnions:
    """Layer 229 moved every button's payload behind a type union.

    A reply button now carries ButtonType and an inline one InlineButtonType, so
    the fields the parsers used to read off the button itself moved one level
    down and the two families no longer share a row type.
    """

    @staticmethod
    async def written(**kwargs):
        return await types.InlineKeyboardButton(**kwargs).write(AsyncMock())

    async def test_an_inline_row_is_not_a_reply_row(self):
        markup = await types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="x", callback_data="d")]]
        ).write(AsyncMock())

        assert isinstance(markup.rows[0], raw.types.KeyboardInlineButtonRow), (
            "ReplyInlineMarkup takes KeyboardInlineButtonRow, and a KeyboardButtonRow "
            "there only fails when the request is serialised"
        )
        assert isinstance(markup.rows[0].buttons[0], raw.types.KeyboardInlineButton)

    async def test_a_button_with_no_action_is_disabled_rather_than_dropped(self):
        written = await self.written(text="x")

        assert isinstance(written.type, raw.types.InlineButtonTypeDisabled)
        assert types.InlineKeyboardButton.read(written).text == "x"

    async def test_login_url_round_trips_through_the_type_union(self):
        written = await self.written(
            text="Log in",
            login_url=types.LoginUrl(url="https://example.org", forward_text="go")
        )

        assert isinstance(written.type, raw.types.InputInlineButtonTypeUrlAuth)
        assert written.type.url == "https://example.org"
        assert written.type.fwd_text == "go"

        incoming = raw.types.KeyboardInlineButton(
            text="Log in",
            type=raw.types.InlineButtonTypeUrlAuth(
                url="https://example.org", fwd_text="go", button_id=3
            )
        )
        parsed = types.InlineKeyboardButton.read(incoming).login_url

        assert parsed.url == "https://example.org"
        assert parsed.forward_text == "go"
        assert parsed.button_id == 3

    def test_a_reply_button_keeps_its_text_beside_the_type(self):
        written = types.KeyboardButton(
            text="Pick users",
            request_users=types.KeyboardButtonRequestUsers(button_id=4, max_quantity=2)
        ).write()

        assert written.text == "Pick users"
        assert written.type.button_id == 4, (
            "button_id lives on the ButtonType now, not on the KeyboardButton"
        )
        assert types.KeyboardButton.read(written).request_users.button_id == 4


class TestSendGameSendOptions:
    """send_game exposed almost none of messages.sendMedia's send options.

    A widened signature proves nothing on its own; each argument has to appear on
    the raw request.
    """

    @staticmethod
    async def sent(**kwargs):
        from pyrogram.methods.bots.send_game import SendGame

        captured = {}

        async def invoke(query, *args, **kw):
            captured["query"] = query

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

        client = AsyncMock(spec=pyrogram.Client)
        client.invoke = invoke
        client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
        client.rnd_id = lambda: 1

        await SendGame.send_game(client, chat_id=1, game_short_name="g", **kwargs)

        return captured["query"]

    async def test_every_send_option_reaches_the_request(self):
        query = await self.sent(
            schedule_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
            repeat_period=3600,
            paid_message_star_count=5,
            background=True,
            clear_draft=True,
            update_stickersets_order=True,
            send_as=2,
            quick_reply_shortcut=7
        )

        assert query.schedule_date == 1893456000
        assert query.schedule_repeat_period == 3600
        assert query.allow_paid_stars == 5
        assert query.background is True
        assert query.clear_draft is True
        assert query.update_stickersets_order is True
        assert isinstance(query.send_as, raw.types.InputPeerSelf)
        assert query.quick_reply_shortcut.shortcut_id == 7

    async def test_omitting_them_sends_nothing(self):
        query = await self.sent()

        assert query.schedule_date is None
        assert query.send_as is None
        assert query.quick_reply_shortcut is None
        assert query.allow_paid_stars is None


class TestEditFamilySendOptions:
    """The editMessage family never exposed messages.editMessage's own options.

    A scheduled message can be rescheduled and a quick reply shortcut retargeted,
    but neither reached the request.
    """

    METHODS = {
        "stop_poll": "pyrogram.methods.messages.stop_poll:StopPoll",
        "edit_message_reply_markup":
            "pyrogram.methods.messages.edit_message_reply_markup:EditMessageReplyMarkup",
        "edit_message_checklist":
            "pyrogram.methods.messages.edit_message_checklist:EditMessageChecklist",
    }

    @staticmethod
    async def sent(dotted, name, **kwargs):
        import importlib

        module, cls = dotted.split(":")
        method = getattr(getattr(importlib.import_module(module), cls), name)
        captured = {}

        async def invoke(query, *args, **kw):
            captured["query"] = query
            captured.update(kw)

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

        client = AsyncMock()
        client.invoke = invoke
        client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
        client.parser.parse = AsyncMock(return_value={"message": "t", "entities": []})

        try:
            await method(client, chat_id=1, message_id=2, **kwargs)
        except Exception:
            # the fake reply carries no updates, so parsing the result fails; the
            # request has already been captured by then, and a request that never
            # happened still fails on the missing key
            pass

        return captured

    REQUIRED = {
        "edit_message_checklist": dict(
            checklist=types.InputChecklist(
                title="t", tasks=[types.InputChecklistTask(id=1, text="a")]
            )
        )
    }

    @pytest.mark.parametrize("name", sorted(METHODS))
    async def test_schedule_options_reach_the_request(self, name):
        captured = await self.sent(
            self.METHODS[name],
            name,
            schedule_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
            repeat_period=60,
            quick_reply_shortcut=9,
            **self.REQUIRED.get(name, {})
        )
        query = captured["query"]

        assert query.schedule_date == 1893456000
        assert query.schedule_repeat_period == 60
        assert query.quick_reply_shortcut_id == 9

    async def test_stop_poll_forwards_the_business_connection(self):
        captured = await self.sent(
            self.METHODS["stop_poll"], "stop_poll", business_connection_id="bc1"
        )

        assert captured["business_connection_id"] == "bc1"


class TestPinBusinessConnection:
    @pytest.mark.parametrize(
        "dotted,name",
        [
            ("pyrogram.methods.chats.pin_chat_message:PinChatMessage", "pin_chat_message"),
            ("pyrogram.methods.chats.unpin_chat_message:UnpinChatMessage", "unpin_chat_message"),
        ]
    )
    async def test_it_reaches_invoke(self, dotted, name):
        import importlib

        module, cls = dotted.split(":")
        method = getattr(getattr(importlib.import_module(module), cls), name)
        captured = {}

        async def invoke(query, *args, **kw):
            captured.update(kw)

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

        client = AsyncMock(spec=pyrogram.Client)
        client.invoke = invoke
        client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())

        await method(client, chat_id=1, message_id=2, business_connection_id="bc1")

        assert captured["business_connection_id"] == "bc1"


class TestQuizPollSerialises:
    """A quiz poll could not be sent at all.

    correct_answers is a Vector<int> of positions, which only resolves if the
    poll is created with inputPollAnswer. send_poll built pollAnswer instead -
    the read-back constructor, which carries its own option bytes - and every
    quiz came back from Telegram as QUIZ_CORRECT_ANSWER_INVALID.
    """

    @staticmethod
    async def sent(**kwargs):
        from pyrogram.methods.messages.send_poll import SendPoll

        captured = {}

        async def invoke(query, *args, **kw):
            captured["query"] = query

            return raw.types.Updates(updates=[], users=[], chats=[], date=0, seq=0)

        client = AsyncMock()
        client.invoke = invoke
        client.resolve_peer = AsyncMock(return_value=raw.types.InputPeerSelf())
        client.rnd_id = lambda: 1
        client.parser.parse = AsyncMock(return_value={"message": "q", "entities": []})

        await SendPoll.send_poll(client, chat_id=1, **kwargs)

        return captured["query"]

    async def test_a_single_correct_answer_serialises(self):
        query = await self.sent(
            question="Q?",
            options=["a", "b"],
            type=enums.PollType.QUIZ,
            correct_option_id=1,
            explanation="because"
        )

        assert query.media.correct_answers == [1]
        query.write()

    async def test_several_correct_answers_serialise(self):
        query = await self.sent(
            question="Q?",
            options=["a", "b"],
            type=enums.PollType.QUIZ,
            correct_option_ids=[0, 1]
        )

        assert query.media.correct_answers == [0, 1]
        query.write()

    async def test_options_are_built_for_creation(self):
        query = await self.sent(question="Q?", options=["a", "b"])

        answers = query.media.poll.answers

        assert all(
            isinstance(answer, raw.types.InputPollAnswer) for answer in answers
        ), "a poll being created sends inputPollAnswer, not the read-back pollAnswer"
        assert [answer.text.text for answer in answers] == ["a", "b"]
        query.write()

    async def test_description_and_its_media_reach_the_request(self):
        class Media:
            async def write(self, **kwargs):
                return raw.types.InputMediaEmpty()

        query = await self.sent(
            question="Q?",
            options=["a", "b"],
            description=types.FormattedText(text="described", entities=[]),
            description_media=Media(),
        )

        assert query.message == "described", "the poll description never left the client"
        assert isinstance(query.media.attached_media, raw.types.InputMediaEmpty), (
            "description_media was accepted and then dropped before SendMedia"
        )
        query.write()

    async def test_explanation_media_reaches_the_request(self):
        class Media:
            async def write(self, **kwargs):
                return raw.types.InputMediaEmpty()

        query = await self.sent(
            question="Q?",
            options=["a", "b"],
            type=enums.PollType.QUIZ,
            correct_option_id=0,
            explanation="because",
            explanation_media=Media(),
        )

        assert isinstance(query.media.solution_media, raw.types.InputMediaEmpty), (
            "explanation_media was accepted and then dropped before SendMedia"
        )
        query.write()


# ---------------------------------------------------------------------------
#  GiftAttribute._parse against every StarGiftAttribute constructor
# ---------------------------------------------------------------------------

async def test_gift_attribute_parses_an_attribute_without_a_rarity():
    """starGiftAttributeOriginalDetails is the one member carrying no rarity.

    Every other field in the constructor is read through ``getattr``; ``rarity``
    was read straight off the union, so the branch that handles original
    details raised AttributeError the moment anything routed one here.
    """
    attr = raw.types.StarGiftAttributeOriginalDetails(
        recipient_id=raw.types.PeerUser(user_id=1),
        date=0,
        sender_id=raw.types.PeerUser(user_id=2),
        message=raw.types.TextWithEntities(text="hi", entities=[]),
    )

    parsed = await types.GiftAttribute._parse(None, attr, {}, {})

    assert parsed.rarity is None
    assert parsed.type is enums.GiftAttributeType.ORIGINAL_DETAILS
    assert parsed.caption == "hi"


# ---------------------------------------------------------------------------
#  List.__repr__ representation
# ---------------------------------------------------------------------------

def test_a_list_of_plain_values_is_representable():
    assert repr(types.List([1, "two"])) == "pyrogram.types.List([1,'two'])"


def test_a_nested_list_is_representable():
    assert repr(types.List([types.List([1])])) == "pyrogram.types.List([pyrogram.types.List([1])])"


def test_an_object_still_reports_its_own_shape():
    username = types.Username(username="someone", active=True)

    assert repr(types.List([username])) == f"pyrogram.types.List([{username!r}])"
    assert "pyrogram.types.Username(" in repr(username)


# ---------------------------------------------------------------------------
#  Str surrogate pair indexing and slicing
# ---------------------------------------------------------------------------

_EMOJI_TEXT = "😀 250"


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        pytest.param(0, "😀", id="leading-half"),
        pytest.param(1, "😀", id="trailing-half"),
        pytest.param(2, " ", id="after-the-pair"),
        pytest.param(-1, "0", id="from-the-end"),
    ],
)
def test_an_index_inside_a_surrogate_pair_gives_the_whole_code_point(
    item: int,
    expected: str,
) -> None:
    assert MessageStr(_EMOJI_TEXT)[item] == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        pytest.param(slice(0, 1), "😀", id="leading-half-only"),
        pytest.param(slice(1, 2), "😀", id="trailing-half-only"),
        pytest.param(slice(0, 2), "😀", id="the-whole-pair"),
        pytest.param(slice(1, 3), "😀 ", id="opening-inside-the-pair"),
        pytest.param(slice(2, None), " 250", id="past-the-pair"),
        pytest.param(slice(None, None, -1), "052 😀", id="reversed"),
    ],
)
def test_a_slice_cutting_a_surrogate_pair_widens_to_the_whole_code_point(
    item: slice,
    expected: str,
) -> None:
    assert MessageStr(_EMOJI_TEXT)[item] == expected


def test_an_entity_offset_still_indexes_the_text_that_entity_marks() -> None:
    entity = types.MessageEntity(
        type=enums.MessageEntityType.BOLD,
        offset=3,
        length=4,
    )
    text = MessageStr("😀 bold").init([entity])

    assert text[entity.offset : entity.offset + entity.length] == "bold"
