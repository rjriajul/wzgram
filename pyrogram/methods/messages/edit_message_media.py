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

import io
import os
import re
from datetime import datetime
from typing import Optional, Tuple, Union

import pyrogram
from pyrogram import raw
from pyrogram import types
from pyrogram import utils
from pyrogram.file_id import FileType


async def resolve_input_media(
    client: "pyrogram.Client",
    chat_id: Union[int, str],
    media: "types.InputMedia",
    file_name: Optional[str] = None
) -> Tuple["raw.base.InputMedia", Optional[str], Optional[list]]:
    """The InputMedia an edit sends, uploading it first if it is a local file.

    edit_message_media and edit_ephemeral_message_media differ only in the RPC they
    hand this to, and it is two hundred lines of media handling either way.
    """

    caption = media.caption
    parse_mode = media.parse_mode

    message, entities = None, None

    if caption is not None:
        message, entities = (await client.parser.parse(caption, parse_mode)).values()

    if isinstance(media, types.InputMediaPhoto):
        if isinstance(media.media, io.BytesIO) or os.path.isfile(media.media):
            uploaded_media = await client.invoke(
                raw.functions.messages.UploadMedia(
                    peer=await client.resolve_peer(chat_id),
                    media=raw.types.InputMediaUploadedPhoto(
                        file=await client.save_file(media.media),
                        spoiler=media.has_spoiler
                    )
                )
            )

            media = raw.types.InputMediaPhoto(
                id=raw.types.InputPhoto(
                    id=uploaded_media.photo.id,
                    access_hash=uploaded_media.photo.access_hash,
                    file_reference=uploaded_media.photo.file_reference
                ),
                spoiler=media.has_spoiler
            )
        elif re.match("^https?://", media.media):
            media = raw.types.InputMediaPhotoExternal(
                url=media.media,
                spoiler=media.has_spoiler
            )
        else:
            media = utils.get_input_media_from_file_id(media.media, FileType.PHOTO)
    elif isinstance(media, types.InputMediaVideo):
        vcover_file = None
        vcover_media = None

        if media.video_cover is not None:
            if isinstance(media.video_cover, str):
                if os.path.isfile(media.video_cover):
                    vcover_media = await client.invoke(
                        raw.functions.messages.UploadMedia(
                            peer=await client.resolve_peer(chat_id),
                            media=raw.types.InputMediaUploadedPhoto(
                                file=await client.save_file(media.video_cover)
                            )
                        )
                    )
                elif re.match("^https?://", media.video_cover):
                    vcover_media = await client.invoke(
                        raw.functions.messages.UploadMedia(
                            peer=await client.resolve_peer(chat_id),
                            media=raw.types.InputMediaPhotoExternal(
                                url=media.video_cover
                            )
                        )
                    )
                else:
                    vcover_file = utils.get_input_media_from_file_id(media.video_cover, FileType.PHOTO).id
            else:
                vcover_media = await client.invoke(
                    raw.functions.messages.UploadMedia(
                        peer=await client.resolve_peer(chat_id),
                        media=raw.types.InputMediaUploadedPhoto(
                            file=await client.save_file(media.video_cover)
                        )
                    )
                )

            if vcover_media:
                vcover_file = raw.types.InputPhoto(
                    id=vcover_media.photo.id,
                    access_hash=vcover_media.photo.access_hash,
                    file_reference=vcover_media.photo.file_reference
                )

        if isinstance(media.media, io.BytesIO) or os.path.isfile(media.media):
            uploaded_media = await client.invoke(
                raw.functions.messages.UploadMedia(
                    peer=await client.resolve_peer(chat_id),
                    media=raw.types.InputMediaUploadedDocument(
                        mime_type=client.guess_mime_type(media.media) or "video/mp4",
                        thumb=await client.save_file(media.thumb),
                        spoiler=media.has_spoiler,
                        file=await client.save_file(media.media),
                        video_cover=vcover_file,
                        video_timestamp=media.video_start_timestamp,
                        attributes=[
                            raw.types.DocumentAttributeVideo(
                                supports_streaming=media.supports_streaming or None,
                                duration=media.duration,
                                w=media.width,
                                h=media.height
                            ),
                            raw.types.DocumentAttributeFilename(
                                file_name=utils.get_file_name(
                                    media.media,
                                    file_name=file_name or media.file_name,
                                    fallback="video.mp4",
                                )
                            )
                        ]
                    )
                )
            )

            media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(
                    id=uploaded_media.document.id,
                    access_hash=uploaded_media.document.access_hash,
                    file_reference=uploaded_media.document.file_reference
                ),
                spoiler=media.has_spoiler,
                video_cover=vcover_file,
                video_timestamp=media.video_start_timestamp
            )
        elif re.match("^https?://", media.media):
            media = raw.types.InputMediaDocumentExternal(
                url=media.media,
                spoiler=media.has_spoiler,
                video_cover=vcover_file,
                video_timestamp=media.video_start_timestamp
            )
        else:
            media = utils.get_input_media_from_file_id(
                media.media, FileType.VIDEO,
                video_cover=vcover_file,
                video_start_timestamp=media.video_start_timestamp
            )
    elif isinstance(media, types.InputMediaAudio):
        if isinstance(media.media, io.BytesIO) or os.path.isfile(media.media):
            media = await client.invoke(
                raw.functions.messages.UploadMedia(
                    peer=await client.resolve_peer(chat_id),
                    media=raw.types.InputMediaUploadedDocument(
                        mime_type=client.guess_mime_type(media.media) or "audio/mpeg",
                        thumb=await client.save_file(media.thumb),
                        file=await client.save_file(media.media),
                        attributes=[
                            raw.types.DocumentAttributeAudio(
                                duration=media.duration,
                                performer=media.performer,
                                title=media.title
                            ),
                            raw.types.DocumentAttributeFilename(
                                file_name=utils.get_file_name(
                                    media.media,
                                    file_name=file_name or media.file_name,
                                    fallback="audio.mp3",
                                )
                            )
                        ]
                    )
                )
            )

            media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(
                    id=media.document.id,
                    access_hash=media.document.access_hash,
                    file_reference=media.document.file_reference
                )
            )
        elif re.match("^https?://", media.media):
            media = raw.types.InputMediaDocumentExternal(
                url=media.media
            )
        else:
            media = utils.get_input_media_from_file_id(media.media, FileType.AUDIO)
    elif isinstance(media, types.InputMediaAnimation):
        if isinstance(media.media, io.BytesIO) or os.path.isfile(media.media):
            uploaded_media = await client.invoke(
                raw.functions.messages.UploadMedia(
                    peer=await client.resolve_peer(chat_id),
                    media=raw.types.InputMediaUploadedDocument(
                        mime_type=client.guess_mime_type(media.media) or "video/mp4",
                        thumb=await client.save_file(media.thumb),
                        spoiler=media.has_spoiler,
                        file=await client.save_file(media.media),
                        attributes=[
                            raw.types.DocumentAttributeVideo(
                                supports_streaming=True,
                                duration=media.duration,
                                w=media.width,
                                h=media.height
                            ),
                            raw.types.DocumentAttributeFilename(
                                file_name=utils.get_file_name(
                                    media.media,
                                    file_name=file_name or media.file_name,
                                    fallback="animation.mp4",
                                )
                            ),
                            raw.types.DocumentAttributeAnimated()
                        ]
                    )
                )
            )

            media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(
                    id=uploaded_media.document.id,
                    access_hash=uploaded_media.document.access_hash,
                    file_reference=uploaded_media.document.file_reference
                ),
                spoiler=media.has_spoiler
            )
        elif re.match("^https?://", media.media):
            media = raw.types.InputMediaDocumentExternal(
                url=media.media,
                spoiler=media.has_spoiler
            )
        else:
            media = utils.get_input_media_from_file_id(media.media, FileType.ANIMATION)
    elif isinstance(media, types.InputMediaDocument):
        if isinstance(media.media, io.BytesIO) or os.path.isfile(media.media):
            media = await client.invoke(
                raw.functions.messages.UploadMedia(
                    peer=await client.resolve_peer(chat_id),
                    media=raw.types.InputMediaUploadedDocument(
                        mime_type=client.guess_mime_type(media.media) or "application/zip",
                        thumb=await client.save_file(media.thumb),
                        file=await client.save_file(media.media),
                        attributes=[
                            raw.types.DocumentAttributeFilename(
                                file_name=utils.get_file_name(
                                    media.media,
                                    file_name=file_name or media.file_name,
                                    fallback="file.zip",
                                )
                            )
                        ]
                    )
                )
            )

            media = raw.types.InputMediaDocument(
                id=raw.types.InputDocument(
                    id=media.document.id,
                    access_hash=media.document.access_hash,
                    file_reference=media.document.file_reference
                )
            )
        elif re.match("^https?://", media.media):
            media = raw.types.InputMediaDocumentExternal(
                url=media.media
            )
        else:
            media = utils.get_input_media_from_file_id(media.media, FileType.DOCUMENT)

    return media, message, entities



class EditMessageMedia:
    async def edit_message_media(
        self: "pyrogram.Client",
        chat_id: Union[int, str],
        message_id: int,
        media: "types.InputMedia",
        reply_markup: Union["types.InlineKeyboardMarkup", type[object], None] = object,
        file_name: Optional[str] = None,
        business_connection_id: Optional[str] = None,
        show_caption_above_media: Optional[bool] = None,
        schedule_date: Optional[datetime] = None,
    ) -> "types.Message":
        """Edit animation, audio, document, photo or video messages.

        If a message is a part of a message album, then it can be edited only to a photo or a video. Otherwise, the
        message type can be changed arbitrarily.

        .. include:: /_includes/usable-by/users-bots.rst

        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.
                For your personal cloud (Saved Messages) you can simply use "me" or "self".
                For a contact that exists in your Telegram address book you can use his phone number (str).

            message_id (``int``):
                Message identifier in the chat specified in chat_id.

            media (:obj:`~pyrogram.types.InputMedia`):
                One of the InputMedia objects describing an animation, audio, document, photo or video.

            reply_markup (:obj:`~pyrogram.types.InlineKeyboardMarkup`, *optional*):
                An InlineKeyboardMarkup object.
                Pass None to remove the existing reply markup.

            file_name (``str``, *optional*):
                File name of the media to be sent. Not applicable to photos.
                Defaults to file's path basename.

            show_caption_above_media (``bool``, *optional*):
                Pass True, if the caption must be shown above the message media.

            schedule_date (:py:obj:`~datetime.datetime`, *optional*):
                Date when the message will be automatically sent.

            business_connection_id (``str``, *optional*):
                Unique identifier of the business connection.

        Returns:
            :obj:`~pyrogram.types.Message`: On success, the edited message is returned.

        Example:
            .. code-block:: python

                from wzgram.types import InputMediaPhoto, InputMediaVideo, InputMediaAudio

                # Replace the current media with a local photo
                await app.edit_message_media(chat_id, message_id,
                    InputMediaPhoto("new_photo.jpg"))

                # Replace the current media with a local video
                await app.edit_message_media(chat_id, message_id,
                    InputMediaVideo("new_video.mp4"))

                # Replace the current media with a local audio
                await app.edit_message_media(chat_id, message_id,
                    InputMediaAudio("new_audio.mp3"))
        """
        media, message, entities = await resolve_input_media(self, chat_id, media, file_name)

        r = await self.invoke(
            raw.functions.messages.EditMessage(
                peer=await self.resolve_peer(chat_id),
                id=message_id,
                media=media,
                reply_markup=await utils.write_edit_reply_markup(self, reply_markup=reply_markup),
                message=message,
                entities=entities,
                invert_media=show_caption_above_media if show_caption_above_media is not None else None,
                schedule_date=utils.datetime_to_timestamp(schedule_date)
            ),
            sleep_threshold=60,
            business_connection_id=business_connection_id
        )

        for i in r.updates:
            if isinstance(i, (raw.types.UpdateEditMessage, raw.types.UpdateEditChannelMessage, raw.types.UpdateEditEphemeralMessage)):
                return await types.Message._parse(
                    self, i.message,
                    {i.id: i for i in r.users},
                    {i.id: i for i in r.chats}
                )
