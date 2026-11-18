# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 过期/退回窗（后挖）→ 批次互证。

## 未核发放 × 钉扎闸（全局唯一策略：未核阻断钉扎）

- 未核发放定义（唯一来源 `repositories/events.py::find_orphan_issues`）：同业务日发生 `issue`，且同业务日不存在同券码 `redeem`/`void` 事件。
- 钉预览、钉扎写批、总览、`GET /api/redeem/orphans` 全部调用同一扫描函数，禁止另写过滤逻辑，杜绝「闸报无未核但清单非空」。
- `POST /api/redeem/seal` 在写批事务内先扫描：存在未核即 **409 拒绝**并原样返回未核清单；须先对这些券码写核销或作废，扫描为空后才能钉。
- 未核/作废券不产生核销事实，不进入批次 `total_amount`；成功钉扎返回 `orphan_issue_count: 0`。
- 未核清单由后端接口与 409 响应提供，前端只做展示，不做与批次脱钩的临时过滤。

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）

测试（隔离临时库，不污染 data/）：
- `cd backend && pip install -r requirements-dev.txt && python -m pytest tests/ -v`
