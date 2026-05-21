"""单机内存限流器(P0)。

asyncio 单事件循环里 check_and_incr 整段无 await,天然原子,不需要锁。
约束:
- 多进程 worker 各自一份计数,部署强制 workers=1
- 进程重启计数清零,日配额可通过 §9.5 持久化补救(本期未实现 flush)
- 后台 janitor 清理超过 1 小时未访问的桶,防内存涨

详见 docs/application-integration-design.md §9。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.rate_limit.base import Decision, Limits

logger = logging.getLogger(__name__)


@dataclass
class _Bucket:
    minute: int = 0  # 当前桶 minute id
    curr: int = 0
    prev: int = 0
    day: str = ""  # yyyymmdd
    day_count: int = 0
    last_seen: float = field(default_factory=time.monotonic)


class MemoryRateLimiter:
    """进程内滑动窗口计数 + 日配额。

    数据结构两张字典:_int 按 integration_id;_key 按 (integration_id, key_id)。
    日配额合并在 Integration 桶上,跨日时随 _swc 一并 reset。
    """

    def __init__(self) -> None:
        self._int: dict[int, _Bucket] = defaultdict(_Bucket)
        self._key: dict[tuple[int, int], _Bucket] = defaultdict(_Bucket)
        self._janitor_task: asyncio.Task[None] | None = None

    # ── 滑动窗口 ──

    @staticmethod
    def _swc(b: _Bucket, minute: int, elapsed: int) -> int:
        """估算当前 minute 内的近似 60s 用量,顺带把 b 推进到当前 minute。

        formula = curr + prev * (60 - elapsed) / 60
        跨多桶时 prev 清零(等同冷启动,略宽松,可接受)。
        """
        if b.minute != minute:
            b.prev = b.curr if b.minute == minute - 1 else 0
            b.curr = 0
            b.minute = minute
        return b.curr + (b.prev * (60 - elapsed)) // 60

    # ── 公共接口 ──

    async def check_and_incr(self, intg_id: int, key_id: int, limits: Limits) -> Decision:
        now = int(time.time())
        minute = now // 60
        elapsed = now % 60
        today = time.strftime("%Y%m%d", time.localtime(now))

        ib = self._int[intg_id]
        kb = self._key[(intg_id, key_id)]
        mono = time.monotonic()
        ib.last_seen = mono
        kb.last_seen = mono

        if ib.day != today:
            ib.day = today
            ib.day_count = 0

        key_used = self._swc(kb, minute, elapsed)
        int_used = self._swc(ib, minute, elapsed)
        day_used = ib.day_count

        if limits.key_rpm > 0 and key_used >= limits.key_rpm:
            return Decision(False, "KEY_RPM", key_used, int_used, day_used)
        if limits.int_rpm > 0 and int_used >= limits.int_rpm:
            return Decision(False, "INTEGRATION_RPM", key_used, int_used, day_used)
        if limits.day_quota > 0 and day_used >= limits.day_quota:
            return Decision(False, "DAY_QUOTA", key_used, int_used, day_used)

        kb.curr += 1
        ib.curr += 1
        ib.day_count += 1
        return Decision(True, "OK", key_used + 1, int_used + 1, day_used + 1)

    async def drop_key(self, intg_id: int, key_id: int) -> None:
        self._key.pop((intg_id, key_id), None)

    async def drop_integration(self, intg_id: int) -> None:
        self._int.pop(intg_id, None)
        for k in list(self._key.keys()):
            if k[0] == intg_id:
                del self._key[k]

    # ── janitor ──

    async def start_janitor(self, interval_seconds: int = 300, idle_seconds: int = 3600) -> None:
        if self._janitor_task is not None:
            return
        self._janitor_task = asyncio.create_task(self._janitor_loop(interval_seconds, idle_seconds))

    async def stop_janitor(self) -> None:
        if self._janitor_task is None:
            return
        self._janitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._janitor_task
        self._janitor_task = None

    async def _janitor_loop(self, interval_seconds: int, idle_seconds: int) -> None:
        while True:
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                raise
            cutoff = time.monotonic() - idle_seconds
            n_int = self._sweep(self._int, cutoff)
            n_key = self._sweep(self._key, cutoff)
            if n_int or n_key:
                logger.debug("rate_limit janitor swept int=%d key=%d", n_int, n_key)

    @staticmethod
    def _sweep(d: dict, cutoff: float) -> int:  # type: ignore[type-arg]
        dead = [k for k, v in d.items() if v.last_seen < cutoff]
        for k in dead:
            del d[k]
        return len(dead)
