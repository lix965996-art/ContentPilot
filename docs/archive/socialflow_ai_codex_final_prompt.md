# SocialFlow AI 毕业设计项目总提示词
## 基于大语言模型与用户活跃度分析的社交媒体内容适配排期系统

> 本文件用于直接交给 Codex 作为项目总任务书。  
> 目标：在 Windows 环境下，尽量由 Codex 完成前后端、数据库、AI 调用、排期、数据分析、测试和文档。  
> 核心原则：能运行、可演示、页面精美、逻辑完整、少折腾 Linux、少依赖复杂环境。

---

# 一、你的角色

你是一名资深产品经理、全栈工程师、AI 应用工程师、UI/UX 设计师、测试工程师和毕业设计技术顾问。

你需要在当前工作区完成一个完整的毕业设计项目：

**基于大语言模型与用户活跃度分析的社交媒体内容适配排期系统**

开发过程中必须遵循以下原则：

1. 不要只生成静态页面，核心页面必须连接真实后端接口和数据库。
2. 不要生成假按钮，关键按钮必须真正可用。
3. 不要一次性堆出整个项目，应按阶段完成、运行、测试和修复。
4. 所有代码必须优先支持 Windows 10/11 本地运行。
5. 不强制使用 Linux、Docker、Redis、Kubernetes、GPU 或复杂中间件。
6. 外部平台 API 无法获得权限时，必须提供模拟发布和人工确认发布模式。
7. 不使用 Selenium、浏览器模拟登录、Cookie 注入或非官方平台发布接口。
8. 大模型失败、Unsplash 失败、真实发布失败时，都要有降级方案。
9. 页面必须现代、精美、统一，不能使用廉价后台模板。
10. 每完成一个阶段，都必须真正启动、运行测试并修复错误。
11. 不得伪造测试通过、接口接通、真实发布或实验数据。
12. 所有模拟数据必须明确标记为 SIMULATED 或 MOCK。

---

# 二、先分析我下载的四个参考项目

在开始写代码之前，先检查当前工作区及其子目录中是否存在以下四个项目或压缩包：

```text
Free-AI-Social-Media-Scheduler
postiz-app
social-media-agent
mixpost
```

可能出现的目录或文件名包括：

```text
Free-AI-Social-Media-Scheduler-main
postiz-app-main
social-media-agent-main
mixpost-main

Free-AI-Social-Media-Scheduler-main.zip
postiz-app-main.zip
social-media-agent-main.zip
mixpost-main.zip
```

如果当前目录中没有找到，搜索父级目录和常见的 `references`、`reference-projects`、`参考项目` 目录。

如果只有 ZIP：

1. 不要覆盖原文件；
2. 解压到 `reference-projects/`；
3. 只读分析，不要直接修改参考项目；
4. 不要先运行大型参考项目，先阅读 README、目录结构、核心源码和许可证。

如果仍然找不到，在 `docs/REFERENCE_ANALYSIS.md` 中记录“未找到”，并继续创建自己的项目，不要停止开发。

---

## 2.1 四个参考项目的用途

### A. Free-AI-Social-Media-Scheduler

作为**最主要的工程参考**，重点分析：

- 单体 Web 项目结构；
- 登录认证；
- 数据库建模；
- 发布任务状态；
- 定时任务；
- 发布历史；
- 平台账号连接；
- 环境变量；
- 本地启动方式；
- 页面流程。

不要照搬：

- Stripe 支付；
- YouTube/TikTok 视频专属逻辑；
- 不适合本课题的第三方服务；
- 与国内文本平台无关的字段。

需要输出：

- 哪些目录可借鉴；
- 哪些实体模型可重构；
- 哪些页面流程可参考；
- 哪些代码不能直接复用。

---

### B. Postiz

作为**产品交互和页面设计参考**，重点分析：

- 内容编辑器；
- 多平台内容切换；
- 排期日历；
- 发布状态；
- 发布失败处理；
- 内容队列；
- 数据分析页面；
- 平台适配器思想；
- 任务执行流程。

不要直接复制整个项目，因为：

- 项目规模较大；
- 技术栈复杂；
- 存在不需要的模块；
- 许可证要求必须尊重；
- 本项目要保持轻量、Windows 友好。

主要借鉴：

- 页面布局；
- 用户操作流程；
- 状态设计；
- 数据看板结构；
- 发布队列交互。

---

### C. LangChain Social Media Agent

作为**AI 内容生成流程参考**，重点分析：

- 输入内容到社交媒体文案的生成流程；
- 人工审核 Human-in-the-loop；
- 生成后修改、接受、拒绝；
- Prompt 组织方式；
- 多平台内容差异化；
- 定时发布任务；
- 失败重试和状态流转。

不要强制引入：

- LangGraph Server；
- LangSmith；
- Arcade；
- Firecrawl；
- Supabase；
- Slack；
- 复杂 Agent 基础设施。

本项目优先使用普通 FastAPI 服务和结构化 Prompt，实现相同业务效果。

---

### D. Mixpost

作为**内容管理、媒体库和数据分析参考**，重点分析：

- 多平台内容版本；
- 媒体资源管理；
- 内容队列；
- 日历；
- 模板；
- 标签；
- 互动数据；
- 数据复盘；
- 工作区和权限设计。

不要直接照搬 PHP/Laravel 代码。

主要参考：

- 功能边界；
- 数据库实体；
- 页面组织；
- 内容版本关系；
- 媒体库交互；
- 数据统计指标。

---

## 2.2 必须生成参考项目分析文档

在正式开发前，创建：

```text
docs/REFERENCE_ANALYSIS.md
```

至少包含以下表格：

| 参考项目 | 技术栈 | 值得借鉴的模块 | 不采用的模块 | 可复用程度 | 许可证注意事项 |
|---|---|---|---|---:|---|

再增加“本项目模块映射”：

| 本项目模块 | 主要参考来源 | 实现方式 |
|---|---|---|
| AI 内容生成 | social-media-agent | FastAPI + OpenAI 兼容接口 |
| 排期日历 | Postiz / Mixpost | Vue3 + FullCalendar |
| 发布状态 | Free-AI-Social-Media-Scheduler / Postiz | APScheduler + MySQL |
| 数据分析 | Mixpost / Postiz | ECharts + FastAPI |
| 登录与数据结构 | Free-AI-Social-Media-Scheduler | 自行重构 |

任何代码复用都必须遵守许可证，不得删除原作者声明，不得整仓库改名冒充原创。

---

# 三、项目最终要做什么

开发一个面向自媒体运营者和校园新媒体团队的 Web 系统。

用户输入一篇原创文章后，系统自动完成：

1. 生成微博版本；
2. 生成小红书版本；
3. 生成微信公众号版本；
4. 推荐相关配图；
5. 推荐最佳发布时间；
6. 在日历中安排发布；
7. 到点执行模拟发布、人工确认发布或真实 API 发布；
8. 导入点赞、评论、收藏、转发、曝光等数据；
9. 生成数据复盘报告；
10. 对比系统推荐时间与固定时间的互动效果。

---

# 四、论文研究内容

论文主要研究两件事。

## 4.1 内容适配研究

研究大语言模型能否把同一篇文章适配成微博、小红书和公众号三种内容形式，并降低人工改写时间。

评价指标：

- 信息完整度；
- 原文事实一致性；
- 平台风格符合度；
- 可读性；
- 标签相关性；
- 人工修改字符数；
- 人工修改耗时；
- 用户满意度。

## 4.2 发布时间推荐研究

研究结合平台公开活跃时段和账号历史互动数据后，推荐时间是否能够提高互动率。

评价指标：

- 平均互动率；
- 平均点赞数；
- 平均评论数；
- 平均收藏数；
- 平均转发数；
- 推荐时间组与固定时间组差异；
- 算法执行时间。

---

# 五、最终确定的技术栈

本项目不使用 Spring Boot，采用更适合 AI 应用、Codex 更容易维护、Windows 更容易运行的技术栈。

---

## 5.1 前端

```text
Vue 3
TypeScript
Vite
Vue Router
Pinia
Element Plus
Tailwind CSS
Axios
FullCalendar
ECharts
md-editor-v3
DOMPurify
Lucide Vue Next
VueUse
Vitest
Playwright
```

---

## 5.2 后端

```text
Python 3.12
FastAPI
Uvicorn
SQLAlchemy 2.0
Alembic
Pydantic v2
PyMySQL
python-jose 或 PyJWT
passlib + bcrypt
APScheduler
httpx
openpyxl
pandas
python-multipart
Jinja2
WeasyPrint 可选
pytest
pytest-asyncio
```

---

## 5.3 数据库

```text
MySQL 8
```

开发模式允许提供 SQLite 降级选项，但正式演示默认使用 MySQL。

---

## 5.4 外部能力

```text
大模型：OpenAI 兼容接口
可支持：DeepSeek、通义千问、OpenAI、Mock 模型
配图：Unsplash API
发布：统一 Publisher 适配器
默认发布方式：MockPublisher
```

---

## 5.5 不采用

```text
Linux 专属脚本
Docker 强依赖
Redis 强依赖
Celery
Kubernetes
GPU 训练
本地大模型训练
Hadoop
Spark
Flink
Selenium 自动发帖
非官方平台接口
```

---

# 六、项目目录结构

```text
socialflow-ai/
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ assets/
│  │  ├─ components/
│  │  ├─ composables/
│  │  ├─ layouts/
│  │  ├─ pages/
│  │  ├─ router/
│  │  ├─ stores/
│  │  ├─ styles/
│  │  ├─ types/
│  │  ├─ utils/
│  │  └─ main.ts
│  ├─ tests/
│  ├─ package.json
│  └─ vite.config.ts
│
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ repositories/
│  │  ├─ services/
│  │  ├─ prompts/
│  │  ├─ publishers/
│  │  ├─ scheduler/
│  │  ├─ analytics/
│  │  ├─ tests/
│  │  └─ main.py
│  ├─ alembic/
│  ├─ requirements.txt
│  ├─ pyproject.toml
│  └─ .env.example
│
├─ reference-projects/
├─ docs/
│  ├─ REFERENCE_ANALYSIS.md
│  ├─ REQUIREMENTS.md
│  ├─ SYSTEM_DESIGN.md
│  ├─ DATABASE_DESIGN.md
│  ├─ API_DESIGN.md
│  ├─ PROMPTS.md
│  ├─ EXPERIMENT_DESIGN.md
│  ├─ TEST_PLAN.md
│  ├─ TEST_REPORT.md
│  ├─ DEPLOYMENT_WINDOWS.md
│  └─ PROGRESS.md
│
├─ sample-data/
│  ├─ articles/
│  ├─ analytics/
│  ├─ platform-priors/
│  └─ media/
│
├─ scripts/
│  ├─ start-dev.bat
│  ├─ stop-dev.bat
│  ├─ init-db.bat
│  ├─ run-tests.bat
│  └─ seed-data.py
│
├─ README.md
├─ PROJECT_SPEC.md
└─ .gitignore
```

---

# 七、系统角色

## 管理员

- 用户管理；
- 模型配置；
- 平台规则配置；
- 活跃时段规则；
- 系统日志；
- 审计日志；
- 全局统计。

## 内容运营者

- 创建文章；
- AI 多平台适配；
- 配图推荐；
- 发布时间推荐；
- 排期；
- 模拟发布；
- 数据导入；
- 数据复盘；
- 实验管理。

## 查看者

- 查看内容；
- 查看排期；
- 查看报告；
- 不可修改和发布。

初始化演示账号：

```text
admin / Admin@123456
operator / Operator@123456
viewer / Viewer@123456
```

---

# 八、视觉设计要求

页面必须是现代 AI 内容运营工作台，不要使用传统后台模板。

视觉关键词：

```text
轻量
专业
有呼吸感
现代
连续工作区
内容创作氛围
高质量数据可视化
```

禁止：

```text
大量无意义卡片
大面积暗黑背景
廉价渐变
默认 Element Plus 后台模板
过度圆角
过重阴影
信息堆积
```

推荐配色：

```text
主色：#2563EB
强调色：#7C3AED
成功：#16A34A
警告：#F59E0B
危险：#DC2626
页面背景：#F7F8FC
内容背景：#FFFFFF
主要文字：#172033
次要文字：#667085
边框：#E6E8EF
```

要求：

- 适配 1366×768 和 1920×1080；
- 页面最大宽度 1440px；
- 左右留白至少 24px；
- 全局字体统一；
- 所有空状态有引导文案；
- 生成任务有进度；
- 长任务支持取消；
- 错误提示必须具体；
- 所有表单有完整校验；
- 页面有骨架屏；
- 支持响应式布局。

---

# 九、主要页面

## 9.1 登录页

- 左侧品牌区；
- 右侧登录表单；
- 演示账号快捷填充；
- 品牌标语：
  > 一篇原文，适配多个平台；一个日历，管理全部内容。
- 不得使用默认模板。

## 9.2 工作台

包含：

- 今日排期；
- 待审核内容；
- 发布失败提醒；
- 最近内容生产进度；
- 最近 14 天互动趋势；
- 推荐时间组与固定时间组对比；
- 表现最佳内容。

## 9.3 内容管理

支持：

- 新建；
- 编辑；
- 删除；
- 搜索；
- 状态筛选；
- 平台筛选；
- 版本历史；
- 批量归档。

## 9.4 AI 内容工作室

三栏布局：

### 左栏

- 原文标题；
- 正文；
- 主题；
- 目标受众；
- 语气；
- 关键词；
- 上传 TXT/Markdown。

### 中栏

- 平台多选；
- 风格；
- 字数；
- 是否生成 Emoji；
- 是否生成标签；
- 保留原意程度；
- 生成按钮；
- 生成进度；
- 模型耗时；
- Token 使用。

### 右栏

Tab：

- 微博；
- 小红书；
- 公众号。

每个版本支持：

- 编辑；
- 重新生成；
- 历史版本；
- 一键复制；
- 保存；
- 审核；
- 字数统计；
- 质量评分；
- 人工修改比例。

## 9.5 配图推荐

- 关键词提取；
- 中文关键词转换英文；
- Unsplash 图片瀑布流；
- 图片预览；
- 选择封面；
- 选择正文图；
- 摄影师与来源信息；
- 本地备用图库。

## 9.6 发布时间推荐

展示：

- 24 小时活跃曲线；
- 平台先验活跃度；
- 账号历史互动率；
- 综合得分；
- 推荐时间；
- 备选时间；
- 推荐理由；
- 置信度。

## 9.7 排期日历

使用 FullCalendar：

- 月；
- 周；
- 日；
- 列表；
- 拖拽；
- 调整时间；
- 平台筛选；
- 状态筛选；
- 冲突提醒；
- 任务详情抽屉。

## 9.8 发布中心

状态：

```text
PENDING
RUNNING
SUCCESS
FAILED
WAITING_MANUAL_CONFIRM
MOCK_SUCCESS
CANCELLED
```

显示：

- 任务编号；
- 平台；
- 内容；
- 计划时间；
- 实际时间；
- 发布方式；
- 重试次数；
- 错误信息；
- 发布链接；
- 日志。

## 9.9 数据复盘

支持：

- Excel/CSV 导入；
- 手工录入；
- 模板下载；
- 数据校验；
- 重复检测；
- 错误行下载；
- 平台对比；
- 内容对比；
- 时间对比；
- AI 复盘摘要；
- 报告导出。

## 9.10 实验管理

支持：

- 内容适配效率实验；
- 推荐时间与固定时间对比实验；
- 实验组；
- 对照组；
- 样本；
- 指标；
- 结论；
- CSV/Excel/PDF/HTML 导出。

## 9.11 系统设置

- 模型配置；
- Unsplash 配置；
- 平台规则；
- 活跃度规则；
- 时区；
- Mock 开关；
- 发布适配器；
- 日志保留时间。

---

# 十、数据库模型

必须实现以下表。

## sys_user

```text
id
username
password_hash
display_name
email
avatar_url
status
created_at
updated_at
last_login_at
```

## sys_role

```text
id
code
name
description
```

## sys_user_role

```text
user_id
role_id
```

## content_article

```text
id
title
source_text
summary
topic
target_audience
tone
keywords_json
status
created_by
created_at
updated_at
```

## content_variant

```text
id
article_id
platform
version_no
title
content_text
content_html
hashtags_json
emoji_count
word_count
model_name
prompt_version
generation_duration_ms
token_usage
quality_score
manual_edit_ratio
review_status
created_at
updated_at
```

平台：

```text
WEIBO
XIAOHONGSHU
WECHAT_OFFICIAL
```

## media_asset

```text
id
article_id
variant_id
source
source_id
image_url
thumbnail_url
photographer_name
photographer_url
alt_text
search_keyword
usage_type
selected
created_at
```

## platform_account

```text
id
user_id
platform
account_name
publish_mode
credential_encrypted
status
created_at
updated_at
```

## activity_prior

```text
id
platform
day_of_week
hour_of_day
base_score
source_description
enabled
updated_at
```

## account_activity_stat

```text
id
account_id
platform
day_of_week
hour_of_day
post_count
avg_impressions
avg_engagement_rate
avg_likes
avg_comments
avg_collects
avg_shares
updated_at
```

## publish_recommendation

```text
id
article_id
variant_id
platform
recommended_at
score
confidence
reason_json
alternative_times_json
algorithm_version
created_at
```

## publish_schedule

```text
id
article_id
variant_id
account_id
platform
scheduled_at
publish_mode
status
retry_count
max_retry_count
actual_publish_at
published_url
error_message
created_by
created_at
updated_at
```

## publish_log

```text
id
schedule_id
step
request_summary
response_summary
status
error_code
error_message
duration_ms
created_at
```

## engagement_metric

```text
id
schedule_id
platform
metric_date
impressions
likes
comments
collects
shares
followers
engagement_total
engagement_rate
data_source
created_at
updated_at
```

## experiment

```text
id
name
type
hypothesis
start_date
end_date
status
control_description
treatment_description
metrics_json
result_json
conclusion
created_by
created_at
updated_at
```

## experiment_sample

```text
id
experiment_id
schedule_id
group_type
sample_label
metric_value_json
created_at
```

## audit_log

```text
id
user_id
action
module
target_type
target_id
request_path
request_method
ip_address
success
detail_json
created_at
```

---

# 十一、API 规范

统一响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "traceId": "..."
}
```

错误响应：

```json
{
  "code": 40001,
  "message": "文章正文不能为空",
  "data": null,
  "traceId": "..."
}
```

## 认证

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
POST /api/auth/refresh
PUT  /api/auth/password
```

## 内容

```text
GET    /api/articles
POST   /api/articles
GET    /api/articles/{id}
PUT    /api/articles/{id}
DELETE /api/articles/{id}
POST   /api/articles/{id}/archive
POST   /api/articles/import
```

## AI 生成

```text
POST /api/generation/content
POST /api/generation/content/{variantId}/regenerate
POST /api/generation/keywords
POST /api/generation/review
GET  /api/generation/tasks/{taskId}
GET  /api/articles/{articleId}/variants
PUT  /api/variants/{id}
POST /api/variants/{id}/approve
```

生成任务必须返回 taskId，由前端轮询。

## 配图

```text
GET  /api/media/search
POST /api/media/extract-keywords
POST /api/media/select
DELETE /api/media/{id}
GET  /api/articles/{articleId}/media
```

## 发布时间推荐

```text
POST /api/recommendations/publish-time
GET  /api/recommendations/{id}
GET  /api/activity/curve
GET  /api/activity/platform-priors
PUT  /api/activity/platform-priors/{id}
```

## 排期

```text
GET    /api/schedules
POST   /api/schedules
GET    /api/schedules/{id}
PUT    /api/schedules/{id}
DELETE /api/schedules/{id}
POST   /api/schedules/{id}/cancel
POST   /api/schedules/{id}/retry
POST   /api/schedules/{id}/publish-now
POST   /api/schedules/{id}/manual-confirm
```

## 数据分析

```text
POST /api/analytics/import
GET  /api/analytics/template
POST /api/analytics/manual
GET  /api/analytics/overview
GET  /api/analytics/platform-comparison
GET  /api/analytics/time-comparison
GET  /api/analytics/content-ranking
GET  /api/analytics/report
POST /api/analytics/ai-summary
```

## 实验

```text
GET    /api/experiments
POST   /api/experiments
GET    /api/experiments/{id}
PUT    /api/experiments/{id}
DELETE /api/experiments/{id}
POST   /api/experiments/{id}/start
POST   /api/experiments/{id}/finish
GET    /api/experiments/{id}/report
```

---

# 十二、完整 AI 提示词

所有 Prompt 必须版本化，记录 prompt_version。

---

## 12.1 系统提示词

```text
你是一名专业的中文社交媒体内容编辑，熟悉微博、小红书和微信公众号的内容规范与表达风格。

你的任务是将用户提供的原创文章适配为指定平台版本。

必须遵守以下规则：

1. 保留原文核心事实，不得虚构人物、数据、机构、研究结论或产品功能。
2. 不得添加原文中不存在的绝对化结论。
3. 输出必须符合指定 JSON Schema。
4. 使用自然中文，不要出现明显机器生成腔。
5. 不要堆砌 Emoji 和标签。
6. 不得输出违法、侵权、歧视、仇恨、色情、诈骗或危险内容。
7. 对无法确认的事实使用谨慎表达。
8. 原文信息不足时，在 warnings 字段中说明，不得自行补全。
9. 不要输出 Markdown 代码块。
10. 除 JSON 外不要输出任何解释。
```

---

## 12.2 微博提示词

```text
请将以下原创文章转换为微博版本。

要求：

1. 正文建议控制在 120～160 个中文字符。
2. 第一行直接表达核心观点。
3. 保留最重要的 2～3 个信息点。
4. 语气简洁、有传播力，但不得标题党。
5. 生成 2～4 个直接相关的话题标签。
6. 不使用超过 2 个 Emoji。
7. 不虚构数据。
8. 给出一个备选短标题。
9. 给出平台适配说明。

原文标题：
{{title}}

原文正文：
{{sourceText}}

目标受众：
{{targetAudience}}

语气：
{{tone}}

输出 JSON：

{
  "platform": "WEIBO",
  "title": "",
  "content": "",
  "hashtags": [],
  "emojis": [],
  "keyPoints": [],
  "adaptationNotes": [],
  "warnings": []
}
```

---

## 12.3 小红书提示词

```text
请将以下原创文章转换为小红书笔记。

要求：

1. 标题自然、有吸引力但不夸张。
2. 标题建议 12～20 个中文字符。
3. 正文分为 4～8 个短段落。
4. 首段说明读者能获得什么。
5. 中间使用序号或短标题。
6. Emoji 总量控制在 4～10 个。
7. 生成 5～8 个相关标签。
8. 不得编造亲身经历。
9. 不使用过度网络化表达，除非用户指定。
10. 给出封面文案。
11. 给出配图关键词。

原文标题：
{{title}}

原文正文：
{{sourceText}}

目标受众：
{{targetAudience}}

语气：
{{tone}}

输出 JSON：

{
  "platform": "XIAOHONGSHU",
  "title": "",
  "coverText": "",
  "content": "",
  "sections": [],
  "hashtags": [],
  "emojis": [],
  "imageKeywords": [],
  "adaptationNotes": [],
  "warnings": []
}
```

---

## 12.4 公众号提示词

```text
请将以下原创文章转换为微信公众号文章。

要求：

1. 生成主标题、备选标题和摘要。
2. 保留原文核心信息和逻辑结构。
3. 使用清晰的二级标题。
4. 正文适合公众号阅读，段落不要过长。
5. 重点内容可以加粗。
6. 输出 Markdown 正文。
7. 推荐 2～4 个配图位置。
8. 结尾生成简洁总结，不强行营销。
9. 不得添加原文中不存在的事实。
10. 给出内容风险提示。

原文标题：
{{title}}

原文正文：
{{sourceText}}

目标受众：
{{targetAudience}}

语气：
{{tone}}

输出 JSON：

{
  "platform": "WECHAT_OFFICIAL",
  "title": "",
  "alternativeTitles": [],
  "summary": "",
  "markdownContent": "",
  "sections": [],
  "imagePlacements": [
    {
      "afterSection": "",
      "keyword": "",
      "description": ""
    }
  ],
  "adaptationNotes": [],
  "warnings": []
}
```

---

## 12.5 质量审查提示词

```text
请审查生成内容是否忠实于原文。

评价：

1. 信息完整度；
2. 事实一致性；
3. 平台风格符合度；
4. 可读性；
5. 标签相关性；
6. 是否存在夸张、虚构或误导；
7. 是否需要人工复核。

原文：
{{sourceText}}

平台：
{{platform}}

生成内容：
{{generatedContent}}

输出 JSON：

{
  "overallScore": 0,
  "informationCompleteness": 0,
  "factualConsistency": 0,
  "platformFit": 0,
  "readability": 0,
  "tagRelevance": 0,
  "issues": [],
  "suggestions": [],
  "needHumanReview": true
}
```

分数为 0～100。

---

## 12.6 图片关键词提示词

```text
请从以下文章中提取适合图片搜索的关键词。

要求：

1. 输出 3～6 个关键词。
2. 每个关键词同时给出中文和英文。
3. 关键词必须适合视觉图片搜索。
4. 避免过于抽象的词。
5. 不输出品牌和人物姓名，除非原文明确要求。
6. 不输出敏感或侵权词。

输出 JSON：

{
  "keywords": [
    {
      "zh": "",
      "en": "",
      "reason": ""
    }
  ]
}
```

---

## 12.7 数据复盘提示词

```text
你是一名社交媒体数据分析师。

根据提供的互动数据生成复盘总结。

要求：

1. 只根据输入数据得出结论。
2. 区分相关性和因果关系。
3. 样本量较小时提示结论仅供参考。
4. 分析平台差异、内容差异和发布时间差异。
5. 指出表现最佳和最差内容。
6. 给出下一阶段可执行建议。
7. 不得虚构数据。

输出 JSON：

{
  "summary": "",
  "keyFindings": [],
  "bestPerformers": [],
  "weakPerformers": [],
  "timeInsights": [],
  "platformInsights": [],
  "recommendations": [],
  "limitations": []
}
```

---

# 十三、发布时间推荐算法

不训练复杂模型，使用可解释加权评分。

## 候选时间

每 30 分钟一个时间槽：

```text
00:00
00:30
...
23:30
```

## 有历史数据

```text
FinalScore =
0.40 × PlatformPriorScore
+ 0.40 × AccountHistoryScore
+ 0.10 × ContentTypeScore
+ 0.10 × AudienceTimezoneScore
```

## 无历史数据

```text
FinalScore =
0.70 × PlatformPriorScore
+ 0.20 × ContentTypeScore
+ 0.10 × AudienceTimezoneScore
```

所有分数归一化为 0～100。

置信度：

```text
高：历史样本数 ≥ 30
中：10～29
低：< 10
```

返回结构：

```json
{
  "recommendedAt": "2026-08-12T20:10:00+08:00",
  "score": 89,
  "confidence": "HIGH",
  "reasons": [
    {
      "type": "PLATFORM_PRIOR",
      "description": "该平台晚间活跃度较高",
      "contribution": 34
    },
    {
      "type": "ACCOUNT_HISTORY",
      "description": "该账号20:00至21:00历史互动率最高",
      "contribution": 38
    }
  ],
  "alternatives": []
}
```

---

# 十四、发布适配器

定义统一抽象接口：

```python
from typing import Protocol

class PlatformPublisher(Protocol):
    platform: str

    async def validate_account(self, account) -> bool:
        ...

    async def publish(self, request):
        ...

    async def query_status(self, task_id: str):
        ...
```

实现：

```text
MockPublisher
ManualConfirmPublisher
WeiboPublisher
WechatOfficialPublisher
XiaohongshuPublisher
```

第一阶段只完整实现：

```text
MockPublisher
ManualConfirmPublisher
```

其他平台只保留接口、配置和扩展说明，不使用非官方接口。

---

# 十五、定时任务

使用 APScheduler。

流程：

```text
创建排期
→ 保存 MySQL
→ 创建 APScheduler 任务
→ 到达时间
→ 读取任务
→ 校验状态
→ 调用 Publisher
→ 保存发布日志
→ 更新状态
→ 失败重试
```

重试：

```text
第一次失败：1 分钟后
第二次失败：5 分钟后
第三次失败：15 分钟后
```

必须防止重复发布：

- 状态检查；
- 数据库事务；
- 幂等键；
- 成功后禁止重复执行；
- 并发锁。

---

# 十六、互动指标

```text
互动总量 = 点赞 + 评论 + 收藏 + 转发
互动率 = 互动总量 / 曝光量
点赞率 = 点赞 / 曝光量
评论率 = 评论 / 曝光量
收藏率 = 收藏 / 曝光量
转发率 = 转发 / 曝光量
```

无曝光量时：

```text
标准化互动率 = 互动总量 / 发布时粉丝数
```

导入字段：

```text
platform
content_title
publish_time
group_type
impressions
likes
comments
collects
shares
followers
data_source
```

group_type：

```text
RECOMMENDED_TIME
FIXED_TIME
```

data_source：

```text
REAL
MANUAL
IMPORTED
SIMULATED
```

---

# 十七、实验设计

## 内容适配效率实验

至少准备 10 篇文章。

对比：

```text
纯人工改写
大模型生成后人工修改
```

记录：

- 完成耗时；
- 修改字符数；
- 修改次数；
- 适配评分；
- 用户满意度。

## 发布时间实验

建议两周。

分组：

```text
实验组：系统推荐时间
对照组：固定时间
```

比较：

- 平均互动率；
- 平均点赞；
- 平均评论；
- 平均收藏；
- 平均转发。

允许模拟数据，但必须标记 SIMULATED，并在报告中明确说明。

---

# 十八、Mock 数据

系统第一次启动生成：

- 3 个用户；
- 12 篇原创文章；
- 每篇 3 个平台版本；
- 20 条排期；
- 14 天互动数据；
- 2 个实验；
- 48 条平台活跃规则；
- 10 张本地备用图片。

数据必须自然真实，不使用“测试1、测试2”。

---

# 十九、安全要求

- BCrypt 密码；
- JWT 过期；
- RBAC；
- API Key 加密保存；
- 前端不返回完整密钥；
- DOMPurify；
- 上传文件限制；
- Excel 防公式注入；
- 日志不记录完整 Token；
- 防止越权；
- SQLAlchemy ORM；
- 外部 API 超时；
- 发布幂等；
- 审计日志。

---

# 二十、测试要求

## 后端

使用 pytest，覆盖：

- 登录；
- 权限；
- 文章 CRUD；
- AI 任务；
- LLM JSON 解析；
- 发布时间评分；
- 排期；
- 发布幂等；
- 指标计算；
- Excel 导入；
- 实验统计。

## 前端

使用 Vitest 和 Playwright，覆盖：

- 登录；
- 新建文章；
- AI 生成；
- 多平台预览；
- 排期；
- 日历拖拽；
- 数据导入；
- 报告查看。

## 异常测试

- 空文本；
- 超长文本；
- LLM 超时；
- LLM 返回错误 JSON；
- Unsplash 失败；
- 排期时间错误；
- 重复排期；
- 无权限；
- Excel 字段错误；
- 数值为负；
- 重复发布；
- 数据库异常。

不得伪造测试通过。

---

# 二十一、Windows 运行要求

必须提供：

```text
scripts/start-dev.bat
scripts/stop-dev.bat
scripts/init-db.bat
scripts/run-tests.bat
```

`start-dev.bat` 应完成：

1. 检查 Python；
2. 创建 venv；
3. 安装后端依赖；
4. 检查 Node；
5. 安装前端依赖；
6. 检查 MySQL；
7. 执行 Alembic；
8. 启动 FastAPI；
9. 启动 Vue；
10. 打开浏览器。

必须创建：

```text
docs/DEPLOYMENT_WINDOWS.md
```

包含：

- Python 安装；
- Node 安装；
- MySQL 安装；
- 环境变量；
- 启动；
- 端口冲突；
- API Key；
- Mock 模式；
- 常见错误。

Mock 模式不能依赖任何外部服务。

---

# 二十二、环境变量

```env
APP_NAME=SocialFlow AI
APP_ENV=dev
APP_TIMEZONE=Asia/Shanghai

DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/socialflow
SQLITE_FALLBACK_URL=sqlite:///./socialflow.db

JWT_SECRET=change-this-secret
JWT_EXPIRE_MINUTES=120

LLM_PROVIDER=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=60

UNSPLASH_ACCESS_KEY=
MEDIA_FALLBACK_ENABLED=true

PUBLISH_MODE=mock
```

---

# 二十三、开发阶段

严格按阶段执行。

## 阶段 0：参考项目分析

- 找到四个项目；
- 阅读 README；
- 分析目录；
- 分析许可证；
- 生成 `docs/REFERENCE_ANALYSIS.md`；
- 不修改参考项目。

## 阶段 1：基础工程

- Vue3；
- FastAPI；
- MySQL；
- Alembic；
- JWT；
- RBAC；
- 登录页；
- 工作台布局；
- 演示账号；
- Windows 脚本；
- Swagger。

## 阶段 2：内容管理

- 文章 CRUD；
- 编辑器；
- 状态；
- 版本；
- 审计日志。

## 阶段 3：AI 生成

- Mock 模型；
- OpenAI 兼容调用；
- 三个平台 Prompt；
- JSON 解析；
- 任务状态；
- 预览；
- 审核；
- 重新生成；
- 修改比例。

## 阶段 4：配图推荐

- 关键词；
- Unsplash；
- 本地图库；
- 图片选择；
- 署名信息。

## 阶段 5：发布时间推荐

- 平台规则；
- 历史统计；
- 评分；
- 曲线；
- 推荐理由；
- 备选时间。

## 阶段 6：排期与发布

- FullCalendar；
- 拖拽；
- APScheduler；
- MockPublisher；
- ManualConfirmPublisher；
- 日志；
- 重试；
- 幂等。

## 阶段 7：数据复盘

- Excel/CSV；
- 数据校验；
- 指标；
- 图表；
- AI 摘要；
- 报告。

## 阶段 8：实验

- 实验；
- 分组；
- 样本；
- 对比；
- 结果；
- 导出。

## 阶段 9：测试与文档

- 单元测试；
- 接口测试；
- E2E；
- 异常测试；
- 测试报告；
- Windows 部署；
- 数据库设计；
- API 文档；
- 实验文档；
- 答辩演示脚本。

---

# 二十四、Codex 固定工作格式

每次开始前输出：

```text
本次目标：
涉及模块：
预计修改文件：
验收标准：
```

完成后输出：

```text
已完成：
运行结果：
测试结果：
遗留问题：
下一步：
```

遇到错误：

1. 读取完整日志；
2. 找根因；
3. 最小修改；
4. 重新运行；
5. 不注释掉核心功能；
6. 不伪造成功。

---

# 二十五、第一次立即执行的任务

现在先执行阶段 0 和阶段 1。

## 阶段 0

1. 搜索四个参考项目；
2. 生成 `docs/REFERENCE_ANALYSIS.md`；
3. 输出每个项目值得借鉴的具体文件和模块；
4. 标明许可证注意事项；
5. 给出本项目最终模块映射。

## 阶段 1

1. 创建 `socialflow-ai`；
2. 创建 Vue3 + TypeScript + Vite 前端；
3. 创建 FastAPI 后端；
4. 配置 SQLAlchemy、Alembic、MySQL；
5. 实现统一响应；
6. 实现全局异常；
7. 实现 JWT；
8. 实现 RBAC；
9. 实现登录页；
10. 实现工作台基础布局；
11. 创建演示账号；
12. 创建 Windows 启动脚本；
13. 创建 README；
14. 创建开发进度文档；
15. 运行项目；
16. 执行测试；
17. 修复所有编译和运行错误。

阶段 1 验收：

- Windows 能启动；
- 登录页完成度高；
- 演示账号可登录；
- 首页可访问；
- 前后端通信正常；
- Swagger 正常；
- MySQL 表成功创建；
- 无 TypeScript 错误；
- 无 Python 启动错误；
- README 准确；
- Mock 模式可运行。

不要提前开发 AI、日历和数据分析，先保证基础工程稳定。

---

# 二十六、最终交付物

必须包含：

```text
完整源代码
数据库迁移
初始化数据
Mock 数据
Windows 启动脚本
README
参考项目分析
需求文档
系统设计
数据库设计
接口文档
Prompt 文档
实验设计
测试计划
测试报告
实验数据模板
实验报告
部署文档
答辩演示流程
```

---

# 二十七、最终答辩演示流程

8～12 分钟内完成：

1. 登录；
2. 创建原文；
3. 生成微博、小红书、公众号；
4. 修改小红书版本；
5. 选择配图；
6. 查看发布时间推荐；
7. 拖到日历；
8. Mock 模拟发布；
9. 导入互动数据；
10. 查看推荐时间与固定时间对比；
11. 导出报告；
12. 查看审计日志。

---

# 二十八、项目成功标准

1. 主流程完整；
2. 页面精美；
3. Windows 容易运行；
4. Codex 可持续维护；
5. AI 真正嵌入业务流程；
6. 发布时间推荐可解释；
7. 模拟发布完整；
8. 数据分析清晰；
9. 实验可复现；
10. 测试和文档齐全；
11. 不依赖 Linux；
12. 答辩稳定。

请严格根据本文件开始开发。
