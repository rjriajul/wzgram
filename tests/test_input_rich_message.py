from pyrogram import types


def test_block_message_has_no_trailing_vectors():
    for media in (None, types.InputRichMessageMedia(photos=[])):
        b = types.InputRichMessage(
            blocks=[types.InputRichBlockDivider()], media=media
        ).write().write()
        assert len(b) == 20, b.hex()
