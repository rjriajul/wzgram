from pyrogram import enums


def test_chat_type():
    ct = {m.value for m in enums.ChatType}
    assert "private" in ct
    assert "bot" in ct
    assert "group" in ct
    assert "supergroup" in ct
    assert "channel" in ct
    assert "forum" in ct


def test_parse_mode():
    assert enums.ParseMode.DEFAULT
    assert enums.ParseMode.MARKDOWN
    assert enums.ParseMode.HTML
    assert enums.ParseMode.DISABLED


def test_message_media_type():
    m = enums.MessageMediaType
    assert m.AUDIO
    assert m.DOCUMENT
    assert m.PHOTO
    assert m.STICKER
    assert m.VIDEO
    assert m.ANIMATION
    assert m.VIDEO_NOTE
    assert m.VOICE
    assert m.CONTACT
    assert m.GAME
    assert m.LOCATION
    assert m.POLL
    assert m.VENUE
    assert m.DICE
    assert m.WEB_PAGE


def test_message_entity_type():
    e = enums.MessageEntityType
    assert e.MENTION
    assert e.HASHTAG
    assert e.CASHTAG
    assert e.BOT_COMMAND
    assert e.URL
    assert e.EMAIL
    assert e.PHONE_NUMBER
    assert e.BOLD
    assert e.ITALIC
    assert e.UNDERLINE
    assert e.STRIKETHROUGH
    assert e.SPOILER
    assert e.CODE
    assert e.PRE
    assert e.BLOCKQUOTE
    assert e.TEXT_LINK
    assert e.TEXT_MENTION
    assert e.BANK_CARD
    assert e.CUSTOM_EMOJI
    assert e.UNKNOWN


def test_user_status():
    s = enums.UserStatus
    assert s.ONLINE
    assert s.OFFLINE
    assert s.RECENTLY
    assert s.LAST_WEEK
    assert s.LAST_MONTH
    assert s.LONG_AGO


def test_chat_action():
    a = enums.ChatAction
    assert a.TYPING
    assert a.UPLOAD_PHOTO
    assert a.RECORD_VIDEO
    assert a.UPLOAD_VIDEO
    assert a.RECORD_AUDIO
    assert a.UPLOAD_AUDIO
    assert a.UPLOAD_DOCUMENT
    assert a.CANCEL
    assert a.RECORD_VIDEO_NOTE
    assert a.UPLOAD_VIDEO_NOTE
    assert a.CHOOSE_STICKER


def test_chat_action_all_constructible():
    # mirrors send_chat_action: every member must build with no caller-supplied data
    for m in enums.ChatAction:
        name = m.name.lower()
        m.value(progress=0) if "upload" in name or "history" in name else m.value()


def test_chat_member_status():
    s = enums.ChatMemberStatus
    assert s.OWNER
    assert s.ADMINISTRATOR
    assert s.MEMBER
    assert s.RESTRICTED
    assert s.LEFT
    assert s.BANNED


def test_chat_members_filter():
    f = enums.ChatMembersFilter
    assert f.SEARCH
    assert f.BANNED
    assert f.RESTRICTED
    assert f.BOTS
    assert f.RECENT
    assert f.ADMINISTRATORS


def test_poll_type():
    p = enums.PollType
    assert p.QUIZ
    assert p.REGULAR


def test_sticker_type():
    s = enums.StickerType
    assert s.REGULAR
    assert s.MASK
    assert s.CUSTOM_EMOJI


def test_messages_filter():
    f = enums.MessagesFilter
    assert f.EMPTY
    assert f.PHOTO
    assert f.VIDEO


def test_button_style():
    s = enums.ButtonStyle
    assert s.DEFAULT
    assert s.PRIMARY
    assert s.DANGER
    assert s.SUCCESS


def test_message_origin_type():
    o = enums.MessageOriginType
    assert o.USER
    assert o.HIDDEN_USER
    assert o.CHAT
    assert o.CHANNEL
    assert o.IMPORT


def test_chat_type_values():
    ct = {m.value for m in enums.ChatType}
    assert "private" in ct
    assert "bot" in ct
    assert "group" in ct
    assert "supergroup" in ct
    assert "channel" in ct
    assert "forum" in ct


def test_poll_type_values():
    assert enums.PollType.QUIZ.value == "quiz"
    assert enums.PollType.REGULAR.value == "regular"


def test_chat_action_record():
    assert enums.ChatAction.RECORD_VIDEO
    assert enums.ChatAction.RECORD_AUDIO
    assert enums.ChatAction.RECORD_VIDEO_NOTE


def test_chat_member_status_distinct():
    s = enums.ChatMemberStatus
    assert s.OWNER != s.ADMINISTRATOR
    assert s.ADMINISTRATOR != s.MEMBER
    assert s.MEMBER != s.LEFT
    assert s.LEFT != s.BANNED


def test_business_schedule():
    assert enums.BusinessSchedule


def test_chat_event_action():
    a = enums.ChatEventAction
    assert a.UNKNOWN
    assert a.DESCRIPTION_CHANGED


def test_client_platform():
    p = enums.ClientPlatform
    assert p.ANDROID
    assert p.IOS


def test_phone_call_discard_reason():
    assert enums.PhoneCallDiscardReason


def test_paid_reaction_privacy():
    assert enums.PaidReactionPrivacy


def test_privacy_key():
    assert enums.PrivacyKey


def test_privacy_rule_type():
    assert enums.PrivacyRuleType


def test_sent_code_type():
    assert enums.SentCodeType


def test_next_code_type():
    assert enums.NextCodeType


def test_phone_number_code_type():
    assert enums.PhoneNumberCodeType


def test_message_service_type():
    assert enums.MessageServiceType


def test_block_list():
    assert enums.BlockList


def test_chat_join_type():
    assert enums.ChatJoinType


def test_chat_join_request_query_result():
    assert enums.ChatJoinRequestQueryResult


def test_media_area_type():
    assert enums.MediaAreaType


def test_mask_point_type():
    assert enums.MaskPointType


def test_payment_form_type():
    assert enums.PaymentFormType


def test_profile_tab():
    assert enums.ProfileTab


def test_top_chat_category():
    assert enums.TopChatCategory


def test_suggested_post_state():
    assert enums.SuggestedPostState


def test_suggested_post_refund_reason():
    assert enums.SuggestedPostRefundReason


def test_upgraded_gift_origin():
    assert enums.UpgradedGiftOrigin


def test_gift_type():
    assert enums.GiftType


def test_gift_attribute_type():
    assert enums.GiftAttributeType


def test_gift_for_resale_order():
    assert enums.GiftForResaleOrder


def test_gift_purchase_offer_state():
    assert enums.GiftPurchaseOfferState
