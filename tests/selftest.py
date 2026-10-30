"""ctxmeter 离线自测：不装 astrbot 也能跑。

    python3 tests/selftest.py --offline
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.breakdown import breakdown_request  # noqa: E402
from core.estimate import count_chars, estimate_tokens  # noqa: E402
from core.paths import db_path, resolve_data_dir  # noqa: E402
from core.report import bar, fmt_int, format_summary, format_turn  # noqa: E402
from core.store import CtxStore  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"[FAIL] {msg}")


class FakeUsage:
    def __init__(self, other=0, cached=0, out=0):
        self.input_other = other
        self.input_cached = cached
        self.output = out

    @property
    def total(self):
        return self.input_other + self.input_cached + self.output


class FakeReq:
    def __init__(self):
        self.system_prompt = "你是一个助手。" * 10
        self.contexts = [
            {"role": "user", "content": "历史问题"},
            {"role": "assistant", "content": [{"type": "text", "text": "历史回答"}]},
        ]
        self.prompt = "本轮问题"
        self.extra_user_content_parts = [
            {"text": "<Quoted Message>\n(某人): 被引用的一段话\n</Quoted Message>"},
            {"text": "<system-reminder>now</system-reminder>"},
        ]
        self.image_urls = ["a.png", "b.png"]
        self.func_tool = None
        self.model = "deepseek-v4.1-flash"
        self.session_id = "sess-1"


def test_estimate():
    print("── token 估算 ──")
    check(estimate_tokens("") == 0, "空串应 0")
    check(estimate_tokens(None) == 0, "None 应 0")
    check(estimate_tokens("今天天气真不错啊哈哈") == 10, "10 个汉字应约 10")
    check(estimate_tokens("hello world this is a test") == 6, "23 个 ASCII 应约 6")
    check(estimate_tokens("中文 abc") == 3, "混排：2 汉字 + 4 ASCII = 2+1")
    check(count_chars("abc") == 3, "count_chars 基础")
    check(count_chars(None) == 0, "count_chars None")


def test_breakdown():
    print("── 请求拆解 ──")
    b = breakdown_request(FakeReq())
    t = b["tokens"]
    check(set(t) == {"system_prompt", "history", "user_prompt", "quoted", "extra", "tools"},
          "六个分段齐全")
    check(t["system_prompt"] > 0, "系统提示应 > 0")
    check(t["history"] > 0, "历史应 > 0")
    check(t["user_prompt"] > 0, "本轮输入应 > 0")
    check(t["quoted"] > 0, "引用应被单独归到 quoted")
    check(t["extra"] > 0, "system-reminder 应归到 extra")
    check(t["tools"] == 0, "func_tool 为空时 tools 应为 0")
    check(b["images"] == 2, "图片张数")
    check(b["model"] == "deepseek-v4.1-flash", "模型名")
    check(b["chars"]["quoted"] > 0, "字符数同步统计")

    empty = breakdown_request(object())
    check(sum(empty["tokens"].values()) == 0, "空对象全 0，且不抛异常")


def test_store():
    print("── 落库与汇总 ──")
    path = db_path(tempfile.mkdtemp())
    store = CtxStore(path)
    b = breakdown_request(FakeReq())
    rid = store.record(b, FakeUsage(other=1000, cached=9000, out=200))
    check(rid == 1, "第一条 id 应为 1")
    rows = store.recent(1)
    check(len(rows) == 1, "recent(1) 一条")
    row = rows[0]
    check(row["in_other"] == 1000 and row["in_cached"] == 9000, "真实用量落库")
    check(row["out_tokens"] == 200, "输出落库")
    check(row["est_total"] == sum(b["tokens"].values()), "估算合计自洽")
    check(row["images"] == 2, "图片张数落库")
    check(row["session"] == "sess-1", "会话落库")
    s = store.summary(24)
    check(s["n"] == 1, "汇总轮数")
    check(abs(s["cache_hit"] - 0.9) < 1e-6, "缓存命中 1000/10000 → 0.9")

    store.record(b, None)
    rows = store.recent(5)
    check(len(rows) == 2, "无 usage 也要能落库")
    check(rows[0]["est_total"] > 0, "无 usage 时估算仍在")
    check(rows[0]["in_other"] == 0, "无 usage 时真实列为 0")
    store.close()


def test_report():
    print("── 排版 ──")
    check(fmt_int(999) == "999", "fmt_int 千以下")
    check(fmt_int(1500) == "1.5k", "fmt_int 千")
    check(fmt_int(2_500_000) == "2.50M", "fmt_int 百万")
    check(bar(0, 100) == "░" * 10, "bar 全空")
    check(bar(100, 100) == "█" * 10, "bar 全满")
    check(bar(50, 0) == "░" * 10, "bar 分母 0 不炸")
    check(len(bar(37, 100)) == 10, "bar 宽度固定")

    row = {"id": 7, "ts": 1_700_000_000, "est_system": 500, "est_history": 3000,
           "est_user": 40, "est_quoted": 120, "est_extra": 30, "est_tools": 800,
           "in_other": 1000, "in_cached": 9000, "out_tokens": 200, "images": 1}
    out = format_turn(row)
    check("第 7 轮" in out, "轮次标题")
    check("引用内容" in out, "引用行出现")
    check("命中 90.0%" in out, "缓存命中百分比")
    check("图片：1 张" in out, "图片行")

    no_usage = dict(row)
    for k in ("in_other", "in_cached", "out_tokens"):
        no_usage[k] = 0
    check("没拿到 usage" in format_turn(no_usage), "无 usage 时的提示")

    summ = {"n": 3, "system_prompt": 1500, "history": 9000, "user_prompt": 120,
            "quoted": 360, "extra": 90, "tools": 2400,
            "in_other": 3000, "in_cached": 27000, "out_tokens": 600, "cache_hit": 0.9}
    text = format_summary(summ, 24)
    check("3 轮" in text, "汇总轮数")
    check("90.0%" in text, "汇总命中率")
    check(format_summary({"n": 0}, 24) == "最近 24 小时还没有记录", "空汇总")


def test_paths():
    print("── 路径 ──")
    d = resolve_data_dir("/tmp/ctxmeter-x")
    check(d == "/tmp/ctxmeter-x", "显式目录原样返回")
    auto = resolve_data_dir("")
    check(auto.endswith(os.path.join("plugin_data", "astrbot_plugin_ctxmeter")), "默认路径以插件名结尾")
    check(db_path(d).endswith("ctxmeter.sqlite3"), "db 文件名")


def main():
    test_estimate()
    test_breakdown()
    test_store()
    test_report()
    test_paths()
    print()
    if FAIL:
        print(f"❌ 失败 {FAIL} 条 / 通过 {PASS} 条")
        return 1
    print(f"全部断言通过 ✅  通过：{PASS} 条   失败：0 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
