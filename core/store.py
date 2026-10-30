"""每轮用量落 sqlite，纯标准库。"""

import os
import sqlite3
import time

SEGMENTS = ("system_prompt", "history", "user_prompt", "quoted", "extra", "tools")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    session       TEXT,
    model         TEXT,
    est_system    INTEGER DEFAULT 0,
    est_history   INTEGER DEFAULT 0,
    est_user      INTEGER DEFAULT 0,
    est_quoted    INTEGER DEFAULT 0,
    est_extra     INTEGER DEFAULT 0,
    est_tools     INTEGER DEFAULT 0,
    est_total     INTEGER DEFAULT 0,
    images        INTEGER DEFAULT 0,
    in_other      INTEGER DEFAULT 0,
    in_cached     INTEGER DEFAULT 0,
    out_tokens    INTEGER DEFAULT 0,
    total_tokens  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
"""


def _seg_col(seg: str) -> str:
    return {"system_prompt": "est_system", "history": "est_history",
            "user_prompt": "est_user", "quoted": "est_quoted",
            "extra": "est_extra", "tools": "est_tools"}[seg]


class CtxStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def record(self, breakdown: dict, usage=None, ts=None) -> int:
        """写一轮。breakdown 来自 core.breakdown.breakdown_request。"""
        tokens = breakdown.get("tokens") or {}
        est_total = sum(int(v or 0) for v in tokens.values())
        in_other = int(getattr(usage, "input_other", 0) or 0) if usage else 0
        in_cached = int(getattr(usage, "input_cached", 0) or 0) if usage else 0
        out_tokens = int(getattr(usage, "output", 0) or 0) if usage else 0
        total = int(getattr(usage, "total", 0) or 0) if usage else est_total
        row = (
            float(ts if ts is not None else time.time()),
            breakdown.get("session") or "",
            breakdown.get("model") or "",
            *(int(tokens.get(seg, 0) or 0) for seg in SEGMENTS),
            est_total,
            int(breakdown.get("images") or 0),
            in_other,
            in_cached,
            out_tokens,
            total,
        )
        cur = self._conn.execute(
            "INSERT INTO turns (ts, session, model, est_system, est_history,"
            " est_user, est_quoted, est_extra, est_tools, est_total, images,"
            " in_other, in_cached, out_tokens, total_tokens)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent(self, limit: int = 5) -> list[dict]:
        limit = max(1, min(int(limit or 5), 100))
        rows = self._conn.execute(
            "SELECT * FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def summary(self, hours: int = 24) -> dict:
        since = time.time() - hours * 3600
        row = self._conn.execute(
            "SELECT COUNT(*) AS n,"
            " COALESCE(SUM(est_system),0) AS system_prompt,"
            " COALESCE(SUM(est_history),0) AS history,"
            " COALESCE(SUM(est_user),0) AS user_prompt,"
            " COALESCE(SUM(est_quoted),0) AS quoted,"
            " COALESCE(SUM(est_extra),0) AS extra,"
            " COALESCE(SUM(est_tools),0) AS tools,"
            " COALESCE(SUM(in_other),0) AS in_other,"
            " COALESCE(SUM(in_cached),0) AS in_cached,"
            " COALESCE(SUM(out_tokens),0) AS out_tokens"
            " FROM turns WHERE ts >= ?",
            (since,),
        ).fetchone()
        data = dict(row)
        total_in = data["in_other"] + data["in_cached"]
        data["cache_hit"] = (data["in_cached"] / total_in) if total_in else 0.0
        return data
