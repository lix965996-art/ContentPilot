# ContentPilot

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](frontend/package.json)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688.svg)](backend/requirements.txt)

ContentPilot 是一个面向内容运营团队的多平台 AI 内容工作台。它把原始素材、选题研究、平台化创作、质量评审、智能配图、发布预览、排期、真实平台连接和数据复盘串成一条可检查的工作流。

> 项目不会用模拟数据伪装发布成功。平台登录、草稿创建和公开发布会分别记录状态；浏览器扫码会话只保存在运行 ContentPilot 的本机。

## 快速导航

- [核心能力](#核心能力)
- [平台能力矩阵](#平台能力矩阵)
- [Docker 正式启动](#正式启动推荐)
- [Windows 本地启动](#windows-本地开发启动)
- [完整使用流程](#ai-改写怎么用)
- [平台账号与发布边界](#平台发布边界)
- [测试与质量检查](#测试)
- [运维与故障排查](docs/OPERATIONS.md)

## 工作流概览

```text
热点 / 原文 / 灵感
        ↓
快速改写或深度创作（研究 → 策略 → 候选稿 → 主编评审）
        ↓
微博 / X / 小红书 / 微信公众号 / 今日头条独立版本
        ↓
平台预览与编辑 → 质量审核 → 配图 → 草稿或发布任务
        ↓
运行中心 → 日历与排期 → 用量、费用和效果复盘
```

![ContentPilot AI 素材预览](frontend/public/media/generated/content-adaptation.webp)

## 核心能力

- 同一篇原文并行生成微博、X、小红书、微信公众号、今日头条五个独立版本；
- 提供“快速改写”和“深度创作”两种模式；深度创作会依次完成事实简报、平台策略、双候选稿、AI 主编评审与修订定稿；
- “选题研究”读取百度热榜与 Hacker News 的真实公开榜单，保留原始链接和来源状态，并可用真实 LLM 生成选题角度；分析结果与自建笔记可保存到灵感库，稍后从灵感条目直接进入创作；
- 风格、长度、目标读者、原意保留程度、Emoji 和话题标签等参数真实进入 Prompt；
- 五个平台分别使用独立 Prompt Profile 和 Pydantic 结构化输出模型；
- JSON 校验失败自动重试，单个平台失败不会丢弃其他平台结果；
- 实时显示 `PENDING`、`RUNNING`、`RETRYING`、`SUCCESS`、`FAILED` 和 `PARTIAL_SUCCESS`；
- 规则校验与真实 LLM 语义评审结合，覆盖事实一致性、信息完整度、平台适配度、可读性和格式合规性；
- 支持历史版本、版本对比、编辑保存、拒绝、删除和单平台重新生成；
- 微信公众号版本内置排版助手，支持主题、主题色、字号、行距、段距、首行缩进、外链脚注、实时预览和富文本复制；保存后的内联样式 HTML 会直接用于公众号草稿发布；
- 关键词优先由 LLM 提取，失败时回退本地规则；Markdown 会转换为经过清理的安全 HTML；
- 内置 8 张 AI 生成的本地编辑素材，也可接入 Unsplash；
- 内容工作室右侧内置智能配图助手：可搜索相关素材、调用已配置服务商的真实图片模型生成封面，并用现有图片进行 AI 改造；服务商临时图片会立即下载到本地永久保存；
- 支持平台账号、发布日历、定时任务、发布状态和数据复盘；
- 运行中心集中展示每次发布任务的执行步骤、失败原因和重试次数，未完成的步骤附带处理建议，并支持仅重试失败的平台；
- 微博与 X 使用真实官方接口；微信公众号可选本机扫码保存草稿或 AppID/AppSecret 官方接口；
- 小红书明确采用人工交付，不把人工流程伪装成“已连接”；
- 今日头条提供可选的本机 Chrome 扫码登录与无封面文章发布；Cookie 只保存在本机独立浏览器目录，真实发布默认由账号级安全开关阻止；
- 提供可读的发布时段实验视图，不向普通管理员直接展示原始 JSON。

## 平台能力矩阵

| 平台 | 内容生成与预览 | 账号连接 | 当前交付方式 |
| --- | --- | --- | --- |
| 微博 | 短正文、话题标签、配图预览 | 官方 OAuth | 官方 API 发布 |
| X | 字符限制与帖子预览 | OAuth 2.0 + PKCE | 官方 API 文字发布 |
| 小红书 | 标题、正文、标签和图片组合 | 人工交付；可选本机 MCP 扫码 | 下载发布包或实验性 MCP |
| 微信公众号 | 长文排版、手机预览、标题与正文微调 | 本机 Chrome 扫码；可选 AppID/AppSecret | 保存真实草稿，已选图片会上传到微信素材域名 |
| 今日头条 | 长文和移动端预览 | 可选本机 Chrome 扫码 | 实验性浏览器发布，默认受安全开关保护 |

本机浏览器连接依赖 Google Chrome，适合在 Windows 本地开发模式使用。Cookie 和扫码登录资料不会写入数据库，也不会进入 Git；Docker 部署若要使用这些连接，需要额外提供宿主机浏览器能力。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Pinia、Element Plus、Tailwind CSS、ECharts、FullCalendar |
| 后端 | FastAPI、SQLAlchemy、Pydantic、Alembic、APScheduler |
| 数据库 | MySQL 8，开发环境支持 SQLite 回退 |
| 测试 | Pytest、Ruff、Vitest、ESLint、Prettier、Playwright |

## 正式启动（推荐）

正式运行统一使用 Docker Compose，前端由 Nginx 提供，后端和 MySQL 分别运行在独立容器中，数据库与上传文件使用持久化卷保存。需要先安装 Docker Desktop，或安装带 Compose 插件的 Docker Engine。

```powershell
Copy-Item .env.example .env
# 打开 .env，至少更换四项密码和密钥
docker compose up -d --build
```

启动后访问：

- Web：http://127.0.0.1:8080
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

常用维护命令：

```powershell
docker compose ps                 # 查看状态
docker compose logs -f            # 查看日志
docker compose up -d --build       # 更新代码后重新构建
docker compose down                # 停止服务，保留数据
docker compose down --volumes      # 停止并删除数据，仅在确定要重置时使用
```

首次启动会自动执行数据库迁移和基础数据初始化。管理员可以随后在“设置 → 模型服务”中配置硅基流动或其他 OpenAI 兼容模型。

## Windows 本地开发启动

不使用 Docker 时，需要 Python 3.12、Node.js 20+ 和 MySQL 8。仓库只保留一个管理入口：

```powershell
.\contentpilot.ps1 setup          # 首次安装或更新依赖
.\contentpilot.ps1 start          # 后台启动本地开发服务
.\contentpilot.ps1 status         # 查看状态
.\contentpilot.ps1 logs           # 查看最近日志
.\contentpilot.ps1 logs -Follow   # 持续跟踪日志
.\contentpilot.ps1 stop           # 停止服务
.\contentpilot.ps1 test           # 运行全部检查
```

如果当前 PowerShell 禁止运行本地脚本，只对当前终端临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

本地开发页面为 http://127.0.0.1:5173。该模式使用 Vite 开发服务器，适合调试，不作为正式部署方式。

## 演示账号与角色

| 角色 | 用户名 | 密码 | 用途 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `Admin@123456` | 统一配置模型、授权平台账号、管理用户和系统参数，也可发布 |
| 运营者 | `operator` | `Operator@123456` | 使用管理员已授权的平台账号进行创作、改写、选图、排期和发布，不能查看密钥或修改授权 |
| 查看者 | `viewer` | `Viewer@123456` | 只读查看内容、日历和数据，不能进入平台账号及系统设置 |

三个账号不是使用 AI 改写所必需的三个人，而是用来演示权限隔离。平台账号按系统共享：管理员只需授权一次，运营者即可在排期和发布时选择该账号，但接口不会向运营者返回 Token、Client Secret 等敏感信息。个人使用时可以一直使用管理员账号；团队使用时，再按职责分配运营者和查看者。正式部署前必须修改演示密码和 `JWT_SECRET`。

## AI 改写怎么用

1. 管理员进入“设置 → 模型服务”，完成一次模型配置。
2. 在“内容库”新建或导入一篇原始文章。
3. 进入“创作”，选择微博、X、小红书、微信公众号和今日头条中的一个或多个平台。
4. 选择“快速改写”或“深度创作”，再设置风格、长度、目标受众、原意保留程度、Emoji 和标签偏好。
5. 点击生成。五个平台会并行处理，并分别显示实时进度和失败原因。深度创作还会显示切入角度、开场钩子、候选标题和 AI 选稿结果。
6. 对照原文检查质量分、编辑版本、查看历史或仅重新生成失败的平台。
7. 切换到微信公众号版本，可点击“公众号排版”选择版式并预览，保存后发布草稿会沿用该排版。
8. 在“媒体”选择配图，随后回到内容工作室继续审核、排期和发布。

生成任务会记录模型、服务商、Prompt 版本、Token 用量和耗时，便于成本统计和 Prompt 回归比较。

## 从真实热点开始创作

1. 进入“选题研究”，选择全部、百度热榜或 Hacker News；
2. 系统实时读取公开榜单并展示来源、热度、抓取状态和原始链接，不使用模拟热点补位；
3. 点击“AI 分析选题”，模型会给出 2～3 个角度、目标读者、开场钩子、大纲和发布前核验项；
4. 选择一个角度并点击“用这个角度进入深度创作”；
5. 系统会创建一篇带来源链接和核验提醒的原文，并自动打开深度创作模式。

AI 分析结果可保存到灵感库；也可以手动新增灵感条目记录标题、来源和研究笔记，之后随时从灵感库把选题转入创作。

热点榜单只作为选题线索，不等同于已经核验的新闻事实。发布前应始终打开原始来源复核；单个来源读取失败时，页面会保留其他成功来源并明确显示失败原因。

## 配置硅基流动或其他模型

系统支持硅基流动，也支持任意兼容 OpenAI Chat Completions 的服务。

硅基流动配置示例：

| 配置项 | 内容 |
| --- | --- |
| 服务商 | 硅基流动 |
| API Base URL | `https://api.siliconflow.cn/v1` |
| API Key | 在硅基流动控制台创建的有效密钥 |
| 可用模型 | 测试连接成功后，从返回的文本/对话模型中选择 |

点击“测试连接”，选择模型，再点击“保存配置”。若使用其他兼容服务，选择自定义服务商并填写它提供的 Base URL、Key 和模型名即可。

密钥只在后端加密保存，接口不会返回完整密钥。不要把真实密钥写入源码、截图或提交到 Git；`backend/.env` 已被忽略。密钥一旦公开，请立即在服务商控制台撤销并重新创建。

也可以复制环境变量模板：

```powershell
Copy-Item backend\.env.example backend\.env
```

然后至少修改数据库、`JWT_SECRET` 和 `PLATFORM_CREDENTIAL_KEY`。模型服务更推荐在管理员设置页配置。

## 素材与数据说明

- 项目内置 8 张由 AI 生成的 WebP 编辑素材，位于 `frontend/public/media/generated/`；
- “相关图片”默认联网搜索无需密钥的 Wikimedia Commons，并显示来源入口；配置 `UNSPLASH_ACCESS_KEY` 后会同时合并 Unsplash 结果；网络失败时会明确报错，不会用本地素材冒充搜索结果；
- 硅基流动配置完成后，智能配图会实时读取账号可用的文生图和图生图模型；图片生成与改造会产生服务商费用；
- 从热点榜单带入的图片只作为来源参考图，正式发布前需要自行确认版权和使用许可；
- 仅在主动开启演示数据时写入的互动样本会标记为 `SIMULATED`，不参与真实发布状态；
- 实验页展示样本量、分组均值、差异和当前结论，样本不足时会明确提示不能形成运营结论。

## 平台发布边界

平台发布不提供模拟成功模式。微博和 X 使用官方接口；微信公众号支持本机扫码草稿与官方 API 两种通道；小红书默认采用明确标记的人工交付流程；今日头条使用可选的本机浏览器会话，并要求管理员显式开启账号级真实发布开关。

- 微博真实发布需要开放平台应用审核、OAuth 授权和对应权限；
- X 使用官方 OAuth 2.0 + PKCE 和 `POST /2/tweets`；管理员必须显式开启公开发布并完成授权，连接测试只读取账号信息，不会发送测试帖；
- 当前 X 自动发布器只发送文字，所选图片不会随 X 帖子上传；静态图片上传和视频分片上传作为后续可选能力；
- 微信公众号推荐本机扫码草稿模式：登录会话仅保存在本机独立 Chrome 目录，创作页可直接存入真实草稿箱，不会点击公开发布；本地图片和公网图片会先完成上传并核对插入数量，缺图时任务会明确失败而不是生成无图草稿；已获开发接口权限的公众号仍可使用 AppID/AppSecret 通道；
- 小红书默认提供人工发布包和发布后确认；可选的 `xiaohongshu-mcp` 只连接本机服务，ContentPilot 不接收或保存小红书 Cookie/密码；
- 今日头条参考社区成熟方案，使用 Playwright 持久化本机 Chrome 会话：首次扫码、后续复用登录，并在页面返回明确成功状态后才记录发布成功；当前首版稳定发布路径选择“无封面”，遇到登录失效、验证码或页面变化会停止并提示人工处理；
- 微信公众号可选用 Wechatsync 作为官方草稿接口不可用时的本机草稿同步后备方案；该方案不会把“进入草稿箱”显示为“已经公开发布”；
- 本地连接不会生成虚假的平台 ID，也不会把“连接测试通过”伪装成“平台发布成功”。

管理员在“平台账号”页为各平台统一配置凭证和发布模式；运营者只能检测连接并使用已授权账号，不能读取或修改凭证。真实凭证仅在服务端加密保存。

完整申请步骤、回调地址和常见错误见 [运维与操作手册](docs/OPERATIONS.md)。

### 可选的本机发布连接

只在明确接受实验性浏览器自动化的维护成本和平台风控风险后启用：

```dotenv
# 小红书：启动本机 xpzouying/xiaohongshu-mcp 后开启
EXPERIMENTAL_BROWSER_PUBLISHING_ENABLED=true
XHS_MCP_BASE_URL=http://127.0.0.1:18060/mcp

# 今日头条：允许启动本机 Playwright/Chrome 登录桥；真实发送仍需在平台账号页单独确认
TOUTIAO_BROWSER_PUBLISHING_ENABLED=true
TOUTIAO_BROWSER_HEADLESS=true
# 可选：自定义仅本机可见的浏览器会话目录
# TOUTIAO_BROWSER_PROFILE_ROOT=C:\Users\you\.contentpilot\toutiao

# 微信公众号：本机 Chrome 扫码保存草稿（默认开启）
WECHAT_BROWSER_PUBLISHING_ENABLED=true
WECHAT_BROWSER_HEADLESS=true
# WECHAT_BROWSER_PROFILE_ROOT=C:\Users\you\.contentpilot\wechat

# 可选后备：安装并登录 @wechatsync/cli
WECHATSYNC_CLI_ENABLED=true
```

微信公众号在“平台账号”选择“本机扫码（推荐）”并完成扫码后，在“创作”切换到公众号版本，点击“存入公众号草稿箱”即可。保存过程会显示已等待秒数和当前阶段；任务只有在微信编辑器确认标题、正文及已选图片全部写入后才会标记成功。启用小红书开关后，在“平台账号”选择“本机小红书 MCP 试运行”，扫码登录并通过连接检测，排期页才会显示可用的 MCP 发布方式。Wechatsync 只作为草稿同步后备。

## 本地开发

后端：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

填充演示工作区：

```powershell
backend\.venv\Scripts\python.exe backend\app\db\seed_realistic_workspace.py
```

## 测试

一键运行完整检查：

```powershell
.\contentpilot.ps1 test
```

也可以分别运行：

```powershell
cd backend
.venv\Scripts\python.exe -m ruff format --check app alembic
.venv\Scripts\python.exe -m ruff check app alembic
.venv\Scripts\python.exe -m pytest

cd ..\frontend
npm run format:check
npm run type-check
npm run lint
npm run test:run
npm run build
npm run test:e2e
```

Prompt 回归数据包含至少 20 篇文章，并比较旧、新 Prompt 的平台格式合规率、事实一致性、信息完整度、耗时、Token 用量和人工修改比例：

```powershell
backend\.venv\Scripts\python.exe scripts\prompt-regression.py
```

## 项目结构

```text
socialflow-ai/
├─ compose.yaml             正式环境容器编排
├─ contentpilot.ps1         Windows 本地统一管理入口
├─ backend/                 FastAPI 服务、模型、迁移与测试
├─ frontend/                Vue 3 前端和 Playwright 测试
├─ scripts/                 管理命令内部实现、测试和回归脚本
├─ sample-data/             示例文章、互动数据与平台先验参数
├─ docs/                    系统、API、部署与测试文档
└─ README.md
```

更多文档：[设计文档](docs/DESIGN.md)（需求、架构、数据库、API、Prompt、实验、测试计划）、[运维与操作手册](docs/OPERATIONS.md)（部署、平台连接、答辩演示）；历史快照见 [docs/archive/](docs/archive/)。

## License

本项目基于 [Apache License 2.0](LICENSE) 开源。
