# 数据库设计

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
