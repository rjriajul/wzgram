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

from typing import List, Optional, Union

import pyrogram
from pyrogram import raw, types, utils
from pyrogram.enums import BlockAlignment

from ..object import Object


def _to_rich_text(text: Union[str, "raw.base.RichText"]) -> "raw.base.RichText":
    if isinstance(text, str):
        return raw.types.TextConcat(texts=[raw.types.TextPlain(text=text)])

    if not isinstance(text, raw.core.TLObject):
        # the parsed types.RichText family describes a message that arrived; it has
        # no write(), so passing one here used to fail with AttributeError from
        # inside the request being serialised, several frames from the call site
        raise TypeError(
            f"a rich block takes plain text or a raw.types.Text* object, "
            f"not {type(text).__name__}"
        )

    return text


def _to_page_caption(
    text: Optional[Union[str, "raw.base.RichText"]] = None,
    credit: Optional[Union[str, "raw.base.RichText"]] = None,
) -> "raw.types.PageCaption":
    return raw.types.PageCaption(
        text=_to_rich_text(text or ""),
        credit=_to_rich_text(credit or ""),
    )


async def _upload_media(
    client: "pyrogram.Client",
    chat_id: Optional[Union[int, str]],
    media: Union[str, "types.InputMedia", "raw.base.InputPhoto", "raw.base.InputDocument"],
    is_photo: bool,
) -> Union["raw.base.InputPhoto", "raw.base.InputDocument"]:
    if isinstance(media, (raw.types.InputPhoto, raw.types.InputDocument)):
        return media

    if isinstance(media, str):
        media = utils.get_input_media_from_file_id(media)
    elif isinstance(media, types.InputMedia):
        media = await media.write(client=client, chat_id=chat_id)

    if isinstance(media, (raw.types.InputMediaPhoto, raw.types.InputMediaDocument)):
        return media.id

    if not isinstance(media, raw.core.TLObject):
        raise TypeError(
            f"a rich block takes a file identifier or an InputMedia object, "
            f"not {type(media).__name__}"
        )

    uploaded_media = await client.invoke(
        raw.functions.messages.UploadMedia(
            peer=(
                await client.resolve_peer(chat_id)
                if chat_id is not None
                else raw.types.InputPeerSelf()
            ),
            media=media,
        )
    )

    if is_photo:
        return raw.types.InputPhoto(
            id=uploaded_media.photo.id,
            access_hash=uploaded_media.photo.access_hash,
            file_reference=uploaded_media.photo.file_reference,
        )

    return raw.types.InputDocument(
        id=uploaded_media.document.id,
        access_hash=uploaded_media.document.access_hash,
        file_reference=uploaded_media.document.file_reference,
    )



def _collect_mentioned_user_ids(blocks) -> List[int]:
    user_ids = []

    def _walk(obj):
        if isinstance(obj, raw.types.TextMentionName):
            user_ids.append(obj.user_id)

        if isinstance(obj, (list, tuple)):
            values = obj
        elif isinstance(obj, raw.core.TLObject):
            values = (getattr(obj, slot, None) for slot in obj.__slots__)
        elif isinstance(obj, Object):
            values = vars(obj).values()
        else:
            return

        for value in values:
            _walk(value)

    _walk(blocks)

    return list(dict.fromkeys(user_ids))

def _walk_blocks(blocks) -> List["InputRichBlock"]:
    found = []
    stack = list(blocks or ())

    while stack:
        current = stack.pop()

        if isinstance(current, InputRichBlock):
            found.append(current)

        if not isinstance(current, Object):
            continue

        for value in vars(current).values():
            if isinstance(value, Object):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                stack.extend(item for item in value if isinstance(item, Object))

    return found


class InputRichBlock(Object):
    """Base class for all input rich message blocks.

    Subclasses define specific block types that can be used to compose
    the content of a rich message. Each subclass implements a ``write()``
    method that produces the corresponding raw Telegram type.
    """

    def __init__(self):
        super().__init__()

        self._media_id = None

    def write(self) -> "raw.base.PageBlock":
        raise NotImplementedError

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        pass


class InputRichBlockParagraph(InputRichBlock):
    """A paragraph block, corresponding to the HTML tag ``<p>``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the block.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
    ):
        super().__init__()

        self.text = text

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockParagraph(
            text=_to_rich_text(self.text)
        )


class InputRichBlockSectionHeading(InputRichBlock):
    """A section heading block, corresponding to the HTML tags ``<h1>`` through ``<h6>``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the block.

        size (``int``):
            Relative size of the text font, 1-6.
            1 is the largest, 6 is the smallest.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
        size: int,
    ):
        super().__init__()

        self.text = text
        self.size = size

    def write(self) -> "raw.base.PageBlock":
        mapping = {
            1: raw.types.PageBlockHeading1,
            2: raw.types.PageBlockHeading2,
            3: raw.types.PageBlockHeading3,
            4: raw.types.PageBlockHeading4,
            5: raw.types.PageBlockHeading5,
            6: raw.types.PageBlockHeading6,
        }
        cls = mapping.get(self.size)
        if cls is None:
            raise ValueError(f"Invalid heading size: {self.size}. Must be 1-6.")
        return cls(text=_to_rich_text(self.text))


class InputRichBlockPreformatted(InputRichBlock):
    """A preformatted text block, corresponding to the HTML tag ``<pre>``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the block.

        language (``str``):
            Language of the code block (e.g. ``python``, ``javascript``).
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
        language: str,
    ):
        super().__init__()

        self.text = text
        self.language = language

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockPreformatted(
            text=_to_rich_text(self.text),
            language=self.language,
        )


class InputRichBlockFooter(InputRichBlock):
    """A footer block, corresponding to the HTML tag ``<footer>``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the block.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
    ):
        super().__init__()

        self.text = text

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockFooter(
            text=_to_rich_text(self.text)
        )


class InputRichBlockDivider(InputRichBlock):
    """A thematic break block, corresponding to the HTML tag ``<hr>``.

    This block has no content and simply draws a horizontal line.
    """

    def __init__(self):
        super().__init__()

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockDivider()


class InputRichBlockMathematicalExpression(InputRichBlock):
    """A mathematical expression block, corresponding to the custom HTML tag ``<tg-math-block>``.

    Parameters:
        expression (``str``):
            The mathematical expression in TeX source format.
    """

    def __init__(
        self,
        expression: str,
    ):
        super().__init__()

        self.expression = expression

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockMath(source=self.expression)


class InputRichBlockAnchor(InputRichBlock):
    """An anchor block, corresponding to the HTML tag ``<a>`` with a ``name`` attribute.

    This block creates a named anchor point in the message that can be
    linked to from other parts of the message.

    Parameters:
        name (``str``):
            The anchor name.
    """

    def __init__(
        self,
        name: str,
    ):
        super().__init__()

        self.name = name

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockAnchor(name=self.name)


class InputRichBlockListItem(Object):
    """An item in a :class:`~pyrogram.types.InputRichBlockList`.

    A list item either contains a single text line or a collection of nested blocks.

    Parameters:
        blocks (List of :obj:`~pyrogram.types.InputRichBlock`, *optional*):
            Nested blocks that make up the list item content.
            Mutually exclusive with *text*.

        text (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Simple text content of the list item.
            Mutually exclusive with *blocks*.

        has_checkbox (``bool``, *optional*):
            Pass True if the item has a checkbox.

        is_checked (``bool``, *optional*):
            Pass True if the item has a checked checkbox.
    """

    def __init__(
        self,
        blocks: Optional[List[InputRichBlock]] = None,
        text: Optional[Union[str, "raw.base.RichText"]] = None,
        has_checkbox: Optional[bool] = None,
        is_checked: Optional[bool] = None,
    ):
        super().__init__()

        self.blocks = blocks
        self.text = text
        self.has_checkbox = has_checkbox
        self.is_checked = is_checked

    def write(
        self, ordered: bool = False
    ) -> Union["raw.base.PageListItem", "raw.base.PageListOrderedItem"]:
        if self.blocks:
            blocks = [b.write() for b in self.blocks]

            if ordered:
                return raw.types.PageListOrderedItemBlocks(
                    blocks=blocks,
                    checkbox=self.has_checkbox,
                    checked=self.is_checked
                )

            return raw.types.PageListItemBlocks(
                blocks=blocks,
                checkbox=self.has_checkbox,
                checked=self.is_checked
            )

        text = _to_rich_text(self.text or "")

        if ordered:
            return raw.types.PageListOrderedItemText(
                text=text,
                checkbox=self.has_checkbox,
                checked=self.is_checked
            )

        return raw.types.PageListItemText(
            text=text,
            checkbox=self.has_checkbox,
            checked=self.is_checked
        )


class InputRichBlockList(InputRichBlock):
    """A list block, corresponding to the HTML tags ``<ul>`` (unordered) or ``<ol>`` (ordered).

    Parameters:
        items (List of :obj:`~pyrogram.types.InputRichBlockListItem`):
            The items in the list.

        ordered (``bool``, *optional*):
            Pass *True* for an ordered (numbered) list, *False* or omit for an unordered list.
    """

    def __init__(
        self,
        items: List[InputRichBlockListItem],
        ordered: Optional[bool] = None,
    ):
        super().__init__()

        self.items = items
        self.ordered = ordered

    def write(self) -> "raw.base.PageBlock":
        if self.ordered:
            return raw.types.PageBlockOrderedList(
                items=[item.write(ordered=True) for item in self.items]
            )
        return raw.types.PageBlockList(
            items=[item.write() for item in self.items]
        )


class InputRichBlockBlockQuotation(InputRichBlock):
    """A block quotation, corresponding to the HTML tag ``<blockquote>``.

    Parameters:
        blocks (List of :obj:`~pyrogram.types.InputRichBlock`):
            Blocks inside the block quotation.

        credit (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Credit or citation source of the block quotation,
            corresponding to the HTML tag ``<cite>``.
    """

    def __init__(
        self,
        blocks: List[InputRichBlock],
        credit: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.blocks = blocks
        self.credit = credit

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockBlockquoteBlocks(
            blocks=[b.write() for b in self.blocks],
            caption=_to_rich_text(self.credit or ""),
        )


class InputRichBlockExpandableBlockQuotation(InputRichBlock):
    """A block quotation, corresponding to the HTML tag ``<blockquote>`` with the
    custom attribute ``expandable``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Content of the block.

        credit (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Credit or citation source of the block quotation,
            corresponding to the HTML tag ``<cite>``.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
        credit: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.text = text
        self.credit = credit

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockBlockquote(
            text=_to_rich_text(self.text),
            caption=_to_rich_text(self.credit or ""),
            collapsed=True,
        )


class InputRichBlockButtons(InputRichBlock):
    """A block containing a list of buttons shown in one row, corresponding to the
    custom HTML tag ``<tg-button-row>``.

    Parameters:
        buttons (List of :obj:`~pyrogram.types.RichMessageButton`):
            List of 1-8 buttons to send.

        align (:obj:`~pyrogram.enums.BlockAlignment`, *optional*):
            Horizontal alignment of the buttons.
    """

    def __init__(
        self,
        buttons: List["types.RichMessageButton"],
        align: Optional["BlockAlignment"] = None,
    ):
        super().__init__()

        self.buttons = buttons
        self.align = align

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockButtonRow(
            buttons=[button.write() for button in self.buttons],
            align_left=self.align == BlockAlignment.LEFT or None,
            align_center=self.align == BlockAlignment.CENTER or None,
            align_right=self.align == BlockAlignment.RIGHT or None,
        )


class InputRichBlockDocument(InputRichBlock):
    """A block with a general file, corresponding to the custom HTML tag ``<tg-document>``.

    Parameters:
        document_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputDocument` that
            represents the file.

        document (``str`` | :obj:`~pyrogram.types.InputMediaDocument`, *optional*):
            The document to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaDocument` object. Given
            instead of *document_id*.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        document_id: Optional[int] = None,
        document: Optional[Union[str, "types.InputMediaDocument"]] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if document_id is None and document is None:
            raise ValueError("You must pass either document_id or document")

        self.document_id = document_id
        self.document = document
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockDocument(
            document_id=self._media_id or self.document_id,
            caption=_to_page_caption(text=self.caption),
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.document is None:
            return

        media = await _upload_media(client, chat_id, self.document, is_photo=False)

        documents.append(media)

        self._media_id = media.id


class InputRichBlockPullQuotation(InputRichBlock):
    """A pull quotation block, corresponding to the HTML tag ``<aside>``.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the pull quotation.

        credit (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Credit or citation source of the pull quotation,
            corresponding to the HTML tag ``<cite>``.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
        credit: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.text = text
        self.credit = credit

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockPullquote(
            text=_to_rich_text(self.text),
            caption=_to_rich_text(self.credit or ""),
        )


class InputRichBlockCollage(InputRichBlock):
    """A collage block, corresponding to the custom HTML tag ``<tg-collage>``.

    Displays a set of media blocks in a grid layout.

    Parameters:
        items (List of :obj:`~pyrogram.types.InputRichBlock`):
            Media blocks in the collage (typically :class:`~pyrogram.types.InputRichBlockPhoto`,
            :class:`~pyrogram.types.InputRichBlockVideo`, etc.).

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the collage.
    """

    def __init__(
        self,
        items: List[InputRichBlock],
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.items = items
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockCollage(
            items=[item.write() for item in self.items],
            caption=_to_page_caption(text=self.caption),
        )


class InputRichBlockSlideshow(InputRichBlock):
    """A slideshow block, corresponding to the custom HTML tag ``<tg-slideshow>``.

    Displays a set of media blocks in a slideshow/carousel layout.

    Parameters:
        items (List of :obj:`~pyrogram.types.InputRichBlock`):
            Media blocks in the slideshow (typically :class:`~pyrogram.types.InputRichBlockPhoto`,
            :class:`~pyrogram.types.InputRichBlockVideo`, etc.).

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the slideshow.
    """

    def __init__(
        self,
        items: List[InputRichBlock],
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.items = items
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockSlideshow(
            items=[item.write() for item in self.items],
            caption=_to_page_caption(text=self.caption),
        )


class InputRichBlockTable(InputRichBlock):
    """A table block, corresponding to the HTML tag ``<table>``.

    Parameters:
        title (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Title of the table, corresponding to the HTML tag ``<caption>``.

        rows (List of List of :obj:`~pyrogram.types.InputRichBlockTableCell`):
            Rows of the table. Each row is a list of cell objects.

        bordered (``bool``, *optional*):
            Pass *True* to display the table with a border.

        striped (``bool``, *optional*):
            Pass *True* to display the table with alternating row colors.

        compact (``bool``, *optional*):
            Pass *True* if table cells must have smaller indents.
    """

    def __init__(
        self,
        title: Union[str, "raw.base.RichText"],
        rows: List[List["InputRichBlockTableCell"]],
        bordered: Optional[bool] = None,
        striped: Optional[bool] = None,
        compact: Optional[bool] = None,
    ):
        super().__init__()

        self.title = title
        self.rows = rows
        self.bordered = bordered
        self.striped = striped
        self.compact = compact

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockTable(
            title=_to_rich_text(self.title),
            rows=[
                raw.types.PageTableRow(
                    cells=[cell.write() for cell in row]
                )
                for row in self.rows
            ],
            bordered=self.bordered,
            striped=self.striped,
            compact=self.compact,
        )


class InputRichBlockTableCell(Object):
    """A cell in a table row (used with :class:`~pyrogram.types.InputRichBlockTable`).

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text content of the cell.

        header (``bool``, *optional*):
            Pass *True* if the cell is a header cell (``<th>``).

        align_center (``bool``, *optional*):
            Pass *True* to center-align the cell content.

        align_right (``bool``, *optional*):
            Pass *True* to right-align the cell content.

        valign_middle (``bool``, *optional*):
            Pass *True* to middle-align the cell content vertically.

        valign_bottom (``bool``, *optional*):
            Pass *True* to bottom-align the cell content vertically.

        colspan (``int``, *optional*):
            Number of columns the cell spans.

        rowspan (``int``, *optional*):
            Number of rows the cell spans.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
        header: Optional[bool] = None,
        align_center: Optional[bool] = None,
        align_right: Optional[bool] = None,
        valign_middle: Optional[bool] = None,
        valign_bottom: Optional[bool] = None,
        colspan: Optional[int] = None,
        rowspan: Optional[int] = None,
    ):
        super().__init__()

        self.text = text
        self.header = header
        self.align_center = align_center
        self.align_right = align_right
        self.valign_middle = valign_middle
        self.valign_bottom = valign_bottom
        self.colspan = colspan
        self.rowspan = rowspan

    def write(self) -> "raw.types.PageTableCell":
        return raw.types.PageTableCell(
            text=_to_rich_text(self.text),
            header=self.header,
            align_center=self.align_center,
            align_right=self.align_right,
            valign_middle=self.valign_middle,
            valign_bottom=self.valign_bottom,
            colspan=self.colspan,
            rowspan=self.rowspan,
        )


class InputRichBlockDetails(InputRichBlock):
    """A details block, corresponding to the HTML tag ``<details>``.

    Creates a collapsible section that the user can expand or collapse.

    Parameters:
        summary (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Summary text of the details element, corresponding to the HTML tag ``<summary>``.
            This is the visible label when the section is collapsed.

        blocks (List of :obj:`~pyrogram.types.InputRichBlock`):
            Blocks inside the details element (hidden until expanded).

        is_open (``bool``, *optional*):
            Pass *True* to display the details element in the open (expanded) state.
    """

    def __init__(
        self,
        summary: Union[str, "raw.base.RichText"],
        blocks: List[InputRichBlock],
        is_open: Optional[bool] = None,
    ):
        super().__init__()

        self.summary = summary
        self.blocks = blocks
        self.is_open = is_open

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockDetails(
            title=_to_rich_text(self.summary),
            blocks=[b.write() for b in self.blocks],
            open=self.is_open,
        )


class InputRichBlockMap(InputRichBlock):
    """A map block, corresponding to the custom HTML tag ``<tg-map>``.

    Embeds a geographic map with a pin at the specified location.

    Parameters:
        geo (:obj:`~pyrogram.raw.base.InputGeoPoint`):
            Geolocation of the map pin.

        zoom (``int``):
            Map zoom level (typically 1-20).

        w (``int``):
            Map width in pixels.

        h (``int``):
            Map height in pixels.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the map.
    """

    def __init__(
        self,
        geo: "raw.base.InputGeoPoint",
        zoom: int,
        w: int,
        h: int,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        self.geo = geo
        self.zoom = zoom
        self.w = w
        self.h = h
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.InputPageBlockMap(
            geo=self.geo,
            zoom=self.zoom,
            w=self.w,
            h=self.h,
            caption=_to_page_caption(text=self.caption),
        )


class InputRichBlockAnimation(InputRichBlock):
    """An animation block, corresponding to the HTML tag ``<video>``.

    Displays an animated file (GIF-like) in the message.

    Parameters:
        video_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputDocument` that
            represents an animation. The document must have the ``animated`` flag set.

        animation (``str`` | :obj:`~pyrogram.types.InputMediaAnimation`, *optional*):
            The animation to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaAnimation` object. Given
            instead of *video_id*.

        has_spoiler (``bool``, *optional*):
            Pass *True* to cover the media preview with a spoiler animation.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        video_id: Optional[int] = None,
        animation: Optional[Union[str, "types.InputMediaAnimation"]] = None,
        has_spoiler: Optional[bool] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if video_id is None and animation is None:
            raise ValueError("You must pass either video_id or animation")

        self.video_id = video_id
        self.animation = animation
        self.has_spoiler = has_spoiler
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockVideo(
            video_id=self._media_id or self.video_id,
            caption=_to_page_caption(text=self.caption),
            spoiler=self.has_spoiler,
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.animation is None:
            return

        media = await _upload_media(client, chat_id, self.animation, is_photo=False)

        documents.append(media)

        self._media_id = media.id


class InputRichBlockAudio(InputRichBlock):
    """An audio block, corresponding to the HTML tag ``<audio>``.

    Displays an audio file (music) in the message.

    Parameters:
        audio_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputDocument` that
            represents an audio file.

        audio (``str`` | :obj:`~pyrogram.types.InputMediaAudio`, *optional*):
            The audio file to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaAudio` object. Given
            instead of *audio_id*.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        audio_id: Optional[int] = None,
        audio: Optional[Union[str, "types.InputMediaAudio"]] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if audio_id is None and audio is None:
            raise ValueError("You must pass either audio_id or audio")

        self.audio_id = audio_id
        self.audio = audio
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockAudio(
            audio_id=self._media_id or self.audio_id,
            caption=_to_page_caption(text=self.caption),
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.audio is None:
            return

        media = await _upload_media(client, chat_id, self.audio, is_photo=False)

        documents.append(media)

        self._media_id = media.id


class InputRichBlockPhoto(InputRichBlock):
    """A photo block, corresponding to the HTML tag ``<img>``.

    Displays a photo in the message.

    Parameters:
        photo_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputPhoto` that
            represents the photo.

        photo (``str`` | :obj:`~pyrogram.types.InputMediaPhoto`, *optional*):
            The photo to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaPhoto` object. Given
            instead of *photo_id*.

        has_spoiler (``bool``, *optional*):
            Pass *True* to cover the photo with a spoiler animation.

        url (``str``, *optional*):
            URL to open when the photo is clicked.

        webpage_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputWebDocument`
            of the webpage to associate with the photo.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        photo_id: Optional[int] = None,
        photo: Optional[Union[str, "types.InputMediaPhoto"]] = None,
        has_spoiler: Optional[bool] = None,
        url: Optional[str] = None,
        webpage_id: Optional[int] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if photo_id is None and photo is None:
            raise ValueError("You must pass either photo_id or photo")

        self.photo_id = photo_id
        self.photo = photo
        self.has_spoiler = has_spoiler
        self.url = url
        self.webpage_id = webpage_id
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockPhoto(
            photo_id=self._media_id or self.photo_id,
            caption=_to_page_caption(text=self.caption),
            spoiler=self.has_spoiler,
            url=self.url,
            webpage_id=self.webpage_id,
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.photo is None:
            return

        media = await _upload_media(client, chat_id, self.photo, is_photo=True)

        photos.append(media)

        self._media_id = media.id


class InputRichBlockVideo(InputRichBlock):
    """A video block, corresponding to the HTML tag ``<video>``.

    Displays a video in the message.

    Parameters:
        video_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputDocument` that
            represents a video file.

        video (``str`` | :obj:`~pyrogram.types.InputMediaVideo`, *optional*):
            The video to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaVideo` object. Given
            instead of *video_id*.

        has_spoiler (``bool``, *optional*):
            Pass *True* to cover the video with a spoiler animation.

        autoplay (``bool``, *optional*):
            Pass *True* to start playing the video automatically.

        loop (``bool``, *optional*):
            Pass *True* to loop the video playback.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        video_id: Optional[int] = None,
        video: Optional[Union[str, "types.InputMediaVideo"]] = None,
        has_spoiler: Optional[bool] = None,
        autoplay: Optional[bool] = None,
        loop: Optional[bool] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if video_id is None and video is None:
            raise ValueError("You must pass either video_id or video")

        self.video_id = video_id
        self.video = video
        self.has_spoiler = has_spoiler
        self.autoplay = autoplay
        self.loop = loop
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockVideo(
            video_id=self._media_id or self.video_id,
            caption=_to_page_caption(text=self.caption),
            autoplay=self.autoplay,
            loop=self.loop,
            spoiler=self.has_spoiler,
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.video is None:
            return

        media = await _upload_media(client, chat_id, self.video, is_photo=False)

        documents.append(media)

        self._media_id = media.id


class InputRichBlockVoiceNote(InputRichBlock):
    """A voice note block, corresponding to the HTML tag ``<audio>``.

    Displays a voice recording in the message.

    Parameters:
        audio_id (``int``, *optional*):
            The ``id`` field from an :obj:`~pyrogram.raw.types.InputDocument` that
            represents a voice note (a document with the ``voice`` attribute set).

        voice (``str`` | :obj:`~pyrogram.types.InputMediaVoiceNote`, *optional*):
            The voice note to send, as a file identifier of an already uploaded file, a local
            path, an HTTP URL or an :obj:`~pyrogram.types.InputMediaVoiceNote` object. Given
            instead of *audio_id*.

        caption (``str`` | :obj:`~pyrogram.raw.base.RichText`, *optional*):
            Caption of the block.
    """

    def __init__(
        self,
        audio_id: Optional[int] = None,
        voice: Optional[Union[str, "types.InputMediaVoiceNote"]] = None,
        caption: Optional[Union[str, "raw.base.RichText"]] = None,
    ):
        super().__init__()

        if audio_id is None and voice is None:
            raise ValueError("You must pass either audio_id or voice")

        self.audio_id = audio_id
        self.voice = voice
        self.caption = caption

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockAudio(
            audio_id=self._media_id or self.audio_id,
            caption=_to_page_caption(text=self.caption),
        )

    async def _upload(
        self,
        client: "pyrogram.Client",
        chat_id: Optional[Union[int, str]],
        photos: List["raw.base.InputPhoto"],
        documents: List["raw.base.InputDocument"],
    ):
        if self.voice is None:
            return

        media = await _upload_media(client, chat_id, self.voice, is_photo=False)

        documents.append(media)

        self._media_id = media.id


class InputRichBlockThinking(InputRichBlock):
    """A block with a "Thinking..." placeholder, corresponding to the custom HTML tag ``<tg-thinking>``.

    The block may be used only in :meth:`~pyrogram.Client.send_rich_message_draft`, therefore it
    can't be received in messages.
    See https://t.me/addemoji/AIActions for examples of custom emoji, which are recommended for usage in the block.

    Parameters:
        text (``str`` | :obj:`~pyrogram.raw.base.RichText`):
            Text of the block.
            See https://t.me/addemoji/AIActions for examples of custom emoji, which are recommended for usage in the block.
    """

    def __init__(
        self,
        text: Union[str, "raw.base.RichText"],
    ):
        super().__init__()

        self.text = text

    def write(self) -> "raw.base.PageBlock":
        return raw.types.PageBlockThinking(
            text=_to_rich_text(self.text)
        )
