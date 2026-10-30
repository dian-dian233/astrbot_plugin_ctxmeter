"""把 ProviderRequest 拆成若干段，分别估算 token。

不 import astrbot：全部用 getattr 鸭子类型，这样离线自测不需要装框架。
"""

from .estimate import count_chars, estimate_tokens

SEGMENTS = (
    "system_prompt",  # 系统提示词
    "history",        # 历史消息（contexts）
    "user_prompt",    # 本轮用户输入
    "quoted",         # 引用内容 <Quoted Message>
    "extra",          # 其它附加内容块（系统提醒等）
    "tools",          # 工具 schema
)


def _text_of(content) -> str:
    """把 message.content（str 或 list[dict]）拍平成字符串。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        buf = []
        for part in content:
            if isinstance(part, str):
                buf.append(part)
            elif isinstance(part, dict):
                for key in ("text", "content", "input_text"):
                    if isinstance(part.get(key), str):
                        buf.append(part[key])
                        break
            else:
                buf.append(str(part))
        return "\n".join(buf)
    return str(content)


def _flatten_contexts(contexts) -> str:
    if not contexts:
        return ""
    buf = []
    for msg in contexts:
        if isinstance(msg, dict):
            buf.append(_text_of(msg.get("content")))
        else:
            buf.append(str(msg))
    return "\n".join(buf)


def _flatten_extra(parts) -> tuple[str, str]:
    """返回 (引用部分文本, 其它附加部分文本)。"""
    quoted, extra = [], []
    for part in parts or []:
        text = ""
        if isinstance(part, dict):
            text = part.get("text") or ""
        else:
            text = getattr(part, "text", "") or ""
        if not isinstance(text, str) or not text:
            continue
        if "<Quoted Message>" in text:
            quoted.append(text)
        else:
            extra.append(text)
    return "\n".join(quoted), "\n".join(extra)


def _flatten_tools(func_tool) -> str:
    if not func_tool is None:
        try:
            tools = getattr(func_tool, "tools", None)
            if tools is None:
                return ""
            buf = []
            for tool in tools:
                name = getattr(tool, "name", "") or ""
                desc = getattr(tool, "description", "") or ""
                params = getattr(tool, "parameters", None) or {}
                buf.append(f"{name} {desc} {params}")
            return "\n".join(buf)
        except Exception:
            return ""
    return ""


def breakdown_request(req) -> dict:
    """拆解一个 ProviderRequest，返回各段 token 估算 + 字符数。

    返回结构：
        {"tokens": {段: int}, "chars": {段: int}, "images": int,
         "model": str, "session": str}
    """
    system_prompt = getattr(req, "system_prompt", "") or ""
    contexts = getattr(req, "contexts", None) or []
    prompt = getattr(req, "prompt", "") or ""
    extra_parts = getattr(req, "extra_user_content_parts", None) or []
    func_tool = getattr(req, "func_tool", None)

    quoted_text, extra_text = _flatten_extra(extra_parts)
    pieces = {
        "system_prompt": _text_of(system_prompt),
        "history": _flatten_contexts(contexts),
        "user_prompt": _text_of(prompt),
        "quoted": quoted_text,
        "extra": extra_text,
        "tools": _flatten_tools(func_tool),
    }

    tokens = {seg: estimate_tokens(text) for seg, text in pieces.items()}
    chars = {seg: count_chars(text) for seg, text in pieces.items()}
    images = getattr(req, "image_urls", None) or []

    return {
        "tokens": tokens,
        "chars": chars,
        "images": len(images) if hasattr(images, "__len__") else 0,
        "model": getattr(req, "model", None) or "",
        "session": getattr(req, "session_id", None) or "",
    }
