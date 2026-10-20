# ContentPilot

多平台内容适配与排期系统：原文 → 大语言模型生成 → 编辑审核 → 历史活跃度分析 → 推荐与排期 → 交付与复盘。

毕业设计以合成演示数据和有来源的公开历史数据为主，保留演示操作；真实社交平台发布属于可选扩展。公开数据的离线分析不能写成已经验证的线上运营提升。已知问题与验收要求见 [ROADMAP](docs/ROADMAP.md)。

## 互动采集与机器学习

Bluesky/Mastodon 新帖可自动采集1、24、72小时互动，在“数据”页查看记录或手动采集。训练按平台与24小时目标隔离，合格模型可由管理员启停；没有成熟数据或模型未达标时使用统计推荐。

没有自有发帖数据时，也可运行作者公开的 YouTube 观看时长研究实验。它只提供回顾性预测证据，不能用于两个社交平台的发布效果承诺。安装可选依赖、复现命令和当前实测结果见 [OPERATIONS](docs/OPERATIONS.md#互动采集与机器学习) 与 [交付记录](docs/REMEDIATION_REPORT.md)。

## 技术栈

| 层       | 当前实现                                                   |
| -------- | ---------------------------------------------------------- |
| 前端     | Vue 3、TypeScript、Vite、Tailwind CSS、Element Plus、Pinia |
| 后端     | Python 3.12、FastAPI、SQLAlchemy、Alembic、APScheduler     |
| 数据库   | MySQL 8；本地开发支持 SQLite 回退                          |
| 质量检查 | Ruff、Pytest、ESLint、Prettier、Vitest、Playwright         |

API 统一使用 `{ code, data, message }`，当前响应另带 `traceId` 便于定位错误。`code = 0` 表示业务成功。

## 本地运行

需要 Python 3.12、Node.js 20+；使用 MySQL 时先配置数据库。首次安装：

```powershell
cd E:\Bye-bye\1.0\socialflow-ai
.\contentpilot.ps1 setup
.\contentpilot.ps1 start
```

打开 [本地工作台](http://127.0.0.1:5173)，API 文档位于 [8000/docs](http://127.0.0.1:8000/docs)。在管理员“设置 → 模型服务”中填写服务地址、密钥和模型，测试连接后保存。

启用 `APP_DEMO_MODE` 的开发环境提供 `admin / Admin@123456`、`operator / Operator@123456`、`viewer / Viewer@123456`。管理员配置模型和账号，运营者演示内容业务，查看者只读访问；正式部署应修改密码并关闭演示模式。

所有日常管理使用同一个入口：

| 命令                              | 用途                             |
| --------------------------------- | -------------------------------- |
| `.\contentpilot.ps1 setup`        | 安装或更新依赖，执行迁移和初始化 |
| `.\contentpilot.ps1 start`        | 启动本地 API 与前端              |
| `.\contentpilot.ps1 status`       | 查看服务状态                     |
| `.\contentpilot.ps1 logs -Follow` | 跟随运行日志                     |
| `.\contentpilot.ps1 stop`         | 停止本入口管理的服务             |
| `.\contentpilot.ps1 db`           | 初始化 MySQL 数据库并执行迁移    |
| `.\contentpilot.ps1 test`         | 运行后端、前端与浏览器检查       |

PowerShell 禁止执行脚本时，可在当前窗口运行 `Set-ExecutionPolicy -Scope Process Bypass`。详细配置与排障见 [OPERATIONS](docs/OPERATIONS.md)。

## Bluesky 个人账号接入

管理员在“平台账号 → Bluesky”填写完整账号名（如 `name.bsky.social`）和在 Bluesky 设置中生成的应用密码，保存后点击“检测连接”。应用密码与访问会话加密存储，不会回显到页面。连接检测只验证身份，不会发帖；准备好稿件后开启真实发布开关，再由运营者审核、排期或立即发布。

Bluesky 帖子最多 300 个可见字符（包含标题、正文、话题）及 3000 个 UTF-8 字节，最多 4 张图片。目前配图使用项目内上传素材，支持 JPEG、PNG、WebP，每张不超过 1 MB；远程图片需先上传，校验失败会明确提示。同一排期重试会核对固定帖子标识及图文内容，避免请求中断造成重复发帖。连接和模拟测试通过不等于真实发布已验证。

## Mastodon 个人账号接入

在注册账号所在服务器的“偏好设置 → 开发”中新建 ContentPilot 应用，选择 `read:accounts`、`write:statuses`、`write:media`，将应用的个人访问令牌填入管理员“平台账号 → Mastodon”。服务器填写 HTTPS 根网址（例如 `https://mastodon.social`），保存后检测连接；连接检测只读取账号与实例限制，不会发帖。令牌加密保存且不回显，更换服务器必须同时输入该服务器的新令牌。断开只清除本项目本地授权；需要撤销令牌时应到服务器的应用设置操作。如果服务器在当前网络无法直连，在 `backend/.env` 设置 `OUTBOUND_HTTP_PROXY`（例如 `http://127.0.0.1:7892`）并重启后端。

开启真实发布后，可使用现有审核、排期与发布回执流程。默认限制为 500 个可见字符（URL 默认计 23 字符）和 4 张配图，最终还会遵守连接实例的更低限制。支持项目内 JPEG、PNG、WebP 图片，每张最多 8 MB，并按实例限制进一步收紧。重试复用同一幂等标识；结果未明超过安全窗口时会停止自动发送，要求先核对个人主页。请遵守所选服务器的内容规则，包括适用的 AI 内容披露要求。

## 工程目录

```text
socialflow-ai/
├─ backend/                API、模型、迁移与测试
├─ frontend/               页面、组件、样式与测试
├─ scripts/                开发、部署、数据导入与回归工具
├─ examples/history/       演示历史与公开数据样例
├─ docs/                   设计、使用、待办和修复记录
├─ var/                    本机运行数据，默认不进入 Git
├─ contentpilot.ps1        本地统一管理入口
├─ compose.yaml            Docker 部署入口
├─ .env.example            Docker 环境变量模板
└─ README.md
```

`var/` 集中存放运行状态、业务数据、会话、工具、缓存及测试产物；设置 `CONTENTPILOT_VAR_DIR` 可指定其他位置，默认是本项目的 `var/`。后端配置保存在 `backend/.env`，已安装依赖仍位于 `backend/.venv` 与 `frontend/node_modules`。

## Docker 部署

```powershell
Copy-Item .env.example .env
# 修改 MYSQL_PASSWORD、MYSQL_ROOT_PASSWORD、JWT_SECRET、PLATFORM_CREDENTIAL_KEY
# 关闭 APP_DEMO_MODE，并设置 ADMIN_INITIAL_PASSWORD
docker compose up -d --build
```

默认 Web 地址为 [127.0.0.1:8080](http://127.0.0.1:8080)，API 健康检查为 [8000/api/health](http://127.0.0.1:8000/api/health)。数据库与运行数据需要持久化；不要使用 `docker compose down --volumes` 清理普通运行环境。

## 检查与文档

运行 `.\contentpilot.ps1 test` 执行完整检查。需要单独定位时，后端使用 Ruff/Pytest，前端使用 `npm run lint`、`npm run format:check`、`npm run build`、`npm run test:run` 与 `npm run test:e2e`。

GitHub 的 push 和 pull request 使用同一检查入口，浏览器测试使用独立 SQLite 和本机不可用模型地址，避免调用真实模型或写入业务数据库。运行数据和诊断产物统一保存在 `var/`。

```powershell
backend\.venv\Scripts\python.exe scripts\prompt-regression.py
```

上面的 Prompt 工具执行离线规则回归；其中字符估算、字符串差异和本地耗时不能作为真实模型用量、人工修改量或模型效率实验的证据。

- [DESIGN](docs/DESIGN.md)：研究范围、架构、业务模型与实验设计。
- [OPERATIONS](docs/OPERATIONS.md)：配置、部署、平台连接与故障排查。
- [ROADMAP](docs/ROADMAP.md)：已确认问题、实现顺序与验收标准。
- [修复记录](docs/REMEDIATION_REPORT.md)：当前修复、验证结果与账号接入状态。
- [后续改进方案](docs/IMPROVEMENT_PLAN.md)：Bluesky/Mastodon 反馈闭环、机器学习接入步骤、GitHub 参考与验收标准。

项目使用 [Apache License 2.0](LICENSE)。
