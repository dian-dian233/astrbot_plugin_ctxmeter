"""纯标准库的 token 估算。

不是精确 tiktoken，是启发式：中日韩字符按 1 token/字，其余按 4 字符/token。
误差通常在 ±15% 以内，够用来回答「哪一段最吃 token」这个问题。
"""

import re

_CJK = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u3040-\u30ff\uac00-\ud7af]"
)


def estimate_tokens(text) -> int:
    """估算一段文本的 token 数。空值返回 0。"""
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    rest = len(text) - cjk
    return int(round(cjk + rest / 4.0))


def count_chars(text) -> int:
    if text is None:
        return 0
    return len(text if isinstance(text, str) else str(text))
