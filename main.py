"""上下文仪表盘：每轮把 prompt 拆成若干段，记录各段估算 token 与真实用量。

指令：
    /ctx [N]      看最近 N 轮的拆解（默认 5）
    /ctx sum [H]  看最近 H 小时的汇总（默认 24）与缓存命中率
    /ctx clear    清空本会话语义上的统计（实际是删库重来，谨慎）

设计要点：
    - on_llm_request 记录拆解（此时还没调模型）
    - on_llm_response 配对真实 usage（input_other / input_cached / output）
    - 估算与真实分两列存，不混淆：估算用来「看构成」，真实用来「算钱」
"""

import os
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .core.breakdown import breakdown_request
from .core.paths import db_path, resolve_data_dir
from .core.report import SEG_LABEL, bar, fmt_int, format_summary, format_turn
from .core.store import CtxStore

@register(
    "astrbot_plugin_ctxmeter",
    "dian-dian233",
    "上下文仪表盘：每轮拆解 prompt token 构成与缓存命中",
    "0.1.0",
)
class CtxMeterPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.conf = config or {}
        self.store: CtxStore | None = None
        self._pending: dict = {}

    async def initialize(self):
        data_dir = resolve_data_dir(self.conf.get("data_dir") or "")
        path = db_path(data_dir)
        self.store = CtxStore(path)
        logger.info(f"[ctxmeter] 数据库：{path}")

    async def terminate(self):
        if self.store:
            self.store.close()
            self.store = None

    def _key(self, event: AstrMessageEvent) -> str:
        return (
            getattr(event, "unified_msg_origin", "")
            or getattr(event, "session_id", "")
            or "default"
        )

    @filter.on_llm_request()
    async def on_req(self, event: AstrMessageEvent, req):
        if not self.conf.get("enabled", True):
            return
        try:
            self._pending[self._key(event)] = breakdown_request(req)
        except Exception as exc:  # 绝不因为仪表盘把正常回复搞挂
            logger.warning(f"[ctxmeter] 拆解失败：{type(exc).__name__}: {exc}")

    @filter.on_llm_response()
    async def on_resp(self, event: AstrMessageEvent, response):
        if not self.conf.get("enabled", True) or not self.store:
            return
        breakdown = self._pending.pop(self._key(event), None)
        try:
            usage = getattr(response, "usage", None)
            self.store.record(breakdown or {"tokens": {}}, usage)
            if self.conf.get("log_each_turn", True):
                row = {"id": "-", "ts": time.time(), **(breakdown or {}).get("tokens", {})}
                segs = {
                    "est_system": (breakdown or {}).get("tokens", {}).get("system_prompt", 0),
                    "est_history": (breakdown or {}).get("tokens", {}).get("history", 0),
                    "est_user": (breakdown or {}).get("tokens", {}).get("user_prompt", 0),
                    "est_quoted": (breakdown or {}).get("tokens", {}).get("quoted", 0),
                    "est_extra": (breakdown or {}).get("tokens", {}).get("extra", 0),
                    "est_tools": (breakdown or {}).get("tokens", {}).get("tools", 0),
                }
                row.update(segs)
                in_other = int(getattr(usage, "input_other", 0) or 0)
                in_cached = int(getattr(usage, "input_cached", 0) or 0)
                row["in_other"] = in_other
                row["in_cached"] = in_cached
                row["out_tokens"] = int(getattr(usage, "output", 0) or 0)
                logger.info("[ctxmeter] " + format_turn(row).replace("\n", " | "))
        except Exception as exc:
            logger.warning(f"[ctxmeter] 记录失败：{type(exc).__name__}: {exc}")

    @filter.command("ctx")
    async def ctx_cmd(self, event: AstrMessageEvent, arg: str = ""):
        """查看上下文用量：/ctx [N] 或 /ctx sum [小时]"""
        if not self.store:
            yield event.plain_result("ctxmeter 还没初始化好，等会儿再试")
            return
        arg = (arg or "").strip()
        if arg.startswith("sum"):
            hours = 24
            parts = arg.split()
            if len(parts) > 1 and parts[1].isdigit():
                hours = max(1, min(int(parts[1]), 24 * 30))
            s = self.store.summary(hours)
            yield event.plain_result(format_summary(s, hours))
            return
        n = 5
        if arg.isdigit():
            n = max(1, min(int(arg), 20))
        rows = self.store.recent(n)
        if not rows:
            yield event.plain_result("还没有记录。发一条消息让我跑一轮，再看 /ctx")
            return
        yield event.plain_result("\n\n".join(format_turn(r) for r in rows))
