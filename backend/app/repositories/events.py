from __future__ import annotations
import sqlite3
from typing import Any


def list_events(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM coupon_events WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM coupon_events ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_event(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount, business_day, occurred_at, note) VALUES(?,?,?,?,?,?,?)",
        (
            fields["event_type"],
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields.get("amount") or 0),
            fields["business_day"],
            fields["occurred_at"],
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)


def find_orphan_issues(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    """钉扎闸 / 钉预览 / 总览共用的唯一同源扫描。

    定义：同业务日发生 issue，且同业务日不存在同券码 redeem/void 事件的发放行。
    券码一旦在同业务日被核销或作废即闭包，不再视为未核发放。
    严禁在别处另写一套过滤逻辑，避免「闸报无未核但清单非空」。
    """
    rows = conn.execute(
        """
        SELECT i.id AS event_id,
               i.coupon_code,
               i.campaign_code,
               i.business_day,
               i.occurred_at,
               i.note
        FROM coupon_events i
        WHERE i.event_type = 'issue'
          AND i.business_day = ?
          AND NOT EXISTS (
              SELECT 1
              FROM coupon_events t
              WHERE t.business_day = i.business_day
                AND t.coupon_code = i.coupon_code
                AND t.event_type IN ('redeem', 'void')
          )
        ORDER BY i.id
        """,
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]
