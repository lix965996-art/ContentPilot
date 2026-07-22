# API 设计

统一成功响应：`{ "code": 0, "message": "success", "data": ..., "traceId": "..." }`。校验、权限、冲突和内部错误使用业务码并保留相同结构。Swagger：`/docs`。

| 模块 | 主要端点 |
|---|---|
| 认证 | `/api/auth/login`, `/logout`, `/me`, `/refresh`, `/password` |
| 内容 | `/api/articles`, `/api/articles/{id}`, `/archive`, `/import`, `/variants/{id}/approve` |
| AI | `/api/generation/content`, `/tasks/{taskId}`, `/regenerate`, `/keywords`, `/review` |
| 媒体 | `/api/media/search`, `/extract-keywords`, `/select`, `/articles/{id}/media` |
| 推荐 | `/api/recommendations/publish-time`, `/api/activity/curve`, `/platform-priors` |
| 排期发布 | `/api/schedules`, `/{id}/publish-now`, `/retry`, `/cancel`, `/manual-confirm` |
| 平台账号 | `/api/platform-accounts`, `/{platform}/test`, `/{platform}/auth-logs`, `/{platform}` |
| 微博授权 | `/api/platform-accounts/WEIBO/oauth/start`, `/WEIBO/oauth/callback` |
| 发布包 | `/api/schedules/{id}/publish-package`, `/publish-package/download` |
| 数据 | `/api/analytics/import`, `/manual`, `/overview`, 三类对比、`/report`, `/ai-summary` |
| 实验 | `/api/experiments`, `/{id}/start`, `/finish`, `/report` |
| 管理 | `/api/admin/users`, `/audit-logs`, `/api/settings` |

权限原则：读接口允许对应业务的查看者；所有写操作至少 OPERATOR；用户、配置和活跃规则写操作仅 ADMIN。

## 文章改写任务

- `POST /api/generation/content`：创建并行生成任务，保持原 API 主路径。
- `GET /api/generation/tasks/{task_id}`：查询总进度及 `platformStatusJson` 平台级状态。
- `POST /api/generation/tasks/{task_id}/platforms/{platform}/retry`：只重试指定平台。
- `POST /api/generation/content/{variant_id}/regenerate`：基于历史版本重新生成单个平台。
- `POST /api/generation/review`：执行规则校验和 LLM 语义质量评审。
- `POST /api/generation/keywords`：LLM 优先的关键词提取。
- `POST /api/variants/{variant_id}/reject`：拒绝版本。
- `DELETE /api/variants/{variant_id}`：删除未进入发布任务的版本。

任务总状态为 `PENDING/RUNNING/SUCCESS/PARTIAL_SUCCESS/FAILED`，平台状态为
`PENDING/RUNNING/RETRYING/SUCCESS/FAILED`。任务记录 provider、modelName、promptVersion、
tokenUsage、durationMs，以及每个平台的错误、耗时、重试次数和结果版本 ID。
