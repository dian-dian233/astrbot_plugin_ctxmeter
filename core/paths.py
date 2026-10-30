"""数据目录解析：优先用 AstrBot 的 data 目录，拿不到就退回当前工作目录。"""

import os

PLUGIN_NAME = "astrbot_plugin_ctxmeter"


def resolve_data_dir(explicit: str = "") -> str:
    if explicit:
        return explicit
    base = ""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        base = str(get_astrbot_data_path())
    except Exception:
        try:
            from astrbot.core.utils.io import get_astrbot_data_path  # 旧版路径

            base = str(get_astrbot_data_path())
        except Exception:
            base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "plugin_data", PLUGIN_NAME)


def db_path(data_dir: str) -> str:
    return os.path.join(data_dir, "ctxmeter.sqlite3")
