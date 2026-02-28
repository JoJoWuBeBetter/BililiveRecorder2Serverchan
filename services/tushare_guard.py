from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from config import get_tushare_min_interval_seconds


logger = logging.getLogger(__name__)

tushare_sdk_lock = Lock()
_tushare_last_call_monotonic = 0.0
_tushare_failure_cooldown_until_monotonic = 0.0
TUSHARE_FAILURE_COOLDOWN_SECONDS = 30.0


@contextmanager
def guarded_tushare_call() -> Iterator[None]:
    global _tushare_last_call_monotonic, _tushare_failure_cooldown_until_monotonic

    with tushare_sdk_lock:
        min_interval_seconds = get_tushare_min_interval_seconds()
        now = time.monotonic()
        if now < _tushare_failure_cooldown_until_monotonic:
            cooldown_sleep = _tushare_failure_cooldown_until_monotonic - now
            logger.warning(
                "Tushare 调用处于失败冷却期，等待后继续: sleep=%.2fs, cooldown=%.2fs",
                cooldown_sleep,
                TUSHARE_FAILURE_COOLDOWN_SECONDS,
            )
            time.sleep(cooldown_sleep)
            now = time.monotonic()
        elapsed = now - _tushare_last_call_monotonic
        if _tushare_last_call_monotonic > 0 and elapsed < min_interval_seconds:
            sleep_seconds = min_interval_seconds - elapsed
            logger.info(
                "Tushare 调用节流等待: sleep=%.2fs, min_interval=%.2fs",
                sleep_seconds,
                min_interval_seconds,
            )
            time.sleep(sleep_seconds)
        try:
            yield
        except Exception:
            _tushare_failure_cooldown_until_monotonic = time.monotonic() + TUSHARE_FAILURE_COOLDOWN_SECONDS
            logger.warning(
                "Tushare 调用失败，进入冷却期: cooldown=%.2fs",
                TUSHARE_FAILURE_COOLDOWN_SECONDS,
            )
            raise
        finally:
            _tushare_last_call_monotonic = time.monotonic()
