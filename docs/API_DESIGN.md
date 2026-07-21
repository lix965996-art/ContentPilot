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
| 数据 | `/api/analytics/import`, `/manual`, `/overview`, 三类对比、`/report`, `/ai-summary` |
| 实验 | `/api/experiments`, `/{id}/start`, `/finish`, `/report` |
| 管理 | `/api/admin/users`, `/audit-logs`, `/api/settings` |

权限原则：读接口允许对应业务的查看者；所有写操作至少 OPERATOR；用户、配置和活跃规则写操作仅 ADMIN。
