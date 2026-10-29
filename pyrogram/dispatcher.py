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

import asyncio
import contextvars
import inspect
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Dict, Optional, Tuple

import pyrogram
from pyrogram import utils
from pyrogram.handlers import (
    BusinessConnectionHandler,
    BusinessMessageHandler,
    CallbackQueryHandler,
    ChatBoostHandler,
    ChatJoinRequestHandler,
    ChatMemberUpdatedHandler,
    ChosenInlineResultHandler,
    DeletedBusinessMessagesHandler,
    DeletedMessagesHandler,
    EditedBusinessMessageHandler,
    EditedMessageHandler,
    ErrorHandler,
    GuestMessageHandler,
    Handler,
    InlineQueryHandler,
    ManagedBotUpdatedHandler,
    MessageGenerationStoppedHandler,
    MessageHandler,
    MessageReactionCountHandler,
    MessageReactionHandler,
    PollHandler,
    PreCheckoutQueryHandler,
    PurchasedPaidMediaHandler,
    RawUpdateHandler,
    ShippingQueryHandler,
    StoryHandler,
    TonWalletStateHandler,
    UserStatusHandler,
)
from pyrogram.raw.types import (
    UpdateBotBusinessConnect,
    UpdateBotCallbackQuery,
    UpdateBotChatBoost,
    UpdateBotChatInviteRequester,
    UpdateBotDeleteBusinessMessage,
    UpdateBotEditBusinessMessage,
    UpdateBotGuestChatQuery,
    UpdateBotInlineQuery,
    UpdateBotInlineSend,
    UpdateBotMessageReaction,
    UpdateBotMessageReactions,
    UpdateBotNewBusinessMessage,
    UpdateBotPrecheckoutQuery,
    UpdateBotPurchasedPaidMedia,
    UpdateBotShippingQuery,
    UpdateBusinessBotCallbackQuery,
    UpdateChannelParticipant,
    UpdateChatParticipant,
    UpdateDeleteChannelMessages,
    UpdateDeleteEphemeralMessages,
    UpdateDeleteMessages,
    UpdateEditChannelMessage,
    UpdateEditEphemeralMessage,
    UpdateEphemeralBotCallbackQuery,
    UpdateEditMessage,
    UpdateInlineBotCallbackQuery,
    UpdateManagedBot,
    UpdateMessagePoll,
    UpdateMessagePollVote,
    UpdateNewChannelMessage,
    UpdateNewEphemeralMessage,
    UpdateNewMessage,
    UpdateNewScheduledMessage,
    UpdateStory,
    UpdateChannelUserTyping,
    UpdateChatUserTyping,
    UpdateUserStatus,
    UpdateUserTyping,
    UpdateWalletState,
)

log = logging.getLogger(__name__)

_current_worker: "contextvars.ContextVar[Optional[Tuple]]" = contextvars.ContextVar(
    "wzgram_dispatch_worker", default=None
)


class Dispatcher:
    NEW_MESSAGE_UPDATES = (UpdateNewMessage, UpdateNewChannelMessage, UpdateNewScheduledMessage, UpdateNewEphemeralMessage)
    EDIT_MESSAGE_UPDATES = (UpdateEditMessage, UpdateEditChannelMessage, UpdateEditEphemeralMessage)
    DELETE_MESSAGES_UPDATES = (UpdateDeleteMessages, UpdateDeleteChannelMessages, UpdateDeleteEphemeralMessages)
    CALLBACK_QUERY_UPDATES = (UpdateBotCallbackQuery, UpdateInlineBotCallbackQuery, UpdateBusinessBotCallbackQuery,
                              UpdateEphemeralBotCallbackQuery)
    CHAT_MEMBER_UPDATES = (UpdateChatParticipant, UpdateChannelParticipant)
    USER_STATUS_UPDATES = (UpdateUserStatus,)
    TYPING_UPDATES = (UpdateUserTyping, UpdateChatUserTyping, UpdateChannelUserTyping)
    BOT_INLINE_QUERY_UPDATES = (UpdateBotInlineQuery,)
    POLL_UPDATES = (UpdateMessagePoll, UpdateMessagePollVote)
    CHOSEN_INLINE_RESULT_UPDATES = (UpdateBotInlineSend,)
    CHAT_JOIN_REQUEST_UPDATES = (UpdateBotChatInviteRequester,)
    NEW_STORY_UPDATES = (UpdateStory,)
    PRE_CHECKOUT_QUERY_UPDATES = (UpdateBotPrecheckoutQuery,)
    SHIPPING_QUERY_UPDATES = (UpdateBotShippingQuery,)
    MESSAGE_REACTION_UPDATES = (UpdateBotMessageReaction,)
    MESSAGE_REACTION_COUNT_UPDATES = (UpdateBotMessageReactions,)
    CHAT_BOOST_UPDATES = (UpdateBotChatBoost,)
    PURCHASED_PAID_MEDIA_UPDATES = (UpdateBotPurchasedPaidMedia,)
    BUSINESS_CONNECTION_UPDATES = (UpdateBotBusinessConnect,)
    NEW_BUSINESS_MESSAGE_UPDATES = (UpdateBotNewBusinessMessage,)
    EDITED_BUSINESS_MESSAGE_UPDATES = (UpdateBotEditBusinessMessage,)
    DELETED_BUSINESS_MESSAGES_UPDATES = (UpdateBotDeleteBusinessMessage,)
    MANAGED_BOT_UPDATES = (UpdateManagedBot,)
    GUEST_MESSAGE_UPDATES = (UpdateBotGuestChatQuery,)
    TON_WALLET_STATE_UPDATES = (UpdateWalletState,)

    ENQUEUE_TIMEOUT = 5

    def __init__(self, client: "pyrogram.Client"):
        self.client = client

        self.handler_worker_tasks = []
        self.locks_list = []
        self._modify_lock = asyncio.Lock()

        self.updates_queue = asyncio.Queue(maxsize=256)
        self.groups = OrderedDict()

        self.listeners = getattr(client, "listeners", None)
        self.listener_types = {
            MessageHandler: pyrogram.enums.ListenerTypes.MESSAGE,
            CallbackQueryHandler: pyrogram.enums.ListenerTypes.CALLBACK_QUERY,
        }

        self.relief_workers = set()
        self.parked = 0
        self.relief_capped = False
        self.starting = False
        self.unread_warned = False

        async def message_parser(update, users, chats):
            return (
                await pyrogram.types.Message._parse(
                    self.client,
                    update.message,
                    users,
                    chats,
                    is_scheduled=isinstance(update, UpdateNewScheduledMessage),
                    replies=0 if getattr(update, "connection_id", None) else 1,
                    business_connection_id=getattr(update, "connection_id", None),
                    guest_query_id=getattr(update, "query_id", None),
                    raw_reply_to_message=getattr(update, "reply_to_message", None)
                ),
                MessageHandler
            )

        async def edited_message_parser(update, users, chats):
            parsed, _ = await message_parser(update, users, chats)

            return (
                parsed,
                EditedMessageHandler
            )

        async def deleted_messages_parser(update, users, chats):
            return (
                utils.parse_deleted_messages(self.client, update, users, chats),
                DeletedMessagesHandler,
            )

        async def callback_query_parser(update, users, chats):
            return (
                await pyrogram.types.CallbackQuery._parse(self.client, update, users, chats),
                CallbackQueryHandler
            )

        async def message_generation_stopped_parser(update, users, chats):
            stopped = pyrogram.types.MessageGenerationStopped._parse(
                self.client, update, users, chats
            )

            # typing updates carry every SendMessageAction, and only the stop one has a
            # handler; type(None) matches nothing, so the rest fall through to raw handlers
            if stopped is None:
                return None, type(None)

            return stopped, MessageGenerationStoppedHandler

        async def user_status_parser(update, users, chats):
            return (
                pyrogram.types.User._parse_user_status(self.client, update),
                UserStatusHandler
            )

        async def inline_query_parser(update, users, chats):
            return (
                pyrogram.types.InlineQuery._parse(self.client, update, users),
                InlineQueryHandler
            )

        async def poll_parser(update, users, chats):
            return (
                await pyrogram.types.Poll._parse_update(self.client, update, users, chats),
                PollHandler
            )

        async def chosen_inline_result_parser(update, users, chats):
            return (
                pyrogram.types.ChosenInlineResult._parse(self.client, update, users),
                ChosenInlineResultHandler
            )

        async def chat_member_updated_parser(update, users, chats):
            return (
                pyrogram.types.ChatMemberUpdated._parse(self.client, update, users, chats),
                ChatMemberUpdatedHandler
            )

        async def chat_join_request_parser(update, users, chats):
            return (
                pyrogram.types.ChatJoinRequest._parse(self.client, update, users, chats),
                ChatJoinRequestHandler
            )

        async def story_parser(update, users, chats):
            return (
                await pyrogram.types.Story._parse(self.client, update.story, update.peer, users, chats),
                StoryHandler
            )

        async def pre_checkout_query_parser(update, users, chats):
            return (
                await pyrogram.types.PreCheckoutQuery._parse(self.client, update, users),
                PreCheckoutQueryHandler
            )

        async def shipping_query_parser(update, users, chats):
            return (
                await pyrogram.types.ShippingQuery._parse(self.client, update, users),
                ShippingQueryHandler
            )

        async def message_reaction_parser(update, users, chats):
            return (
                pyrogram.types.MessageReactionUpdated._parse(self.client, update, users, chats),
                MessageReactionHandler
            )

        async def message_reaction_count_parser(update, users, chats):
            return (
                pyrogram.types.MessageReactionCountUpdated._parse(self.client, update, users, chats),
                MessageReactionCountHandler
            )

        async def chat_boost_parser(update, users, chats):
            return (
                pyrogram.types.ChatBoostUpdated._parse(self.client, update, users, chats),
                ChatBoostHandler
            )

        async def purchased_paid_media_parser(update, users, chats):
            return (
                pyrogram.types.PurchasedPaidMedia._parse(self.client, update, users),
                PurchasedPaidMediaHandler
            )

        async def business_connection_parser(update, users, chats):
            return (
                pyrogram.types.BusinessConnection._parse(self.client, update, users),
                BusinessConnectionHandler
            )

        async def business_message_parser(update, users, chats):
            parsed, _ = await message_parser(update, users, chats)

            return (
                parsed,
                BusinessMessageHandler
            )

        async def edited_business_message_parser(update, users, chats):
            parsed, _ = await message_parser(update, users, chats)

            return (
                parsed,
                EditedBusinessMessageHandler
            )

        async def deleted_business_messages_parser(update, users, chats):
            parsed, _ = await deleted_messages_parser(update, users, chats)

            return (
                parsed,
                DeletedBusinessMessagesHandler,
            )

        async def managed_bot_parser(update, users, chats):
            return (
                await pyrogram.types.ManagedBotUpdated._parse(self.client, update, users),
                ManagedBotUpdatedHandler
            )

        async def guest_message_parser(update, users, chats):
            for ref in update.reference_messages or []:
                await pyrogram.types.Message._parse(self.client, ref, users, chats)
            parsed, _ = await message_parser(update, users, chats)

            return (
                parsed,
                GuestMessageHandler
            )

        async def ton_wallet_state_parser(update, users, chats):
            return (
                pyrogram.types.TonWalletState._parse(update.state),
                TonWalletStateHandler
            )

        self.update_parsers = {
            Dispatcher.NEW_MESSAGE_UPDATES: message_parser,
            Dispatcher.EDIT_MESSAGE_UPDATES: edited_message_parser,
            Dispatcher.DELETE_MESSAGES_UPDATES: deleted_messages_parser,
            Dispatcher.CALLBACK_QUERY_UPDATES: callback_query_parser,
            Dispatcher.USER_STATUS_UPDATES: user_status_parser,
            Dispatcher.TYPING_UPDATES: message_generation_stopped_parser,
            Dispatcher.BOT_INLINE_QUERY_UPDATES: inline_query_parser,
            Dispatcher.POLL_UPDATES: poll_parser,
            Dispatcher.CHOSEN_INLINE_RESULT_UPDATES: chosen_inline_result_parser,
            Dispatcher.CHAT_MEMBER_UPDATES: chat_member_updated_parser,
            Dispatcher.CHAT_JOIN_REQUEST_UPDATES: chat_join_request_parser,
            Dispatcher.NEW_STORY_UPDATES: story_parser,
            Dispatcher.PRE_CHECKOUT_QUERY_UPDATES: pre_checkout_query_parser,
            Dispatcher.SHIPPING_QUERY_UPDATES: shipping_query_parser,
            Dispatcher.MESSAGE_REACTION_UPDATES: message_reaction_parser,
            Dispatcher.MESSAGE_REACTION_COUNT_UPDATES: message_reaction_count_parser,
            Dispatcher.CHAT_BOOST_UPDATES: chat_boost_parser,
            Dispatcher.PURCHASED_PAID_MEDIA_UPDATES: purchased_paid_media_parser,
            Dispatcher.BUSINESS_CONNECTION_UPDATES: business_connection_parser,
            Dispatcher.NEW_BUSINESS_MESSAGE_UPDATES: business_message_parser,
            Dispatcher.EDITED_BUSINESS_MESSAGE_UPDATES: edited_business_message_parser,
            Dispatcher.DELETED_BUSINESS_MESSAGES_UPDATES: deleted_business_messages_parser,
            Dispatcher.MANAGED_BOT_UPDATES: managed_bot_parser,
            Dispatcher.GUEST_MESSAGE_UPDATES: guest_message_parser,
            Dispatcher.TON_WALLET_STATE_UPDATES: ton_wallet_state_parser,
        }

        self.update_parsers = {key: value for key_tuple, value in self.update_parsers.items() for key in key_tuple}

    async def enqueue_update(self, update, users, chats) -> bool:
        """Hand an update to the workers, waiting for room. Returns False if dropped."""
        try:
            self.updates_queue.put_nowait((update, users, chats))
            return True
        except asyncio.QueueFull:
            pass

        if not self.handler_worker_tasks and not self.starting:
            if not self.unread_warned:
                self.unread_warned = True
                log.warning(
                    "Dropping updates: no handler worker is running to read them. "
                    "Start the client with `start()` and `workers` above 0, or pass "
                    "`no_updates=True` to stop receiving them."
                )

            return False

        try:
            await asyncio.wait_for(
                self.updates_queue.put((update, users, chats)),
                self.ENQUEUE_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.warning(
                "Dropping %s update after %ss: handlers cannot keep up with the "
                "update rate (queue size %s). Consider raising `workers` or "
                "moving slow work off the handler.",
                type(update).__name__, self.ENQUEUE_TIMEOUT, self.updates_queue.maxsize
            )
            return False
        else:
            return True

    async def start(self):
        self.starting = True
        self.unread_warned = False

        try:
            if callable(self.client.start_handler):
                try:
                    await self.client.start_handler(self.client)
                except Exception as e:
                    log.exception(e)

            if not self.client.no_updates:
                for i in range(self.client.workers):
                    self.locks_list.append(asyncio.Lock())

                    self.handler_worker_tasks.append(
                        self.client.loop.create_task(self.handler_worker(self.locks_list[-1]))
                    )

                log.info("Started %s HandlerTasks", self.client.workers)

                if not self.client.skip_updates:
                    await self.client.recover_gaps()
        finally:
            self.starting = False

    def prune_workers(self):
        self.handler_worker_tasks = [
            t for t in self.handler_worker_tasks if not t.done()
        ]

    async def stop(self, clear_handlers: bool = True):
        if callable(self.client.stop_handler):
            try:
                await self.client.stop_handler(self.client)
            except Exception as e:
                log.exception(e)

        if not self.client.no_updates:
            self.parked = 0

            for i in range(self.client.workers + len(self.relief_workers)):
                try:
                    self.updates_queue.put_nowait(None)
                except asyncio.QueueFull:
                    try:
                        await asyncio.wait_for(
                            self.updates_queue.put(None), self.ENQUEUE_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        log.warning(
                            "Updates queue still full during stop; "
                            "cancelling remaining handler workers"
                        )
                        break

            for i in [*self.handler_worker_tasks, *self.relief_workers]:
                try:
                    await asyncio.wait_for(i, timeout=10)
                except asyncio.TimeoutError:
                    log.warning("Handler worker task timed out during stop")
                    i.cancel()
                    try:
                        await i
                    except asyncio.CancelledError:
                        pass
                except Exception:
                    pass

            # a sentinel a cancelled worker never took retires a worker of the
            # next generation the instant it starts, and parsed updates left
            # here hold their peer graphs for as long as the client lives
            while not self.updates_queue.empty():
                try:
                    self.updates_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            self.relief_workers.clear()
            self.relief_capped = False
            self.locks_list.clear()
            self.handler_worker_tasks.clear()

            if clear_handlers:
                self.groups.clear()

            log.info("Stopped %s HandlerTasks", self.client.workers)

    @asynccontextmanager
    async def _barrier(self):
        """Hold every worker lock while the handler groups are edited.

        Releases exactly what it acquired: ``locks_list`` is rebuilt on every
        dispatcher start and cleared on stop, so releasing whatever the list
        holds at the end can either release a lock this never took or, worse,
        leave one held and stop the workers for good.
        """
        acquired = []

        try:
            for lock in list(self.locks_list):
                await lock.acquire()
                acquired.append(lock)

            yield
        except Exception as e:
            log.exception("Failed to edit handlers: %s", e)
        finally:
            for lock in acquired:
                lock.release()

    def add_handler(self, handler: Handler, group: int):
        async def fn():
            async with self._barrier():
                if group not in self.groups:
                    self.groups[group] = []
                    self.groups = OrderedDict(sorted(self.groups.items()))

                if handler not in self.groups[group]:
                    self.groups[group].append(handler)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if group not in self.groups:
                self.groups[group] = []
                self.groups = OrderedDict(sorted(self.groups.items()))
            if handler not in self.groups[group]:
                self.groups[group].append(handler)
        else:
            utils.run_in_background(fn(), loop)

    def remove_handler(self, handler: Handler, group: int):
        async def fn():
            async with self._barrier():
                if group not in self.groups:
                    raise ValueError(
                        f"Group {group} does not exist. Handler was not removed."
                    )

                self.groups[group].remove(handler)

                if not self.groups[group]:
                    del self.groups[group]

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if group in self.groups:
                self.groups[group].remove(handler)
                if not self.groups[group]:
                    del self.groups[group]
        else:
            utils.run_in_background(fn(), loop)

    def park(self, lock=None) -> bool:
        """Register that a handler worker is about to block on a listener.

        Handler callbacks are awaited inline in the worker, so a callback that
        waits for a reply holds its worker for the whole conversation. Left
        alone, the worker-th concurrent conversation exhausts the pool and no
        worker is left to deliver the very updates the parked ones are waiting
        for. Every parked worker is therefore covered one for one by a relief
        worker sharing its lock — the parked worker is not holding it, so
        ``locks_list`` never changes and the barrier in ``add_handler`` is
        untouched. Relief is not capped separately: parked workers cannot
        outnumber listeners, and those are already bounded process-wide.
        """
        if lock is None:
            entry = _current_worker.get()

            if entry is None or entry[0] is not self:
                return False

            lock = entry[1]

        self.parked += 1

        if not self.relief_capped and len(self.relief_workers) >= self.client.workers * 4:
            self.relief_capped = True
            log.warning(
                "%s conversations are parked inside handlers. They are covered, "
                "but a flow that waits this often is cheaper driven from its own "
                "task or from register_next_step_handler.",
                len(self.relief_workers)
            )

        relief = self.client.loop.create_task(self.handler_worker(lock, relief=True))

        # a retiring worker takes itself out, so the set never needs sweeping
        self.relief_workers.add(relief)
        relief.add_done_callback(self.relief_workers.discard)

        return True

    def unpark(self):
        if self.parked:
            self.parked -= 1

    async def handler_worker(self, lock, relief: bool = False):
        _current_worker.set((self, lock))

        while True:
            if relief and self.parked < len(self.relief_workers):
                break

            if self.client.rate_limiter is not None and not self.client.rate_limiter.is_closed:
                congestion = self.client.rate_limiter.congestion()
                if congestion > 0.8:
                    await asyncio.sleep(min(0.5, congestion * 2))

            packet = await self.updates_queue.get()

            if packet is None:
                break

            try:
                update, users, chats = packet
                parser = self.update_parsers.get(type(update), None)

                parsed_update, handler_type = (
                    await parser(update, users, chats)
                    if parser is not None
                    else (None, type(None))
                )

                consumed = False

                if self.listeners and parsed_update is not None:
                    listener_type = self.listener_types.get(handler_type)

                    if listener_type is not None:
                        consumed = await self.listeners.feed(
                            self.client, listener_type, parsed_update
                        )

                async with lock:
                    groups_snapshot = list(self.groups.items())

                for group, handlers in groups_snapshot:
                    for handler in handlers:
                        if isinstance(handler, ErrorHandler):
                            continue

                        args = None

                        if not consumed and isinstance(handler, handler_type):
                            try:
                                if await handler.check(self.client, parsed_update):
                                    args = (parsed_update,)
                            except Exception as e:
                                log.exception(e)
                                continue

                        elif isinstance(handler, RawUpdateHandler):
                            try:
                                if await handler.check(self.client, update):
                                    args = (update, users, chats)
                            except Exception as e:
                                log.exception(e)
                                continue

                        if args is None:
                            continue

                        try:
                            if inspect.iscoroutinefunction(handler.callback):
                                await handler.callback(self.client, *args)
                            else:
                                await self.client.loop.run_in_executor(
                                    self.client.executor,
                                    handler.callback,
                                    self.client,
                                    *args
                                )
                        except pyrogram.StopPropagation:
                            raise
                        except pyrogram.ContinuePropagation:
                            continue
                        except Exception as exc:
                            await self.handle_update_handler_exception(
                                exc, handler, update, users, chats, parsed_update
                            )

                        break
            except pyrogram.StopPropagation:
                pass
            except Exception as e:
                log.exception(e)

    async def handle_update_handler_exception(
        self,
        exc: Exception,
        update_handler: Handler,
        update: "pyrogram.raw.base.Update",
        users: Dict[int, "pyrogram.raw.base.User"],
        chats: Dict[int, "pyrogram.raw.base.Chat"],
        parsed_update: Optional["pyrogram.types.Update"] = None
    ) -> None:
        handled = False
        try:
            for group in self.groups.values():
                for handler in group:
                    if not isinstance(handler, ErrorHandler):
                        continue

                    if not isinstance(exc, handler.exceptions):
                        continue

                    try:
                        if not await handler.check(self.client, parsed_update):
                            continue
                    except Exception as e:
                        log.exception(e)
                        continue

                    try:
                        if inspect.iscoroutinefunction(handler.callback):
                            await handler.callback(
                                self.client, exc, update_handler, update, users, chats
                            )
                        else:
                            await self.client.loop.run_in_executor(
                                self.client.executor, handler.callback,
                                self.client, exc, update_handler, update, users, chats
                            )
                    except pyrogram.StopPropagation:
                        handled = True
                        raise
                    except pyrogram.ContinuePropagation:
                        handled = True
                        continue
                    except Exception:
                        log.exception("Error handler raised an exception:")
                    else:
                        handled = True

                    break
        except pyrogram.StopPropagation:
            pass
        finally:
            if not handled:
                log.error(
                    f"Unexpected exception raised in {type(update_handler).__name__}:",
                    exc_info=(type(exc), exc, exc.__traceback__)
                )
