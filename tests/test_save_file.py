import asyncio
from types import SimpleNamespace

import pytest

import pyrogram
import pyrogram.methods.advanced.save_file as save_file_mod


class _UploadClient:
    save_file = pyrogram.Client.save_file

    def __init__(self, pool):
        self._pool = pool
        self.save_file_semaphore = asyncio.Semaphore(1)
        self.loop = asyncio.get_event_loop()
        self.executor = None
        self.me = SimpleNamespace(is_bot=True, is_premium=False)
        self.storage = SimpleNamespace(dc_id=self._dc_id)

    async def _dc_id(self):
        return 1

    def rnd_id(self):
        return 1234

    async def _get_media_session_pool(self, dc_id, n):
        return [self._pool]


class _FailFirstThenWedge:
    """One session: the first part fails outright, every later one wedges."""

    def __init__(self):
        self.calls = 0

    async def invoke(self, data, timeout=None):
        self.calls += 1
        if self.calls == 1:
            raise OSError("connection reset")
        await asyncio.sleep(3600)


class _Wedged:
    async def invoke(self, data, timeout=None):
        await asyncio.sleep(3600)


async def test_failed_upload_does_not_hang_on_wedged_workers(monkeypatch, tmp_path):
    monkeypatch.setattr(save_file_mod, "PART_SIZE", 1024)
    monkeypatch.setattr(save_file_mod, "MAX_RETRIES", 1)

    src = tmp_path / "part.bin"
    src.write_bytes(b"\x00" * (256 * 1024))

    client = _UploadClient(_FailFirstThenWedge())

    loop = asyncio.get_event_loop()
    started = loop.time()

    with pytest.raises(OSError):
        await asyncio.wait_for(client.save_file(str(src)), timeout=10)

    assert loop.time() - started < 5, (
        "a failed upload must not block in its cleanup handing sentinels to wedged "
        "workers on a full queue — it holds the transmission semaphore while it does"
    )


async def test_cancelled_upload_does_not_hang_on_wedged_workers(monkeypatch, tmp_path):
    monkeypatch.setattr(save_file_mod, "PART_SIZE", 1024)

    src = tmp_path / "part.bin"
    src.write_bytes(b"\x00" * (256 * 1024))

    client = _UploadClient(_Wedged())
    task = asyncio.ensure_future(client.save_file(str(src)))
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert not client.save_file_semaphore.locked(), (
        "a cancelled upload must release the transmission semaphore — CancelledError "
        "is a BaseException, so it skips an `except Exception` cleanup guard"
    )


async def test_parts_are_sent_with_the_media_deadline(monkeypatch, tmp_path):
    from pyrogram.session import Session

    monkeypatch.setattr(save_file_mod, "PART_SIZE", 1024)

    seen = []

    class _Recorder:
        async def invoke(self, data, timeout=None):
            seen.append(timeout)

    src = tmp_path / "part.bin"
    src.write_bytes(b"\x00" * 4096)

    client = _UploadClient(_Recorder())
    await client.save_file(str(src))

    assert seen and all(t == Session.MEDIA_TIMEOUT for t in seen), (
        "parts must not inherit the generic 15s deadline — it is shorter than a "
        "512 KiB part takes to be answered on a slow uplink, so the part gets "
        "re-uploaded over the link that is already the bottleneck"
    )
