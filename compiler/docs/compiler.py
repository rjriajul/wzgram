#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

import ast
import os
import re
import shutil

from pyrogram import types as pyrogram_types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = os.path.join(ROOT, "compiler/docs")
DESTINATION = os.path.join(ROOT, "docs/source/telegram")
PYROGRAM_API_DEST = os.path.join(ROOT, "docs/source/api")

FUNCTIONS_PATH = os.path.join(ROOT, "pyrogram/raw/functions")
TYPES_PATH = os.path.join(ROOT, "pyrogram/raw/types")
BASE_PATH = os.path.join(ROOT, "pyrogram/raw/base")

FUNCTIONS_BASE = "functions"
TYPES_BASE = "types"
BASE_BASE = "base"


def snek(s: str):
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def generate(source_path, base):
    all_entities = {}

    def build(path, level=0):
        last = os.path.basename(path)

        for i in os.listdir(path):
            child = os.path.join(path, i)
            try:
                if not i.startswith("__"):
                    build(child, level=level + 1)
            except NotADirectoryError:
                with open(child, encoding="utf-8") as f:
                    p = ast.parse(f.read())

                for node in ast.walk(p):
                    if isinstance(node, ast.ClassDef):
                        name = node.name
                        break
                else:
                    continue

                full_path = os.path.basename(path) + "/" + snek(name).replace("_", "-") + ".rst"

                if level:
                    full_path = base + "/" + full_path

                namespace = os.path.basename(path)
                if namespace in ["base", "types", "functions"]:
                    namespace = ""

                full_name = f"{(namespace + '.') if namespace else ''}{name}"

                os.makedirs(os.path.dirname(os.path.join(DESTINATION, full_path)), exist_ok=True)

                with open(os.path.join(DESTINATION, full_path), "w", encoding="utf-8") as f:
                    f.write(
                        page_template.format(
                            title=full_name,
                            title_markup="=" * len(full_name),
                            full_class_path="pyrogram.raw.{}".format(
                                ".".join(full_path.split("/")[:-1]) + "." + name
                            )
                        )
                    )

                if last not in all_entities:
                    all_entities[last] = []

                all_entities[last].append(name)

    build(source_path)

    for k, v in sorted(all_entities.items()):
        v = sorted(v)
        entities = []

        for i in v:
            entities.append(f'{i} <{snek(i).replace("_", "-")}>')

        if k != base:
            inner_path = base + "/" + k + "/index" + ".rst"
            module = "pyrogram.raw.{}.{}".format(base, k)
        else:
            for i in sorted(list(all_entities), reverse=True):
                if i != base:
                    entities.insert(0, "{0}/index".format(i))

            inner_path = base + "/index" + ".rst"
            module = "pyrogram.raw.{}".format(base)

        with open(os.path.join(DESTINATION, inner_path), "w", encoding="utf-8") as f:
            if k == base:
                f.write(":tocdepth: 1\n\n")
                k = "Raw " + k

            f.write(
                toctree.format(
                    title=k.title(),
                    title_markup="=" * len(k),
                    module=module,
                    entities="\n    ".join(entities)
                )
            )

            f.write("\n")


def pyrogram_api():
    def get_title_list(s: str) -> list:
        return [i.strip() for i in [j.strip() for j in s.split("\n") if j] if i]

    def is_property(bound_method: str) -> bool:
        cls_name, _, attr = bound_method.partition(".")
        return isinstance(getattr(getattr(pyrogram_types, cls_name, None), attr, None), property)

    # Methods

    categories = dict(
        account="""
        Account
            add_profile_audio
            get_account_ttl
            get_global_privacy_settings
            get_privacy
            remove_profile_audio
            set_account_ttl
            set_global_privacy_settings
            set_inactive_session_ttl
            set_privacy
            set_profile_audio_position
        """,
        advanced="""
        Advanced
            get_session
            invoke
            recover_gaps
            resolve_peer
            save_file
            set_dc
        """,
        auth="""
        Authorization
            accept_terms_of_service
            change_phone_number
            check_password
            connect
            disconnect
            get_active_sessions
            get_password_hint
            initialize
            log_out
            recover_password
            resend_code
            resend_phone_number_code
            reset_session
            reset_sessions
            send_code
            send_phone_number_code
            send_recovery_code
            sign_in
            sign_in_bot
            sign_up
            terminate
        """,
        bots="""
        Bots
            allow_bot_send_message
            answer_callback_query
            answer_chat_join_request_query
            answer_guest_query
            answer_inline_query
            answer_pre_checkout_query
            answer_shipping_query
            answer_web_app_query
            can_bot_send_message
            check_bot_username
            create_bot
            create_invoice_link
            delete_bot_commands
            edit_user_star_subscription
            get_admined_bots
            get_bot_commands
            get_bot_default_privileges
            get_bot_info
            get_bot_info_description
            get_bot_info_short_description
            get_bot_name
            get_chat_menu_button
            get_game_high_scores
            get_inline_bot_results
            get_managed_bot_access_settings
            get_managed_bot_token
            get_owned_bots
            refund_star_payment
            replace_managed_bot_token
            request_callback_answer
            send_chat_join_request_web_app
            send_game
            send_inline_bot_result
            send_invoice
            set_bot_commands
            set_bot_default_privileges
            set_bot_info_description
            set_bot_info_short_description
            set_bot_name
            set_chat_menu_button
            set_game_score
            set_managed_bot_access_settings
        """,
        business="""
        Business
            create_business_chat_link
            delete_business_chat_link
            delete_business_messages
            get_business_account_gifts
            get_business_account_star_balance
            get_business_chat_links
            get_business_connection
            get_connected_bots
            resolve_business_chat_link
            transfer_business_account_stars
            update_business_away_message
            update_business_greeting_message
            update_business_intro
            update_business_location
            update_business_work_hours
        """,
        chats="""
        Chats
            add_chat_members
            archive_chats
            ban_chat_member
            close_forum_topic
            close_general_forum_topic
            create_channel
            create_forum_topic
            create_group
            create_supergroup
            delete_all_message_reactions
            delete_channel
            delete_chat_photo
            delete_forum_topic
            delete_message_reaction
            delete_supergroup
            delete_user_history
            edit_forum_topic
            edit_general_forum_topic
            get_chat
            get_chat_event_log
            get_chat_member
            get_chat_members
            get_chat_members_count
            get_chat_online_count
            get_chat_settings
            get_dialogs
            get_dialogs_count
            get_direct_messages_topics
            get_direct_messages_topics_by_id
            get_forum_topics
            get_forum_topics_by_id
            get_nearby_chats
            get_personal_channels
            get_send_as_chats
            get_similar_channels
            get_suitable_discussion_chats
            get_top_chats
            hide_general_forum_topic
            join_chat
            leave_chat
            mark_chat_unread
            pin_chat_message
            pin_forum_topic
            promote_chat_member
            reopen_forum_topic
            reopen_general_forum_topic
            restrict_chat_member
            restrict_sponsored_messages
            set_administrator_title
            set_chat_accent_color
            set_upgraded_gift_colors
            set_chat_description
            set_chat_direct_messages_group
            set_chat_discussion_group
            set_chat_member_tag
            set_chat_permissions
            set_chat_photo
            set_chat_protected_content
            set_chat_title
            set_chat_ttl
            set_chat_username
            set_main_profile_tab
            set_send_as_chat
            set_slow_mode
            toggle_anti_spam
            toggle_auto_translation
            toggle_forum
            toggle_join_to_send
            toggle_participants_hidden
            toggle_pre_history_hidden
            toggle_signatures
            toggle_slow_mode
            toggle_view_forum_as_messages
            transfer_chat_ownership
            unarchive_chats
            unban_chat_member
            unhide_general_forum_topic
            unpin_all_chat_messages
            unpin_all_forum_topic_messages
            unpin_all_general_forum_topic_messages
            unpin_chat_message
            unpin_forum_topic
            update_channel_color
            update_chat_notifications
        """,
        contacts="""
        Contacts
            add_contact
            delete_contacts
            get_blocked_message_senders
            get_contacts
            get_contacts_count
            import_contacts
            search_contacts
            set_contact_note
        """,
        folders="""
        Folders
            check_chat_folder_invite_link
            create_folder
            create_folder_invite_link
            delete_folder
            delete_folder_invite_link
            edit_folder
            edit_folder_invite_link
            get_chats_for_folder_invite_link
            get_folder_invite_links
            get_folders
            join_folder
            leave_folder
            reorder_folders
            toggle_folder_tags
        """,
        invite_links="""
        Invite Links
            approve_all_chat_join_requests
            approve_chat_join_request
            create_chat_invite_link
            decline_all_chat_join_requests
            decline_chat_join_request
            delete_chat_admin_invite_links
            delete_chat_invite_link
            edit_chat_invite_link
            export_chat_invite_link
            get_chat_admin_invite_links
            get_chat_admin_invite_links_count
            get_chat_admins_with_invite_links
            get_chat_invite_link
            get_chat_invite_link_joiners
            get_chat_invite_link_joiners_count
            get_chat_join_requests
            revoke_chat_invite_link
        """,
        messages="""
        Messages
            add_checklist_tasks
            add_poll_option
            add_to_gifs
            approve_suggested_post
            compose_text_with_ai
            copy_media_group
            copy_message
            decline_suggested_post
            delete_chat_history
            delete_direct_messages_chat_topic_history
            delete_ephemeral_message
            get_welcome_messages
            delete_welcome_message
            delete_all_welcome_messages
            edit_ephemeral_message_text
            edit_ephemeral_message_caption
            edit_ephemeral_message_media
            edit_ephemeral_message_reply_markup
            delete_messages
            delete_participant_reaction
            delete_participant_reactions
            delete_poll_option
            delete_scheduled_messages
            download_media
            edit_fact_check
            edit_inline_caption
            edit_inline_media
            edit_inline_reply_markup
            edit_inline_text
            edit_message_caption
            edit_message_checklist
            edit_message_media
            edit_message_reply_markup
            edit_message_text
            fix_text_with_ai
            forward_media_group
            forward_messages
            get_available_effects
            get_chat_history
            get_chat_history_count
            get_custom_emoji_stickers
            get_direct_messages_chat_topic_history
            get_discussion_message
            get_discussion_replies
            get_discussion_replies_count
            get_main_web_app
            get_media_group
            get_messages
            get_poll_results
            get_poll_stats
            get_rich_message
            get_scheduled_messages
            get_stickers
            get_user_personal_chat_messages
            get_web_app_link_url
            get_web_app_url
            mark_checklist_tasks_as_done
            open_web_app
            read_chat_history
            read_mentions
            read_reactions
            retract_vote
            search_global
            search_global_count
            search_messages
            search_messages_count
            search_posts
            search_posts_count
            send_animation
            send_audio
            send_cached_media
            send_chat_action
            send_checklist
            send_contact
            send_dice
            send_document
            send_ephemeral_message
            send_location
            send_media_group
            send_message
            send_message_draft
            send_live_photo
            send_paid_media
            send_paid_reaction
            send_photo
            send_poll
            send_reaction
            send_rich_message
            send_rich_message_draft
            send_scheduled_messages
            send_screenshot_notification
            send_sticker
            send_venue
            send_video
            send_video_note
            send_voice
            set_direct_messages_chat_topic_is_marked_as_unread
            start_bot
            stop_poll
            stream_media
            summarize_text
            translate_text
            view_messages
            vote_poll
        """,
        stickers="""
        Stickers
            add_favorite_sticker
            add_recent_sticker
            add_sticker_to_set
            change_sticker_set
            clear_recent_stickers
            create_new_sticker_set
            delete_sticker_from_set
            delete_sticker_set
            get_favorite_stickers
            get_owned_sticker_sets
            get_recent_stickers
            get_sticker_set
            get_suggested_sticker_set_name
            remove_favorite_sticker
            remove_recent_sticker
            reorder_installed_sticker_sets
            replace_sticker_in_set
            search_sticker_sets
            search_stickers
            set_custom_emoji_sticker_set_thumbnail
            set_sticker_emoji_list
            set_sticker_keywords
            set_sticker_mask_position
            set_sticker_position_in_set
            set_sticker_set_thumbnail
            set_sticker_set_title
            upload_sticker_file
        """,
        password="""
        Password
            change_cloud_password
            enable_cloud_password
            remove_cloud_password
        """,
        payments="""
        Payments
            add_collection_gifts
            apply_gift_code
            buy_gift_upgrade
            check_gift_code
            convert_gift_to_stars
            craft_gift
            create_gift_collection
            delete_gift
            delete_gift_collection
            drop_gift_original_details
            edit_star_subscription
            get_available_gifts
            get_chat_gifts
            get_chat_gifts_count
            get_gift_auction_state
            get_gift_collections
            get_gift_upgrade_preview
            get_gift_upgrade_variants
            get_gifts_for_crafting
            get_payment_form
            get_stars_balance
            get_ton_balance
            get_upgraded_gift
            get_upgraded_gift_value_info
            gift_premium_with_stars
            hide_gift
            increase_gift_auction_bid
            place_gift_auction_bid
            process_gift_purchase_offer
            remove_collection_gifts
            reorder_collection_gifts
            reorder_gift_collections
            reuse_star_subscription
            search_gifts_for_resale
            send_gift
            send_gift_purchase_offer
            send_payment_form
            send_resold_gift
            set_gift_collection_name
            set_gift_resale_price
            set_pinned_gifts
            show_gift
            suggest_birthday
            transfer_gift
            upgrade_gift
        """,
        phone="""
        Phone
            get_call_members
        """,
        premium="""
        Premium
            apply_boost
            get_boosts
            get_boosts_status
        """,
        stories="""
        Stories
            can_post_stories
            copy_story
            delete_stories
            edit_story_caption
            edit_story_media
            edit_story_privacy
            enable_stealth_mode
            forward_story
            get_all_stories
            get_archived_stories
            get_chat_stories
            get_pinned_stories
            get_stories
            get_story_views
            hide_chat_stories
            pin_chat_stories
            read_chat_stories
            send_story
            show_chat_stories
            unpin_chat_stories
            view_stories
        """,
        users="""
        Users
            block_user
            check_username
            delete_profile_photos
            get_chat_audios
            get_chat_audios_count
            get_chat_photos
            get_chat_photos_count
            get_common_chats
            get_default_emoji_statuses
            get_me
            get_users
            set_bot_profile_photo
            set_emoji_status
            set_personal_channel
            set_profile_photo
            set_username
            unblock_user
            update_birthday
            update_profile
            update_status
        """,
        listeners="""
        Listeners
            ask
            listen
            register_next_step_handler
            stop_listening
            wait_for_callback_query
            wait_for_message
        """,
        utilities="""
        Utilities
            add_handler
            export_session_string
            remove_handler
            restart
            run
            set_parse_mode
            start
            stop
            stop_transmission
        """,
        decorators="""
        Decorators
            on_business_connection
            on_business_message
            on_callback_query
            on_chat_boost
            on_chat_join_request
            on_chat_member_updated
            on_chosen_inline_result
            on_connect
            on_deleted_business_messages
            on_deleted_messages
            on_disconnect
            on_edited_business_message
            on_edited_message
            on_error
            on_guest_message
            on_inline_query
            on_managed_bot
            on_message
            on_message_generation_stopped
            on_message_reaction
            on_message_reaction_count
            on_poll
            on_pre_checkout_query
            on_purchased_paid_media
            on_raw_update
            on_shipping_query
            on_start
            on_stop
            on_story
            on_user_status
        """,
    )

    root = PYROGRAM_API_DEST

    shutil.rmtree(os.path.join(root, "methods"), ignore_errors=True)
    os.makedirs(os.path.join(root, "methods"), exist_ok=True)

    with open(os.path.join(HOME, "template/methods.rst")) as f:
        template = f.read()

    with open(os.path.join(root, "methods/index.rst"), "w") as f:
        fmt_keys = {}

        for k, v in categories.items():
            name, *methods = get_title_list(v)
            fmt_keys.update({k: "\n    ".join("{0} <{0}>".format(m) for m in methods)})

            for method in methods:
                with open(os.path.join(root, "methods/{}.rst".format(method)), "w") as f2:
                    title = "{}()".format(method)

                    f2.write(title + "\n" + "=" * len(title) + "\n\n")
                    f2.write(".. automethod:: pyrogram.Client.{}()".format(method))

            functions = ["idle", "compose"]

            for func in functions:
                with open(os.path.join(root, "methods/{}.rst".format(func)), "w") as f2:
                    title = "{}()".format(func)

                    f2.write(title + "\n" + "=" * len(title) + "\n\n")
                    f2.write(".. autofunction:: pyrogram.{}()".format(func))

        f.write(template.format(**fmt_keys))

    # Types

    categories = dict(
        user_and_chats="""
        Users & Chats
            User
            Chat
            ChatPreview
            ChatPhoto
            ChatMember
            ChatPermissions
            ChatPrivileges
            ChatLocation
            ChatInviteLink
            ChatAdminWithInviteLinks
            ChatEvent
            ChatEventFilter
            ChatMemberUpdated
            ChatJoinRequest
            ChatJoiner
            Dialog
            Restriction
            EmojiStatus
            Birthday
            BusinessConnection
            BusinessIntro
            BusinessRecipients
            BusinessWorkingHours
            BusinessWeeklyOpen
            ChatAdministratorRights
            ChatColor
            ChatJoinResult
            ChatSettings
            Folder
            FolderInviteLink
            FoundContacts
            GlobalPrivacySettings
            GroupCallMember
            HistoryCleared
            InviteLinkImporter
            PhoneCallEnded
            PhoneCallStarted
            PrivacyRule
            StoriesStealthMode
            UserRating
            AcceptedGiftTypes
            BotVerification
            BusinessBotRights
            ChatFolderInviteLinkInfo
            ChatFullInfo
            ChatJoinResultDeclined
            ChatJoinResultGuardBotApprovalRequired
            ChatJoinResultRequestSent
            ChatJoinResultSuccess
            Community
            CommunityChatAdded
            CommunityChatJoined
            CommunityChatRemoved
            FailedToAddMember
            Link
            Username
            VerificationStatus
        """,
        messages_media="""
        Messages & Media
            Message
            MessageEntity
            MessageGenerationStopped
            Photo
            Thumbnail
            Audio
            Document
            Animation
            Video
            Voice
            VideoNote
            Contact
            Location
            Venue
            Sticker
            StickerSet
            File
            Game
            WebPage
            Poll
            PollOption
            Dice
            Reaction
            VideoChatScheduled
            VideoChatStarted
            VideoChatEnded
            VideoChatMembersInvited
            WebAppData
            MessageReactions
            ChatReactions
            AvailableEffect
            BoostsStatus
            BusinessMessage
            ChatBackground
            ChatBoost
            Checklist
            ChecklistTask
            ChecklistTasksAdded
            ChecklistTasksDone
            ContactRegistered
            DirectMessagePriceChanged
            DirectMessagesTopic
            EphemeralMessageParameters
            ExternalReplyInfo
            FactCheck
            FormattedText
            ForumTopic
            ForumTopicClosed
            ForumTopicCreated
            ForumTopicEdited
            ForumTopicReopened
            GeneralForumTopicHidden
            GeneralForumTopicUnhidden
            Gift
            GiftAttribute
            GiftBackground
            GiftAuction
            GiftAuctionState
            GiftCollection
            GiftedPremium
            GiftedStars
            GiftedGrams
            Giveaway
            GiveawayCompleted
            GiveawayCreated
            GiveawayPrizeStars
            GiveawayWinners
            InputChecklistTask
            Invoice
            LinkPreviewOptions
            LivePhoto
            ManagedBotCreated
            MaskPosition
            MediaArea
            MessageContent
            MessageOrigin
            MessageOriginChannel
            MessageOriginChat
            MessageOriginHiddenUser
            MessageOriginImport
            MessageOriginUser
            MyBoost
            PaidMediaInfo
            PaidMediaPreview
            PaidMessagesPriceChanged
            PaidMessagesRefunded
            PaidReactor
            PaymentForm
            PaymentOption
            PollOptionAdded
            PollOptionDeleted
            PremiumGiftCode
            ProximityAlertTriggered
            RefundedPayment
            ReplyParameters
            RestrictionReason
            RichBlock
            RichMessage
            RichMessageButton
            RichText
            ScreenshotTaken
            StarAmount
            Story
            StoryView
            StrippedThumbnail
            SuggestedPostApprovalFailed
            SuggestedPostApproved
            SuggestedPostDeclined
            SuggestedPostInfo
            SuggestedPostPaid
            SuggestedPostParameters
            SuggestedPostPrice
            SuggestedPostRefunded
            TextQuote
            TonConnectRequest
            TonWalletTransfer
            UpgradedGiftAttributeId
            UpgradedGiftAttributeIdBackdrop
            UpgradedGiftAttributeIdModel
            UpgradedGiftAttributeIdSymbol
            UpgradedGiftAttributeRarity
            UpgradedGiftOriginalDetails
            UpgradedGiftPurchaseOffer
            UpgradedGiftValueInfo
            WriteAccessAllowed
            AuctionBid
            AuctionRound
            AuctionState
            AuctionStateActive
            AuctionStateFinished
            ChatHasProtectedContentDisableRequested
            ChatHasProtectedContentToggled
            ChatOwnerChanged
            ChatOwnerLeft
            ChatTheme
            CheckedGiftCode
            CraftGiftResult
            CraftGiftResultFail
            CraftGiftResultSuccess
            GiftPurchaseLimit
            GiftResaleParameters
            GiftResalePrice
            GiftResalePriceStar
            GiftResalePriceTon
            GiftUpgradePreview
            GiftUpgradePrice
            GiftUpgradeVariants
            PaymentResult
            PollStats
            RichBlockAnchor
            RichBlockAnimation
            RichBlockAudio
            RichBlockBlockQuotation
            RichBlockButtons
            RichBlockCaption
            RichBlockCollage
            RichBlockDetails
            RichBlockDivider
            RichBlockDocument
            RichBlockExpandableBlockQuotation
            RichBlockFooter
            RichBlockList
            RichBlockListItem
            RichBlockMap
            RichBlockMathematicalExpression
            RichBlockParagraph
            RichBlockPhoto
            RichBlockPreformatted
            RichBlockPullQuotation
            RichBlockSectionHeading
            RichBlockSlideshow
            RichBlockTable
            RichBlockTableCell
            RichBlockThinking
            RichBlockUnsupported
            RichBlockVideo
            RichBlockVoiceNote
            RichTextAnchor
            RichTextAnchorLink
            RichTextBankCardNumber
            RichTextBold
            RichTextButton
            RichTextBotCommand
            RichTextCashtag
            RichTextCode
            RichTextCustomEmoji
            RichTextDateTime
            RichTextDiff
            RichTextEmailAddress
            RichTextHashtag
            RichTextImage
            RichTextItalic
            RichTextMarked
            RichTextMathematicalExpression
            RichTextMention
            RichTextPhoneNumber
            RichTextReference
            RichTextReferenceLink
            RichTextSpoiler
            RichTextStrikethrough
            RichTextSubscript
            RichTextSuperscript
            RichTextTextMention
            RichTextTonAddress
            RichTextUnderline
            RichTextUrl
            SavedCredentials
            Str
            SuccessfulPayment
            SuggestedPostPriceStar
            SuggestedPostPriceTon
            UpgradedGiftAttributeRarityEpic
            UpgradedGiftAttributeRarityLegendary
            UpgradedGiftAttributeRarityPerMille
            UpgradedGiftAttributeRarityRare
            UpgradedGiftAttributeRarityUncommon
            UpgradedGiftPurchaseOfferRejected
        """,
        bots_and_keyboards="""
        Bot keyboards
            ReplyKeyboardMarkup
            KeyboardButton
            ReplyKeyboardRemove
            InlineKeyboardMarkup
            InlineKeyboardButton
            CopyTextButton
            DisabledButton
            SwitchInlineQueryChosenChat
            LoginUrl
            ForceReply
            CallbackQuery
            GameHighScore
            CallbackGame
            WebAppInfo
            MenuButton
            MenuButtonCommands
            MenuButtonWebApp
            MenuButtonDefault
            SentWebAppMessage
            BotCommand
            BotCommandScope
            BotCommandScopeDefault
            BotCommandScopeAllPrivateChats
            BotCommandScopeAllGroupChats
            BotCommandScopeAllChatAdministrators
            BotCommandScopeChat
            BotCommandScopeChatAdministrators
            BotCommandScopeChatMember
            BotAccessSettings
            ChatBoostUpdated
            ChatShared
            KeyboardButtonPollType
            KeyboardButtonRequestChat
            KeyboardButtonRequestManagedBot
            KeyboardButtonRequestUsers
            LabeledPrice
            ManagedBotUpdated
            MessageReactionCountUpdated
            MessageReactionUpdated
            OrderInfo
            PreCheckoutQuery
            PurchasedPaidMedia
            SentGuestMessage
            ShippingAddress
            ShippingOption
            ShippingQuery
            UsersShared
        """,
        inline_mode="""
        Inline Mode
            InlineQuery
            InlineQueryResult
            InlineQueryResultCachedAudio
            InlineQueryResultCachedDocument
            InlineQueryResultCachedAnimation
            InlineQueryResultCachedPhoto
            InlineQueryResultCachedSticker
            InlineQueryResultCachedVideo
            InlineQueryResultCachedVoice
            InlineQueryResultArticle
            InlineQueryResultAudio
            InlineQueryResultContact
            InlineQueryResultDocument
            InlineQueryResultAnimation
            InlineQueryResultLocation
            InlineQueryResultPhoto
            InlineQueryResultVenue
            InlineQueryResultVideo
            InlineQueryResultVoice
            ChosenInlineResult
        """,
        input_content="""
        Input Content
            InputMedia
            InputMediaPhoto
            InputMediaVideo
            InputMediaAudio
            InputMediaAnimation
            InputMediaDocument
            InputPhoneContact
            InputChatPhoto
            InputChecklist
            InputCredentials
            InputCredentialsApplePay
            InputCredentialsGooglePay
            InputCredentialsNew
            InputCredentialsSaved
            InputInvoice
            InputInvoiceMessage
            InputInvoiceMessageContent
            InputInvoiceName
            InputMediaLink
            InputMediaLivePhoto
            InputMediaLocation
            InputMediaSticker
            InputSticker
            InputMediaVenue
            InputMessageContent
            InputPollMedia
            InputPollOption
            InputPollOptionMedia
            InputPrivacyRule
            InputPrivacyRuleAllowAll
            InputPrivacyRuleAllowBots
            InputPrivacyRuleAllowChats
            InputPrivacyRuleAllowCloseFriends
            InputPrivacyRuleAllowContacts
            InputPrivacyRuleAllowPremium
            InputPrivacyRuleAllowUsers
            InputPrivacyRuleDisallowAll
            InputPrivacyRuleDisallowBots
            InputPrivacyRuleDisallowChats
            InputPrivacyRuleDisallowContacts
            InputPrivacyRuleDisallowUsers
            InputRichMessage
            InputRichMessageContent
            InputTextMessageContent
            InputContactMessageContent
            InputLocationMessageContent
            InputVenueMessageContent
            InputChatPhotoAnimation
            InputChatPhotoPrevious
            InputChatPhotoStatic
            InputMediaVoiceNote
            InputRichBlock
            InputRichBlockAnchor
            InputRichBlockAnimation
            InputRichBlockAudio
            InputRichBlockBlockQuotation
            InputRichBlockButtons
            InputRichBlockCollage
            InputRichBlockDetails
            InputRichBlockDivider
            InputRichBlockDocument
            InputRichBlockExpandableBlockQuotation
            InputRichBlockFooter
            InputRichBlockList
            InputRichBlockListItem
            InputRichBlockMap
            InputRichBlockMathematicalExpression
            InputRichBlockParagraph
            InputRichBlockPhoto
            InputRichBlockPreformatted
            InputRichBlockPullQuotation
            InputRichBlockSectionHeading
            InputRichBlockSlideshow
            InputRichBlockTable
            InputRichBlockTableCell
            InputRichBlockThinking
            InputRichBlockVideo
            InputRichBlockVoiceNote
            InputRichMessageMedia
        """,
        listeners="""
        Listeners
            Identifier
            Listener
        """,
        authorization="""
        Authorization
            SentCode
            TermsOfService
            ActiveSession
            ActiveSessions
            FirebaseAuthenticationSettings
            PhoneNumberAuthenticationSettings
            List
            FirebaseAuthenticationSettingsAndroid
            FirebaseAuthenticationSettingsIos
        """,
        enums="""
        Enums
            BlockAlignment
            BlockList
            BusinessSchedule
            ButtonStyle
            RichButtonStyle
            ChatAction
            ChatEventAction
            ChatJoinRequestQueryResult
            ListenerTypes
            ChatJoinType
            ChatMemberStatus
            ChatMembersFilter
            ChatType
            ClientPlatform
            FolderColor
            GiftAttributeType
            GiftForResaleOrder
            GiftPurchaseOfferState
            GiftType
            MaskPointType
            MediaAreaType
            MessageEntityType
            MessageMediaType
            MessageOriginType
            MessageServiceType
            MessagesFilter
            NextCodeType
            PaidReactionPrivacy
            ParseMode
            PaymentFormType
            PhoneCallDiscardReason
            PhoneNumberCodeType
            PollType
            PrivacyKey
            PrivacyRuleType
            ProfileColor
            ProfileTab
            ProxyScheme
            ReplyColor
            SentCodeType
            StickerType
            StickerFormat
            StoriesPrivacyRules
            SuggestedPostRefundReason
            SuggestedPostState
            TopChatCategory
            UpgradedGiftOrigin
            UserStatus
        """
    )

    root = PYROGRAM_API_DEST

    shutil.rmtree(os.path.join(root, "types"), ignore_errors=True)
    os.makedirs(os.path.join(root, "types"), exist_ok=True)

    with open(os.path.join(HOME, "template/types.rst")) as f:
        template = f.read()

    with open(os.path.join(root, "types/index.rst"), "w") as f:
        fmt_keys = {}

        for k, v in categories.items():
            name, *types = get_title_list(v)

            fmt_keys.update({k: "\n    ".join(types)})

            # noinspection PyShadowingBuiltins
            for type in types:
                with open(os.path.join(root, "types/{}.rst".format(type)), "w") as f2:
                    title = "{}".format(type)

                    f2.write(title + "\n" + "=" * len(title) + "\n\n")

                    if k == "enums":
                        f2.write(".. autoclass:: pyrogram.enums.{}()\n".format(type))
                        f2.write("    :members:\n")
                        f2.write("    :undoc-members:\n")
                    else:
                        f2.write(".. autoclass:: pyrogram.types.{}()\n".format(type))

        f.write(template.format(**fmt_keys))

    # Bound Methods

    categories = dict(
        message="""
        Message
            Message.click
            Message.delete
            Message.delete_ephemeral
            Message.edit_ephemeral_text
            Message.edit_ephemeral_caption
            Message.edit_ephemeral_media
            Message.edit_ephemeral_reply_markup
            Message.reply_ephemeral_text
            Message.download
            Message.forward
            Message.copy
            Message.copy_media_group
            Message.pin
            Message.unpin
            Message.edit
            Message.edit_text
            Message.edit_caption
            Message.edit_media
            Message.edit_reply_markup
            Message.reply
            Message.reply_text
            Message.reply_animation
            Message.reply_audio
            Message.reply_cached_media
            Message.reply_chat_action
            Message.reply_checklist
            Message.reply_contact
            Message.reply_dice
            Message.reply_document
            Message.reply_game
            Message.reply_inline_bot_result
            Message.reply_invoice
            Message.reply_live_photo
            Message.reply_location
            Message.reply_media_group
            Message.reply_paid_media
            Message.reply_photo
            Message.reply_poll
            Message.reply_rich
            Message.reply_sticker
            Message.reply_venue
            Message.reply_video
            Message.reply_video_note
            Message.reply_voice
            Message.answer
            Message.answer_animation
            Message.answer_audio
            Message.answer_cached_media
            Message.answer_checklist
            Message.answer_contact
            Message.answer_dice
            Message.answer_document
            Message.answer_game
            Message.answer_inline_bot_result
            Message.answer_invoice
            Message.answer_live_photo
            Message.answer_location
            Message.answer_media_group
            Message.answer_paid_media
            Message.answer_photo
            Message.answer_poll
            Message.answer_rich
            Message.answer_sticker
            Message.answer_venue
            Message.answer_video
            Message.answer_video_note
            Message.answer_voice
            Message.get_media_group
            Message.react
            Message.wait_for_click
            Message.read
            Message.view
            Message.vote
            Message.pay
            Message.retract_vote
            Message.edit_checklist
            Message.edit_live_location
            Message.stop_live_location
            Message.summarize
            Message.content
            Message.link
            Message.html_text
            Message.md_text
            Message.forward_date
            Message.forward_from
            Message.forward_from_chat
            Message.forward_from_message_id
            Message.forward_sender_name
            Message.forward_signature
            Message.is_topic_message
        """,
        chat="""
        Chat
            Chat.archive
            Chat.ask
            Chat.listen
            Chat.stop_listening
            Chat.unarchive
            Chat.set_title
            Chat.set_description
            Chat.set_photo
            Chat.ban_member
            Chat.unban_member
            Chat.restrict_member
            Chat.promote_member
            Chat.get_member
            Chat.get_members
            Chat.add_members
            Chat.join
            Chat.leave
            Chat.mark_unread
            Chat.set_protected_content
            Chat.unpin_all_messages
            Chat.mute
            Chat.unmute
            Chat.set_ttl
            Chat.export_invite_link
            Chat.full_name
            Chat.is_fake
            Chat.is_scam
            Chat.is_verified
        """,
        user="""
        User
            User.archive
            User.unarchive
            User.block
            User.unblock
            User.full_name
            User.is_fake
            User.is_scam
            User.is_verified
            User.mention
            User.get_common_chats
        """,
        callback_query="""
        Callback Query
            CallbackQuery.answer
            CallbackQuery.edit_message_text
            CallbackQuery.edit_message_caption
            CallbackQuery.edit_message_media
            CallbackQuery.edit_message_reply_markup
        """,
        inline_query="""
        InlineQuery
            InlineQuery.answer
        """,
        chat_join_request="""
        ChatJoinRequest
            ChatJoinRequest.approve
            ChatJoinRequest.decline
        """,
        story="""
        Story
            Story.copy
            Story.delete
            Story.download
            Story.edit_caption
            Story.edit_media
            Story.edit_privacy
            Story.forward
            Story.link
            Story.react
            Story.read
            Story.view
            Story.reply_text
            Story.reply_animation
            Story.reply_audio
            Story.reply_cached_media
            Story.reply_media_group
            Story.reply_photo
            Story.reply_sticker
            Story.reply_video
            Story.reply_video_note
            Story.reply_voice
        """,
        gift="""
        Gift
            Gift.buy
            Gift.send
            Gift.transfer
            Gift.upgrade
            Gift.convert
            Gift.hide
            Gift.show
            Gift.link
            Gift.wear
            Gift.owned_gift_id
            Gift.send_purchase_offer
            Gift.get_auction_state
        """,
        poll="""
        Poll
            Poll.get_vote_percentage
        """,
        pre_checkout_query="""
        PreCheckoutQuery
            PreCheckoutQuery.answer
        """,
        shipping_query="""
        ShippingQuery
            ShippingQuery.answer
        """,
        folder="""
        Folder
            Folder.create_invite_link
            Folder.delete
            Folder.edit
            Folder.exclude_chat
            Folder.include_chat
            Folder.pin_chat
            Folder.remove_chat
            Folder.update_color
        """
    )

    root = PYROGRAM_API_DEST

    shutil.rmtree(os.path.join(root, "bound-methods"), ignore_errors=True)
    os.makedirs(os.path.join(root, "bound-methods"), exist_ok=True)

    with open(os.path.join(HOME, "template/bound-methods.rst")) as f:
        template = f.read()

    with open(os.path.join(root, "bound-methods/index.rst"), "w") as f:
        fmt_keys = {}

        for k, v in categories.items():
            name, *bound_methods = get_title_list(v)

            fmt_keys.update({"{}_hlist".format(k): "\n    ".join(
                "- :{}:`~{}`".format("attr" if is_property(bm) else "meth", bm) for bm in bound_methods)})

            fmt_keys.update(
                {"{}_toctree".format(k): "\n    ".join("{} <{}>".format(bm.split(".")[1], bm) for bm in bound_methods)})

            # noinspection PyShadowingBuiltins
            for bm in bound_methods:
                with open(os.path.join(root, "bound-methods/{}.rst".format(bm)), "w") as f2:
                    if is_property(bm):
                        title, directive, suffix = bm, "autoattribute", ""
                    else:
                        title, directive, suffix = "{}()".format(bm), "automethod", "()"

                    f2.write(title + "\n" + "=" * len(title) + "\n\n")
                    f2.write(".. {}:: pyrogram.types.{}{}".format(directive, bm, suffix))

        f.write(template.format(**fmt_keys))


def start():
    global page_template
    global toctree

    shutil.rmtree(DESTINATION, ignore_errors=True)

    with open(os.path.join(HOME, "template/page.txt"), encoding="utf-8") as f:
        page_template = f.read()

    with open(os.path.join(HOME, "template/toctree.txt"), encoding="utf-8") as f:
        toctree = f.read()

    generate(TYPES_PATH, TYPES_BASE)
    generate(FUNCTIONS_PATH, FUNCTIONS_BASE)
    generate(BASE_PATH, BASE_BASE)
    pyrogram_api()


if "__main__" == __name__:
    start()
