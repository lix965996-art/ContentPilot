# 系统设计

## 架构

```text
Vue 3 SPA
  ├─ Router / Pinia / Axios / Element Plus
  ├─ FullCalendar / ECharts
  └─ JWT Bearer
          ↓ /api
FastAPI
  ├─ Auth + RBAC + Audit
  ├─ Content / Generation / Media
  ├─ Recommendation / Schedule / Publisher
  ├─ Analytics / Experiment / Settings
  └─ APScheduler
          ↓
SQLAlchemy 2 + Alembic → MySQL 8
```

## 状态流

- 文章：`DRAFT → GENERATED → APPROVED → ARCHIVED`；
- 版本审核：`PENDING → APPROVED`；
- 发布：`PENDING → RUNNING → MOCK_SUCCESS/SUCCESS`，人工模式进入 `WAITING_MANUAL_CONFIRM`，异常进入 `FAILED`，可重试或取消。

## 降级

- LLM 缺少密钥或失败：结构化本地 Mock；
- Unsplash 不可用：10 张本地 SVG；
- 真实发布不可用：MockPublisher 或 ManualConfirmPublisher；
- 所有降级均在接口或 UI 标记 MOCK/SIMULATED。

## 安全

JWT 区分 access/refresh；服务端校验角色；密码 BCrypt；SQLAlchemy 参数化；上传限制类型与大小；系统密钥只显示掩码；发布使用唯一 `idempotency_key` 和事务状态检查；写操作进入 `audit_log`。
