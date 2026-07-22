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
- 微博发布：`PENDING → RUNNING → SUCCESS`；只有通过 OAuth 实测的账号才可创建任务；
- 公众号发布：`PENDING → RUNNING → DRAFT_CREATED/PUBLISH_SUBMITTED`；创建草稿不等同于公开发布；
- 小红书人工交付：`PENDING → WAITING_MANUAL_CONFIRM → MANUAL_PUBLISHED`；
- 异常进入 `FAILED`，可按接口错误决定重试或重新授权。

## 降级

- LLM 缺少密钥或失败：生成任务明确失败，不生成伪造的模型结果；
- Unsplash 不可用：10 张本地 SVG；
- 微博或公众号未通过官方验证：禁止创建真实发布排期；
- 小红书没有可用官方发布权限：只生成文案与图片交付包，等待人工发布确认。

## 安全

JWT 区分 access/refresh；服务端校验角色；密码 BCrypt；SQLAlchemy 参数化；上传限制类型与大小；系统密钥只显示掩码；发布使用唯一 `idempotency_key` 和事务状态检查；写操作进入 `audit_log`。
