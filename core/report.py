"""排版：把一轮/汇总数据渲染成给人看的文本。纯标准库，可单测。"""

import time

SEG_LABEL = {
    "system_prompt": "系统提示",
    "history": "历史消息",
    "user_prompt": "本轮输入",
    "quoted": "引用内容",
    "extra": "附加块",
    "tools": "工具schema",
}

_FIELD = {
    "system_prompt": "est_system",
    "history": "est_history",
    "user_prompt": "est_user",
    "quoted": "est_quoted",
    "extra": "est_extra",
    "tools": "est_tools",
}


def fmt_int(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def bar(value: int, total: int, width: int = 10) -> str:
    if not total:
        return "░" * width
    filled = max(0, min(width, int(round(width * int(value) / int(total)))))
    return "█" * filled + "░" * (width - filled)


def format_turn(row: dict) -> str:
    segs = [(seg, int(row.get(_FIELD[seg]) or 0)) for seg in SEG_LABEL]
    total = sum(v for _, v in segs) or 1
    when = time.strftime("%m-%d %H:%M", time.localtime(row.get("ts") or 0))
    lines = [f"第 {row.get('id')} 轮 · {when} · 估算合计 {fmt_int(total)}"]
    for seg, val in segs:
        if val:
            lines.append(f"  {SEG_LABEL[seg]:<6} {bar(val, total)} {fmt_int(val)}")
    in_other = int(row.get("in_other") or 0)
    in_cached = int(row.get("in_cached") or 0)
    out = int(row.get("out_tokens") or 0)
    if in_other or in_cached or out:
        real_in = in_other + in_cached
        hit = (in_cached / real_in * 100) if real_in else 0.0
        lines.append(
            f"  真实：输入 {fmt_int(in_other)} 新增 / {fmt_int(in_cached)} 缓存"
            f"（命中 {hit:.1f}%） 输出 {fmt_int(out)}"
        )
    else:
        lines.append("  真实：本轮没拿到 usage（部分供应商不上报）")
    if row.get("images"):
        lines.append(f"  图片：{row['images']} 张")
    return "\n".join(lines)


def format_summary(s: dict, hours: int = 24) -> str:
    if not s or not s.get("n"):
        return f"最近 {hours} 小时还没有记录"
    total = sum(int(s.get(seg) or 0) for seg in SEG_LABEL)
    lines = [f"最近 {hours} 小时 · {s['n']} 轮 · 估算输入合计 {fmt_int(total)}"]
    for seg in SEG_LABEL:
        val = int(s.get(seg) or 0)
        if val:
            pct = val / total * 100 if total else 0
            lines.append(f"  {SEG_LABEL[seg]:<6} {bar(val, total)} {fmt_int(val)}  {pct:.1f}%")
    real_in = int(s.get("in_other") or 0) + int(s.get("in_cached") or 0)
    lines.append(
        f"  真实：新增 {fmt_int(s.get('in_other'))} + 缓存 {fmt_int(s.get('in_cached'))}"
        f" = {fmt_int(real_in)}  缓存命中 {float(s.get('cache_hit') or 0) * 100:.1f}%"
    )
    lines.append(f"  输出：{fmt_int(s.get('out_tokens'))}")
    return "\n".join(lines)
