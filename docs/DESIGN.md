# ContentPilot 设计文档

> 本文合并自原 REQUIREMENTS / SYSTEM_DESIGN / DATABASE_DESIGN / API_DESIGN / PROMPTS / EXPERIMENT_DESIGN / TEST_PLAN 七份文档（2026-07-31），原件见 git 历史。

## 1. 需求说明

### 用户与权限

- ADMIN：用户、模型、平台规则、日志和全局统计；
- OPERATOR：内容、生成、媒体、推荐、排期、发布、数据与实验；
- VIEWER：只读访问内容、排期和报告。

### 核心业务链路

1. 新建或导入 UTF-8 TXT/Markdown 原文；
2. 选择微博、X、小红书、微信公众号并生成版本；
3. 查看质量、耗时、Token、Prompt 版本，编辑并审核；
4. 提取中英文图片关键词，选择封面/正文图；
5. 计算平台曲线、综合分、置信度、推荐理由和备选时间；
6. 创建排期并在日历拖拽；
7. APScheduler 到点调用已通过验证的官方发布器，或生成小红书人工交付任务，记录日志并防止重复；
8. 导入 CSV/XLSX 或手工录入互动数据；
9. 查看平台、内容、时间组对比和 AI 复盘；
10. 建立实验，汇总分组样本并导出报告。

### 非功能要求

- Windows 10/11 优先；没有真实平台凭证时仍可编辑内容，但不能伪造连接或发布成功；
- API 统一 `{ code, message, data, traceId }`；
- 1366×768 与 1920×1080 可用，移动端有响应式导航；
- 上传限制、ORM、JWT、BCrypt、RBAC、密钥脱敏、DOM 安全、审计和发布幂等；
- 不伪造真实 API、测试结果或实验结论。

## 2. 系统设计

### 架构

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

### 状态流

- 文章：`DRAFT → GENERATED → APPROVED → ARCHIVED`；
- 版本审核：`PENDING → APPROVED`；
- 微博发布：`PENDING → RUNNING → SUCCESS`；只有通过 OAuth 实测的账号才可创建任务；
- 公众号发布：`PENDING → RUNNING → DRAFT_CREATED/PUBLISH_SUBMITTED`；创建草稿不等同于公开发布；
- 小红书人工交付：`PENDING → WAITING_MANUAL_CONFIRM → MANUAL_PUBLISHED`；
- 异常进入 `FAILED`，可按接口错误决定重试或重新授权。

### 降级

- LLM 缺少密钥或失败：生成任务明确失败，不生成伪造的模型结果；
- Unsplash 不可用：10 张本地 SVG；
- 微博或公众号未通过官方验证：禁止创建真实发布排期；
- 小红书没有可用官方发布权限：只生成文案与图片交付包，等待人工发布确认。

### 安全

JWT 区分 access/refresh；服务端校验角色；密码 BCrypt；SQLAlchemy 参数化；上传限制类型与大小；系统密钥只显示掩码；发布使用唯一 `idempotency_key` 和事务状态检查；写操作进入 `audit_log`。

## 3. 数据库设计

迁移：`20260721_0001` 创建认证/RBAC；`d7bc40428afb` 创建完整业务模型。

| 领域 | 表 | 关系/用途 |
|---|---|---|
| 认证 | `sys_user`, `sys_role`, `sys_user_role` | 用户与多角色 |
| 内容 | `content_article`, `content_variant` | 一篇原文对应多平台、多版本 |
| 媒体 | `media_asset` | 关联文章/版本，记录来源、署名和用途 |
| 平台 | `platform_account` | 平台账号和发布方式，不明文返回凭证 |
| 推荐 | `activity_prior`, `account_activity_stat`, `publish_recommendation` | 平台先验、账号历史与推荐解释 |
| 发布 | `publish_schedule`, `publish_log` | 排期、幂等键、状态、错误与逐步日志 |
| 分析 | `engagement_metric` | 曝光、互动、分组和数据来源 |
| 实验 | `experiment`, `experiment_sample` | 研究假设、分组样本、结果与结论 |
| 管理 | `audit_log`, `system_setting`, `generation_task` | 审计、配置与 AI 任务状态 |

关键约束：版本号按文章+平台唯一；活跃规则时段唯一；发布幂等键唯一；互动记录按排期+日期+来源去重；外键删除使用 CASCADE 或 SET NULL 保持一致性。

## 4. API 设计

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

### 文章改写任务

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

## 5. Prompt 设计

Prompt 版本当前为 `3.3.0`，生成版本保存 `prompt_version`、模型、耗时和 Token。

- 系统约束：保留事实、不虚构数字、信息不足给出警告、结构化 JSON；
- 微博：120–160 字、核心观点优先、2–4 个话题、最多 2 个 Emoji；
- X：标题钩子、正文和最多 4 个标签合并后不超过 280 个加权字符，不输出 Markdown；
- 小红书：自然标题、短段落、5–8 标签、不虚构亲身经历；
- 公众号：标题/摘要/二级标题/Markdown/配图位置/风险提示；
- 质量审查：完整度、事实一致性、平台风格、可读性、标签相关性与人工复核；
- 数据复盘：只根据输入数据，区分相关与因果，提示样本限制。

完整文字来自总任务书，代码入口为 `backend/app/prompts/templates.py`。真实 OpenAI 兼容响应需是 JSON；结构校验失败会自动重试，连续失败则将对应平台标为 `FAILED`，不会生成本地伪结果。

## 6. 实验设计

### 内容适配效率

- 至少 10 篇文章；
- 对照组纯人工改写，实验组 AI 生成后人工修改；
- 指标：耗时、修改字符数、修改次数、适配评分、满意度；
- 记录 Prompt/模型版本，避免模型变化污染结论。

### 发布时间推荐

- 建议连续两周；
- 实验组使用推荐时间，对照组使用固定时间；
- 指标：互动率及点赞、评论、收藏、转发均值；
- 同期尽量平衡平台、主题、内容质量和粉丝规模。

推荐评分有历史时：`0.4×平台先验 + 0.4×账号历史 + 0.1×内容类型 + 0.1×受众时区`；冷启动为 `0.7×平台先验 + 0.2×内容类型 + 0.1×受众时区`。置信度按历史样本量分为高/中/低。

系统自带样本仅为 `SIMULATED`，不能直接作为论文真实结论。

## 7. 测试计划

- 后端：认证、RBAC、文章 CRUD、四平台生成、任务轮询、JSON 降级、时间评分、排期、发布幂等、指标、导入和实验；
- 前端：Prettier、ESLint、TypeScript 构建、Pinia 和登录组件单测；
- E2E：管理员登录与真实工作台、运营者访问内容/AI/日历/复盘、管理员接口越权；
- 数据库：在 MySQL 8 实际执行 Alembic 和 seed；自动化测试使用隔离 SQLite；
- 启动：后台启动、健康等待、状态、精确停止和再次启动；
- 异常：空/短文本、无权限、过去时间、重复排期、重复发布、负指标、字段缺失、外部模型失败。

每次发布前运行 `.\contentpilot.ps1 test`，不得以删除断言、吞异常或伪造日志获得通过。
