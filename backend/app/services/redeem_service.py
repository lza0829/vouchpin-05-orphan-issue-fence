from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def list_orphan_issues(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        orphans = event_repo.find_orphan_issues(conn, day)
        return {
            "business_day": day,
            "orphan_issue_count": len(orphans),
            "orphan_issues": orphans,
        }
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        opens = fact_repo.open_facts_for_day(conn, day)
        total = round(sum(float(f["amount"]) for f in opens), 2)
        # 与钉扎写批共用同一个同源扫描，预览即闸口径
        orphans = event_repo.find_orphan_issues(conn, day)
        return {
            "business_day": day,
            "open_count": len(opens),
            "open_total": total,
            "orphan_issue_count": len(orphans),
            "orphan_issues": orphans,
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": opens,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        if fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 已有 sealed 钉扎批")
        # 未核阻断钉扎：写批前同一事务内同源扫描，存在未核即拒绝并返回未核清单。
        # 必须先核销或作废这些发放，使扫描结果为空后才能钉。
        orphans = event_repo.find_orphan_issues(conn, day)
        if orphans:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"业务日 {day} 存在 {len(orphans)} 笔未核发放，须先核销或作废",
                    "business_day": day,
                    "orphan_issue_count": len(orphans),
                    "orphan_issues": orphans,
                },
            )
        opens = fact_repo.open_facts_for_day(conn, day)
        if not opens:
            raise HTTPException(400, "无可钉扎的 open 核销事实")
        total = round(sum(float(f["amount"]) for f in opens), 2)
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=len(opens),
            total_amount=total,
            sealed_at=datetime.now().replace(microsecond=0).isoformat(),
            note=body.get("note") or "",
        )
        fact_repo.mark_batched(conn, [int(f["id"]) for f in opens], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "fact_count": len(opens),
            "total_amount": total,
            "orphan_issue_count": 0,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return batch_repo.list_batches(conn)
    finally:
        conn.close()
