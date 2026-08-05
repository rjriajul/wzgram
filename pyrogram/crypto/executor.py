import os
from concurrent.futures.thread import ThreadPoolExecutor


def _default_crypto_workers() -> int:
    override = os.environ.get("WZGRAM_CRYPTO_WORKERS")

    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    # warpcrypto releases the GIL for MTProto framing, so a small pool gives
    # real parallel crypto for the media sessions used in parallel transfers
    # (DOWNLOAD_POOL_SIZE / POOL_SIZE are 4-20). Capping avoids spawning
    # cpu_count threads on big boxes — each thread costs a stack plus allocator
    # arenas that a 256 MB host can't afford.
    return min(4, max(1, os.cpu_count() or 1))


_crypto_pool = None


def get_crypto_executor() -> ThreadPoolExecutor:
    global _crypto_pool
    if _crypto_pool is None:
        _crypto_pool = ThreadPoolExecutor(
            max_workers=_default_crypto_workers(),
            thread_name_prefix="Crypto"
        )
    return _crypto_pool


def set_crypto_executor(executor: ThreadPoolExecutor):
    global _crypto_pool
    _crypto_pool = executor


def create_crypto_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="Crypto"
    )
