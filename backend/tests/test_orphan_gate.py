"""未核发放 × 钉扎闸（策略 A：未核阻断钉扎）端到端核对。

口径（唯一来源 events.find_orphan_issues）：
  同业务日 issue 且同业务日无同券码 redeem/void 事件 => 未核发放。
覆盖：
  1. 有未核 -> 钉扎 409 且返回未核清单；预览/总览/独立清单与闸口同源
  2. 先核销/作废清掉未核 -> 钉扎成功，未核不进入 total_amount
  3. 跨业务日隔离、已钉日禁写核销、重复钉扎 409
"""
from fastapi.testclient import TestClient

from app.main import app
from app.db import connect
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo

client = TestClient(app)


def add_event(day, et, code, camp="NEW10", amount=None):
    body = {"business_day": day, "event_type": et, "coupon_code": code, "campaign_code": camp}
    if amount is not None:
        body["amount"] = amount
    r = client.post("/api/events", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def orphans_of(day):
    return event_repo.find_orphan_issues(connect(), day)


# ---------- 1. 有未核发放：钉扎必须被阻断 ----------

def test_seal_blocked_when_orphan_issues_exist():
    day = "2026-11-01"
    add_event(day, "issue", "G-001")
    add_event(day, "issue", "G-002", camp="VIP20")

    # 仓储直扫：两笔未核
    assert {o["coupon_code"] for o in orphans_of(day)} == {"G-001", "G-002"}

    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["business_day"] == day
    assert detail["orphan_issue_count"] == 2
    assert {o["coupon_code"] for o in detail["orphan_issues"]} == {"G-001", "G-002"}
    # 被拒后不得产生批次
    assert batches_on(day) == []


def test_preview_dashboard_standalone_share_same_source_as_gate():
    day = "2026-11-02"
    add_event(day, "issue", "H-001")
    add_event(day, "issue", "H-002")
    add_event(day, "issue", "H-003")
    add_event(day, "redeem", "H-001", amount=10)

    preview = client.get("/api/redeem/preview", params={"business_day": day}).json()
    orphans = client.get("/api/redeem/orphans", params={"business_day": day}).json()
    dash = client.get("/api/dashboard").json()

    codes_preview = {o["coupon_code"] for o in preview["orphan_issues"]}
    codes_standalone = {o["coupon_code"] for o in orphans["orphan_issues"]}
    expected = {"H-002", "H-003"}
    assert codes_preview == expected
    assert codes_standalone == expected
    assert preview["orphan_issue_count"] == 2
    assert orphans["orphan_issue_count"] == 2

    # 总览口径与闸同源（把业务日切到该日后核对计数）
    client.put("/api/settings/day", json={"business_day": day})
    dash = client.get("/api/dashboard").json()
    assert dash["orphan_issue_count"] == 2
    assert dash["day_sealed"] is False

    # 闸口返回必须与预览清单逐项一致（禁止「闸报无未核但清单非空」）
    gate = client.post("/api/redeem/seal", json={"business_day": day})
    assert gate.status_code == 409
    gate_codes = {o["coupon_code"] for o in gate.json()["detail"]["orphan_issues"]}
    assert gate_codes == codes_preview == codes_standalone


# ---------- 2. 清掉未核后才能钉扎，且未核金额不进 total_amount ----------

def test_redeem_clears_orphan_then_seal_succeeds():
    day = "2026-11-03"
    add_event(day, "issue", "K-001")
    add_event(day, "issue", "K-002")
    add_event(day, "redeem", "K-001", amount=10)
    # K-002 仍未核 -> 阻断
    assert client.post("/api/redeem/seal", json={"business_day": day}).status_code == 409

    add_event(day, "redeem", "K-002", amount=20)
    assert orphans_of(day) == []

    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fact_count"] == 2
    assert body["total_amount"] == 30.0
    assert body["orphan_issue_count"] == 0
    assert body["status"] == "sealed"

    # 事实已全部 sealed 并绑定批次
    conn = connect()
    facts = fact_repo.list_facts(conn, day)
    assert {f["status"] for f in facts} == {"sealed"}
    assert all(f["batch_id"] == body["batch_id"] for f in facts)
    conn.close()

    # 成功钉扎后扫描口径仍为空，且总览显示日已钉
    client.put("/api/settings/day", json={"business_day": day})
    dash = client.get("/api/dashboard").json()
    assert dash["orphan_issue_count"] == 0
    assert dash["day_sealed"] is True
    assert dash["batch_count"] >= 1


def test_void_clears_orphan_without_entering_total_amount():
    day = "2026-11-04"
    add_event(day, "issue", "V-001", camp="VIP20")
    add_event(day, "issue", "V-002", camp="TEA5")
    add_event(day, "redeem", "V-001", amount=20)
    # V-002 作废而非核销 -> 闭包，但不产生事实、不进金额
    add_event(day, "void", "V-002", camp="TEA5")
    assert orphans_of(day) == []

    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fact_count"] == 1
    assert body["total_amount"] == 20.0  # 作废券未进入 total_amount

    conn = connect()
    facts = fact_repo.list_facts(conn, day)
    assert len(facts) == 1
    assert facts[0]["coupon_code"] == "V-001"
    conn.close()


# ---------- 3. 隔离与互斥补充核对 ----------

def test_other_day_orphan_does_not_block_seal():
    day_a = "2026-11-05"
    day_b = "2026-11-06"
    add_event(day_a, "issue", "X-001")  # A 日未核
    add_event(day_b, "issue", "Y-001")
    add_event(day_b, "redeem", "Y-001", amount=5)
    # B 日无未核，钉扎不受 A 日未核影响
    r = client.post("/api/redeem/seal", json={"business_day": day_b})
    assert r.status_code == 200
    assert r.json()["total_amount"] == 5.0
    # A 日仍有未核
    assert {o["coupon_code"] for o in orphans_of(day_a)} == {"X-001"}


def test_sealed_day_rejects_redeem_and_double_seal():
    day = "2026-11-07"
    add_event(day, "issue", "Z-001")
    add_event(day, "redeem", "Z-001", amount=10)
    assert client.post("/api/redeem/seal", json={"business_day": day}).status_code == 200

    # 重复钉扎
    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 409

    # 已钉日再写核销被既有规则拒绝
    r2 = client.post(
        "/api/events",
        json={"business_day": day, "event_type": "redeem", "coupon_code": "Z-009", "campaign_code": "NEW10", "amount": 10},
    )
    assert r2.status_code == 409


def test_no_open_facts_and_no_orphans_returns_400():
    day = "2026-11-08"  # 完全空日：无未核也无 open 事实
    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 400


def test_orphan_list_is_backend_sourced_not_frontend_filter():
    # 仓储层是唯一扫描实现；确认不存在第二套口径：全仓只有 find_orphan_issues 负责该判定
    import inspect
    from app.services import redeem_service, catalog_service

    redeem_src = inspect.getsource(redeem_service)
    catalog_src = inspect.getsource(catalog_service)
    assert redeem_src.count("find_orphan_issues") >= 2  # 预览 + 写批
    assert "find_orphan_issues" in catalog_src          # 总览同源
    # 服务层不得自行内联 issue 过滤 SQL
    assert "event_type = 'issue'" not in redeem_src
    assert "event_type = 'issue'" not in catalog_src


def batches_on(day):
    conn = connect()
    try:
        return [b for b in batch_repo.list_batches(conn) if b["business_day"] == day]
    finally:
        conn.close()
