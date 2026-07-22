# ContentPilot 参考项目分析

> 分析日期：2026-07-21  
> 分析范围：四个参考项目的 README、顶层/核心目录、依赖清单、认证/内容/排期/发布/分析核心文件及许可证。  
> 使用原则：仅借鉴产品边界、数据关系和交互流程；本项目使用 Vue 3 + TypeScript + FastAPI + SQLAlchemy + MySQL 独立实现，没有复制参考项目源码。

## 1. 总览

| 参考项目 | 技术栈 | 值得借鉴的模块 | 不采用的模块 | 可复用程度 | 许可证注意事项 |
|---|---|---|---|---:|---|
| Free-AI-Social-Media-Scheduler | Next.js 16、React 19、NextAuth、Prisma、PostgreSQL、Tailwind、MuAPI | 单体工程的快速启动；用户—排期关系；排期、处理中、成功、失败状态；账号连接与发布历史流程 | Stripe/积分；Google 单一登录；MuAPI；YouTube/TikTok 视频专属字段；在 GET 请求中触发到期任务 | 35%（设计参考） | MIT；复制或形成实质性衍生时必须保留版权和许可文本。本项目不复制其代码 |
| Postiz | pnpm monorepo、Next.js/React、NestJS、Prisma/PostgreSQL、Temporal、Tailwind | 多平台编辑器；平台适配器；日历拖拽；内容队列；发布工作流；失败状态和通知；组织/角色；分析页结构 | Temporal、Redis、复杂 monorepo、支付/市场/代理机构、浏览器扩展、大量海外平台连接器 | 45%（产品/架构参考） | AGPL-3.0；网络服务修改版存在提供对应源码义务。为避免许可证传染风险，只观察思想和交互，不复制源码/样式/素材 |
| LangChain Social Media Agent | TypeScript、LangGraph、LangChain、Anthropic/OpenAI、Arcade、Firecrawl、Supabase、Slack | 内容校验→报告→生成→压缩→人工中断→改写/接受/拒绝→排期的状态流；结构化输出；Prompt 分层；失败降级 | LangGraph Server、LangSmith、Arcade、Firecrawl、Supabase、Slack、复杂 Agent 图基础设施 | 40%（流程/Prompt 参考） | MIT；复用时保留版权与许可。本项目阶段 1 不实现 AI，仅为后续普通 FastAPI 状态机保留边界 |
| Mixpost | PHP 8.2、Laravel、Inertia、Vue 3、Vite、Tailwind、MySQL 兼容数据库、队列 | 原文/账号版本关系；媒体库；标签；账号；日历；指标与受众；发布批次和平台 provider 抽象；工作区布局 | PHP/Laravel 源码、Horizon 队列、FFmpeg、Pro 商业功能、现有社交平台实现 | 50%（模型/UI 组织参考） | MIT；Lite 与 Pro 边界明确，不能误用商业版功能或标识。本项目仅独立重构数据模型和页面信息架构 |

## 2. Free-AI-Social-Media-Scheduler

### 2.1 README 与启动方式

README 将项目定位为可自托管的视频社交排期器，支持 YouTube/TikTok，使用 `npm install`、Prisma migration 和 `npm run dev` 启动。环境依赖 PostgreSQL、NextAuth/Google OAuth、MuAPI 和 Stripe。它证明“小型单体 + 清晰排期表 + 发布状态列表”很适合快速演示，但外部服务依赖和视频优先方向不适合本课题。

### 2.2 目录结构

- `src/app/`：Next.js App Router 页面与 API 路由；登录、工作区、集成、历史页面集中。
- `src/app/api/posts/`：排期创建、列表、到期触发、状态轮询和失败记录。
- `src/app/api/social/`：社交账号获取和 YouTube 连接。
- `src/lib/`：认证、Prisma、配置、用户和计费服务。
- `prisma/schema.prisma`：User、Account、Session、ScheduledPost 等关系模型。

### 2.3 核心文件与结论

- `src/lib/auth.js`：NextAuth + Prisma adapter，把用户 id/credits 注入 session。可借鉴“登录后统一携带用户标识”，但本项目改为本地账号、JWT access/refresh token 与 RBAC。
- `prisma/schema.prisma`：`ScheduledPost` 汇总平台、账号、正文、计划时间、状态、请求 id、发布 URL 和错误。可拆分重构为 `publish_schedule` 与 `publish_log`，避免一张表承担日志职责。
- `src/app/api/posts/route.js`：展示 scheduled → processing → completed/failed 流转和失败退款；但 GET 请求产生写操作、轮询时触发排期，存在副作用和并发重复风险，不直接采用。
- `src/app/page.js`：编辑、预览、排期队列在同一连续工作区，状态徽标与失败重试路径清晰；本项目可借鉴连续操作感，但不复用深色视觉、视频字段或组件代码。
- `src/app/api/social/accounts/route.js`：账号适配输出统一字段的思路可借鉴；直接绑定 MuAPI 的实现不可采用。

### 2.4 可重构实体与流程

- `User` → `sys_user` + `sys_role` + `sys_user_role`。
- `ScheduledPost` → `publish_schedule` + `publish_log`，并增加幂等、重试次数和发布方式。
- Account → `platform_account`，凭据加密且不返回前端。
- 页面流程：登录 → 选择平台账号 → 编辑/预览 → 选择即时或定时 → 状态队列 → 失败原因/重试。

### 2.5 不直接复用

Stripe、credits、Google OAuth、MuAPI、视频上传/下载、YouTube category/madeForKids、TikTok duet/stitch，以及所有 React/Next.js 页面代码。

## 3. Postiz

### 3.1 README 与工程规模

README 显示其为完整的多平台社交运营系统，采用 pnpm workspaces，包含 Next.js 前端、NestJS 后端、Prisma 数据层和 Temporal 编排。项目覆盖协作、平台连接、排期、分析和自动化，适合产品交互参考，但规模和运行依赖明显超出 Windows 友好的毕业设计范围。

### 3.2 目录结构

- `apps/frontend/`：认证、多平台编辑器、日历、集成、分析与布局。
- `apps/backend/`：认证、posts、integrations、analytics 等 API controller。
- `apps/orchestrator/`：发布与自动发布 Temporal workflows/activities。
- `libraries/nestjs-libraries/`：数据库 repository/service、平台 integrations、DTO、权限。
- `libraries/nestjs-libraries/src/database/prisma/schema.prisma`：组织、用户、集成、媒体、帖子等完整关系。
- `libraries/react-shared-libraries/`：共享表单、通知、翻译等 UI 能力。

### 3.3 核心文件与结论

- `apps/frontend/src/components/launches/calendar.tsx`：按日期/小时呈现，使用拖拽、平台筛选、编辑/复制/删除、统计弹窗和本地时区转换。后续日历阶段只借鉴操作链，不复制 React 实现。
- `apps/frontend/src/components/new-launch/` 与 `components/launches/separate.post.tsx`：多平台内容可分离编辑，说明“公共原文 + 平台版本”的交互价值。
- `apps/backend/src/api/routes/posts.controller.ts` 与 `libraries/.../posts/posts.repository.ts`：controller/service/repository 分层、分组内容和状态查询值得借鉴。
- `apps/orchestrator/src/workflows/post-workflows/post.workflow.v1.0.5.ts`：发布前状态校验、平台调用、token refresh、主帖/评论顺序、成功 URL、失败通知的工作流边界清楚；本项目后续用 APScheduler + 数据库事务实现轻量版本。
- `libraries/nestjs-libraries/src/integrations/social.abstract.ts`、`integration.manager.ts` 和 `social/*.provider.ts`：统一平台抽象与 provider manager 思路将映射到 `PlatformPublisher`。
- `schema.prisma`：Organization/UserOrganization role、Integration、Media、Post 等实体提示权限、内容和连接器应解耦。
- `apps/frontend/src/components/analytics/`：将概览图、平台统计、明细表拆分，适合后续 ECharts 看板的信息架构。

### 3.4 不采用

Temporal、Redis、NestJS、Next.js、组织计费/市场、浏览器扩展、OAuth 应用市场、几十个平台 provider 及其素材。AGPL 项目源码不进入本项目。

## 4. LangChain Social Media Agent

### 4.1 README 与目标

README 描述从 URL 获取内容、生成 Twitter/LinkedIn 文案，并通过 human-in-the-loop 让用户编辑、接受、拒绝或调整排期。快速模式仍依赖 Anthropic、LangSmith、Firecrawl 和 Arcade；完整模式还依赖 Supabase、Slack、GitHub、平台开发者账号。

### 4.2 目录结构

- `src/agents/generate-post/`：生成图、状态、报告、生成、压缩和 Prompt。
- `src/agents/shared/nodes/generate-post/`：人工中断、改写与排期。
- `src/agents/find-and-generate-images/`：图片查找、生成、校验和降级。
- `src/agents/upload-post/`：实际上传抽象。
- `src/utils/schedule-date/`：排期解析与测试。
- `scripts/crons/`：定时调用脚本；`src/tests/`、`src/evals/`：测试与评估。

### 4.3 核心文件与结论

- `generate-post-graph.ts`：验证链接 → 生成内容报告 → 生成 → 超长压缩（最多 3 次）→ 图片失败降级 → 人工节点 → 改写/更新时间/排期。后续在 FastAPI 中应实现显式业务状态，不引入 LangGraph Server。
- `generate-post-state.ts`：把 post、scheduleDate、userResponse、next、image、condenseCount 明确建模；本项目将对应 generation task、content variant、review status。
- `shared/nodes/generate-post/human-node.ts`：支持 accept/edit/ignore/respond，并将无法识别的意图返回人工节点。可借鉴为“生成后必须人工审核，拒绝/修改均可追踪”。
- `shared/nodes/generate-post/schedule-post.ts`：排期是独立节点，失败向上抛出，通知失败不阻断核心排期；这是一种合理的核心/旁路职责划分。
- `generate-post/prompts/index.ts`：业务上下文、结构约束、内容规则和 few-shot 示例分开；本项目后续 Prompt 将版本化，并要求 JSON Schema、事实一致性和 warnings。
- 图片子图显式捕获失败并退回纯文本，符合本项目外部能力降级要求。

### 4.4 不采用

LangGraph/LangSmith server、Anthropic 强绑定、Arcade、Firecrawl、Supabase、Slack、GitHub/YouTube 抓取与复杂图运行时。阶段 1 不创建 AI endpoint、prompt 或任务表实现。

## 5. Mixpost

### 5.1 README 与产品范围

README 强调账号统一管理、平台分析、post versions、媒体库、workspace、queue/calendar、模板和标签。工程是 Laravel package + Inertia/Vue 3，前端组织与本项目接近，但后端语言和队列体系不采用。

### 5.2 目录结构

- `src/Models/`：Account、Post、PostVersion、Media、Tag、Metric、Audience 等。
- `src/Actions/`、`src/Jobs/`、`src/SocialProviders/`：发布用例、异步任务和平台连接器。
- `src/Http/Controllers/`、`routes/web.php`：Dashboard、Calendar、Posts、Media、Reports 等页面接口。
- `database/migrations/create_mixpost_tables.php`：账号、帖子、账号关联、版本、标签、媒体、导入帖、指标与受众表。
- `resources/js/Pages/`：Dashboard、Calendar、Media、Posts、Settings。
- `resources/js/Components/` 和 `Composables/`：编辑器、预览、媒体、版本、筛选、空状态和布局。

### 5.3 核心文件与结论

- `database/migrations/create_mixpost_tables.php`：Post 与 PostVersion 分离，账号关联表保存 provider_post_id/data/errors，适合重构为文章、平台版本、排期和发布日志四层。
- `resources/js/Composables/usePostVersions.js`：保留 original version，并按 account 获取定制版本；本项目改为按 `platform + version_no` 管理平台版本。
- `src/Actions/PublishPost.php`：防止 processing 状态重复执行，批量账号任务结束后根据错误汇总状态；幂等思想值得采用。
- `src/Actions/AccountPublishPost.php`：用 provider manager 获取统一发布器，内容 parser 负责账号版本/媒体/参数格式化；后续对应 Publisher protocol + platform request builder。
- `resources/js/Pages/Dashboard.vue`：账号和周期过滤驱动报告组件，加载错误显式提示；适合后续工作台筛选设计。
- `resources/js/Layouts/Authenticated.vue`：侧栏、顶部导航、响应式遮罩、内容滚动区域的布局可作为基础工作台信息架构参考。
- `resources/js/Pages/Media.vue`、`Components/Media/`：本地/stock 媒体选择与复用边界清晰，留待阶段 4。

### 5.4 不采用

Laravel/PHP/Horizon、现有 provider 源码、FFmpeg、Mixpost 品牌素材、Pro/Enterprise 功能代码。只独立重构概念和关系。

## 6. 本项目模块映射

| 本项目模块 | 主要参考来源 | 实现方式 |
|---|---|---|
| 登录与数据结构 | Free-AI-Social-Media-Scheduler | FastAPI + SQLAlchemy；用户名密码；JWT access/refresh；`sys_user/sys_role/sys_user_role`；BCrypt |
| RBAC 与工作区 | Postiz / Mixpost | FastAPI dependency 校验角色；Vue Router meta + Pinia 路由守卫；管理员/运营者/查看者三级权限 |
| 基础布局与工作台 | Mixpost / Postiz | Vue 3 + Element Plus + Tailwind；响应式侧栏/顶栏/内容区；阶段 1 仅提供基础概览数据 |
| AI 内容生成 | social-media-agent | 后续阶段使用 FastAPI + OpenAI 兼容接口 + versioned JSON Prompt；显式任务状态与人工审核 |
| 多平台内容版本 | Mixpost / Postiz | `content_article` + `content_variant(platform, version_no)`，公共原文与平台版本解耦 |
| 排期日历 | Postiz / Mixpost | 后续阶段 Vue 3 + FullCalendar；月/周/日/列表、拖拽和冲突提示 |
| 发布状态 | Free-AI-Social-Media-Scheduler / Postiz | 后续阶段 APScheduler + MySQL；状态机、重试、事务、幂等键和发布日志 |
| 平台适配器 | Postiz / Mixpost | Python `PlatformPublisher` protocol；微博/公众号使用官方接口，小红书保留人工交付 |
| 媒体库 | Mixpost | 后续阶段本地媒体 + Unsplash，保存来源、摄影师、缩略图和使用类型 |
| 数据分析 | Mixpost / Postiz | 后续阶段 ECharts + FastAPI；指标表、平台/时间/内容对比与导出 |

## 7. 阶段 1 的采纳与边界

本阶段只采纳认证、RBAC、统一响应、数据库迁移、演示账号、响应式工作台布局与 Windows 运行方式。工作台使用明确的“尚未启用”状态和基础欢迎/系统状态信息，不伪造今日排期、互动趋势或发布数据。

本阶段明确不创建以下业务实现：AI 生成、Prompt 调用、媒体搜索、FullCalendar 日历、APScheduler 发布、平台 Publisher、互动数据分析和实验统计。导航可以展示后续能力入口，但必须禁用或标注开发阶段，不能出现可点击的假按钮。

## 8. 许可证与完整性结论

- 三个 MIT 项目允许使用、修改和再分发，但实质复制必须附带原版权和许可。本项目没有复制其源码。
- Postiz 为 AGPL-3.0，尤其关注网络交互场景的对应源码义务。本项目仅作功能观察，不复制实现、UI 素材或文本。
- Mixpost README 明确 Lite/Pro 边界，本项目不接触 Pro 商业代码或标识。
- 初始只读快照（文件数 / 内容树 SHA-256）：Free 47 / `E067B9...55B9C`；Postiz 923 / `74E438...9F26`；Agent 254 / `0566BA...CB58`；Mixpost 563 / `84548C...B93C7`。阶段 1 完成后将再次计算并比对。
