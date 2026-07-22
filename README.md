# ContentPilot

ContentPilot 是一个面向内容运营团队的多平台内容工作台。它把原始文章、AI 平台化改写、质量评审、素材选择、排期、发布和数据复盘连接成一条完整工作流。

![ContentPilot AI 素材预览](frontend/public/media/generated/content-adaptation.webp)

## 核心能力

- 同一篇原文并行生成微博、小红书、微信公众号三个独立版本；
- 提供“快速改写”和“深度创作”两种模式；深度创作会依次完成事实简报、平台策略、双候选稿、AI 主编评审与修订定稿；
- “热点选题”读取百度热榜与 Hacker News 的真实公开榜单，保留原始链接和来源状态，并可用真实 LLM 生成选题角度；
- 风格、长度、目标读者、原意保留程度、Emoji 和话题标签等参数真实进入 Prompt；
- 三个平台分别使用独立 Prompt Profile 和 Pydantic 结构化输出模型；
- JSON 校验失败自动重试，单个平台失败不会丢弃其他平台结果；
- 实时显示 `PENDING`、`RUNNING`、`RETRYING`、`SUCCESS`、`FAILED` 和 `PARTIAL_SUCCESS`；
- 规则校验与真实 LLM 语义评审结合，覆盖事实一致性、信息完整度、平台适配度、可读性和格式合规性；
- 支持历史版本、版本对比、编辑保存、拒绝、删除和单平台重新生成；
- 微信公众号版本内置排版助手，支持主题、主题色、字号、行距、段距、首行缩进、外链脚注、实时预览和富文本复制；保存后的内联样式 HTML 会直接用于公众号草稿发布；
- 关键词优先由 LLM 提取，失败时回退本地规则；Markdown 会转换为经过清理的安全 HTML；
- 内置 8 张 AI 生成的本地编辑素材，也可接入 Unsplash；
- 支持平台账号、发布日历、定时任务、发布状态和数据复盘；
- 微博与微信公众号只允许真实官方接口连接；未通过官方验证时禁止创建发布任务；
- 小红书明确采用人工交付，不把人工流程伪装成“已连接”；
- 提供可读的发布时段实验视图，不向普通管理员直接展示原始 JSON。

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
| 管理员 | `admin` | `Admin@123456` | 配置模型、平台账号、用户和系统参数 |
| 运营者 | `operator` | `Operator@123456` | 创作、改写、选图、排期和发布 |
| 查看者 | `viewer` | `Viewer@123456` | 只读查看内容和数据 |

三个账号不是使用 AI 改写所必需的三个人，而是用来演示权限隔离。个人使用时可以一直使用管理员账号；团队使用时，再按职责分配运营者和查看者。正式部署前必须修改演示密码和 `JWT_SECRET`。

## AI 改写怎么用

1. 管理员进入“设置 → 模型服务”，完成一次模型配置。
2. 在“内容库”新建或导入一篇原始文章。
3. 进入“创作”，选择微博、小红书和微信公众号中的一个或多个平台。
4. 选择“快速改写”或“深度创作”，再设置风格、长度、目标受众、原意保留程度、Emoji 和标签偏好。
5. 点击生成。三个平台会并行处理，并分别显示实时进度和失败原因。深度创作还会显示切入角度、开场钩子、候选标题和 AI 选稿结果。
6. 对照原文检查质量分、编辑版本、查看历史或仅重新生成失败的平台。
7. 切换到微信公众号版本，可点击“公众号排版”选择版式并预览，保存后发布草稿会沿用该排版。
8. 在“媒体”选择配图，随后回到内容工作室继续审核、排期和发布。

生成任务会记录模型、服务商、Prompt 版本、Token 用量和耗时，便于成本统计和 Prompt 回归比较。

## 从真实热点开始创作

1. 进入“热点选题”，选择全部、百度热榜或 Hacker News；
2. 系统实时读取公开榜单并展示来源、热度、抓取状态和原始链接，不使用模拟热点补位；
3. 点击“AI 分析选题”，模型会给出 2～3 个角度、目标读者、开场钩子、大纲和发布前核验项；
4. 选择一个角度并点击“用这个角度进入深度创作”；
5. 系统会创建一篇带来源链接和核验提醒的原文，并自动打开深度创作模式。

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
- 配置 `UNSPLASH_ACCESS_KEY` 后可同时搜索 Unsplash；
- 仅在主动开启演示数据时写入的互动样本会标记为 `SIMULATED`，不参与真实发布状态；
- 实验页展示样本量、分组均值、差异和当前结论，样本不足时会明确提示不能形成运营结论。

## 平台发布边界

平台发布不提供模拟成功模式。微博和微信公众号必须先通过官方接口验证，小红书只提供明确标记的人工交付流程。

- 微博真实发布需要开放平台应用审核、OAuth 授权和对应权限；
- 微信公众号推荐使用草稿箱模式：上传素材并创建草稿，不把“创建草稿”显示成已公开发布；
- 小红书提供人工发布包和发布后确认，不保存 Cookie/密码，也不执行浏览器注入；
- 项目不使用 Selenium、Cookie 注入或非官方发布接口。

在“平台账号”页为各平台配置凭证和发布模式。真实凭证仅在服务端加密保存。

完整申请步骤、回调地址和常见错误见 [真实平台连接指南](docs/PLATFORM_CONNECTION.md)。

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
├─ docs/                    系统、API、部署与测试文档
└─ README.md
```

更多文档：[Windows 部署](docs/DEPLOYMENT_WINDOWS.md)、[系统设计](docs/SYSTEM_DESIGN.md)、[API 设计](docs/API_DESIGN.md)、[测试报告](docs/TEST_REPORT.md)。

## License

本项目基于 [Apache License 2.0](LICENSE) 开源。
