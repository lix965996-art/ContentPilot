# ContentPilot 运维

## 本地配置与启动

本地需要 Python 3.12、Node.js 20+。MySQL 配置来自 `backend/.env`；没有可用 MySQL 时可使用已配置的 SQLite 回退。

首次准备环境：

```powershell
Copy-Item backend\.env.example backend\.env
# 修改数据库连接、JWT_SECRET、PLATFORM_CREDENTIAL_KEY
.\contentpilot.ps1 setup
.\contentpilot.ps1 start
```

不要覆盖已有 `backend/.env`。模型通常在管理员“设置 → 模型服务”中配置：填写兼容服务地址、密钥和模型，测试连接后保存。文本兼容接口不代表图片请求也已适配，图片协议限制见 [ROADMAP](ROADMAP.md)。

本地 Web 为 `http://127.0.0.1:5173`，API 为 `http://127.0.0.1:8000`，健康接口为 `/api/health`。管理命令统一使用 `contentpilot.ps1`：

```powershell
.\contentpilot.ps1 status
.\contentpilot.ps1 logs
.\contentpilot.ps1 logs -Follow
.\contentpilot.ps1 stop
.\contentpilot.ps1 db
.\contentpilot.ps1 test
```

`db` 用于 MySQL 初始化；SQLite 环境使用已有配置、迁移和启动流程。启动器执行迁移、启动后台进程、记录 PID 与启动时间，等待健康检查后打开浏览器。停止命令只处理本入口记录的进程。

2026-10 的兼容更新新增指标分母口径和令牌撤销版本。更新前备份数据库；已有指标的分母无法确认时标为 `UNKNOWN`，保留原数据但不比较互动率。旧应用令牌需重新登录，平台扫码资料仍使用原会话目录。退出或改密会撤销该用户全部现有应用令牌。

重启会把已错过执行时间的任务标为“已错过排期”，把停止时正在发布的任务标为“执行中断”，保留日志并提供重新排期入口。执行中断后先核实平台结果，再重新排期。账号、权限或内容预检失败会停止自动重试，修正后可由运营者重试。

## 运行数据目录

默认数据根目录为项目的 `var/`。可在启动前设置环境变量，或在后端配置中指定同一 `CONTENTPILOT_VAR_DIR`：

```powershell
$env:CONTENTPILOT_VAR_DIR = 'F:\ContentPilot-data'
.\contentpilot.ps1 start
```

自定义相对路径按项目根解析。已有数据变更位置时，先停止对应服务并迁移实际数据，再让 API、启动器和测试使用相同目录；仅修改配置不会复制旧数据。

| 子目录      | 用途                                       |
| ----------- | ------------------------------------------ |
| `run/`      | PID、启动时间及服务状态                    |
| `logs/`     | API、前端与本机连接运行日志                |
| `uploads/`  | 系统上传及生成图片，供 `/uploads` 提供服务 |
| `sessions/` | 本机扫码和浏览器登录会话                   |
| `tools/`    | 已安装的本机连接程序                       |
| `cache/`    | 可再生成的工具缓存                         |
| `reports/`  | 测试报告与截图                             |
| `tmp/`      | 临时文件                                   |
| `db/`       | 本地 SQLite 数据库                         |
| `tests/`    | 隔离测试数据，避免触及业务媒体与数据库     |

上传、会话和数据库是业务数据，不能按缓存删除。`backend/.venv` 和 `frontend/node_modules` 是开发依赖；`frontend/dist` 是前端构建输出。`.env`、运行数据和登录资料不进入 Git，Docker 构建也应排除它们。

模型调用账本独立于文章与版本，删除文案不会删除历史费用。MySQL 的账本和月度预留表由 Alembic 管理。
SQLite 为避免模型调用期间与业务写事务争锁，在业务数据库同目录创建 `<业务数据库文件名>.llm-usage.sqlite`；
例如 `var/db/app.db` 对应 `var/db/app.db.llm-usage.sqlite`。该文件只保存调用、价格、币种、预算和未知费用状态，
不保存 API Key 或原文。它属于受保护业务数据；备份、迁移和恢复必须与主数据库一起覆盖，不能当作缓存清理。
伴随账本首次使用时建立结构版本并校验列集合；结构不匹配时拒绝使用，不能通过删库重建来绕过错误。

本地月度预算按当前币种的已知费用和并发预留进行准入检查。预留为估算，不能替代服务商的硬额度或账单；
缺少计价规则的图片/向量调用在预算启用时不会外发。未返回用量、网络中断和进程崩溃的费用保留为未知；
超过调用超时且至少 15 分钟仍未完成的请求标为 `UNCERTAIN` 并释放预留，但不会将其实际费用归零，
预算模式继续阻止新调用。应核对服务商账单；如选择关闭本地预算限制，未知费用告警和历史记录仍会保留。

## Docker 部署

```powershell
Copy-Item .env.example .env
# 设置 MYSQL_PASSWORD、MYSQL_ROOT_PASSWORD、JWT_SECRET、PLATFORM_CREDENTIAL_KEY
# 设置管理员初始密码，关闭演示模式和不需要的注册/发布能力
docker compose up -d --build
docker compose ps
```

默认入口是 `http://127.0.0.1:8080`，API 端口是 `8000`，可以通过 `CONTENTPILOT_PORT`、`CONTENTPILOT_API_PORT` 修改。容器内运行数据使用 `/app/var`。`mysql_data` 保存 MySQL 数据，`uploads` 保留媒体，`runtime_data` 保存其他运行数据；具体挂载以 `compose.yaml` 为准。

```powershell
docker compose logs -f backend
docker compose logs -f web
docker compose up -d --build
docker compose down
```

普通停止保留数据卷。`docker compose down --volumes` 会删除持久化数据，不能作为普通清理步骤。更新前备份数据库和业务数据，恢复验证应覆盖登录、已保存文章及图片访问。

客户独立部署可使用现有工具：

```powershell
.\scripts\new-customer.ps1 -Name acme -Port 8081 -ApiPort 8001
cd .\var\deployments\customers\acme
.\start.ps1
```

默认输出到运行数据目录的 deployments/customers；自定义运行目录或 OutputRoot 时，以脚本显示的位置为准。脚本生成独立 Compose 项目配置、端口和初始密码，部署后检查实际项目名与数据卷隔离。客户实例关闭演示模式，配置自己的模型服务，修改默认密码，并备份该实例的数据库和运行数据卷。

## 操作流程

1. 管理员配置模型服务与需要使用的平台账号。
2. 运营者创建原文，选择平台和 QUICK/DEEP 模式。
3. 对照原文检查事实、质量来源和失败原因，编辑并审核；公众号稿件可使用排版预览。
4. 选择素材或上传图片，核对来源及许可。
5. 导入公开历史，或使用明确标注的演示历史，确认批次、日期范围和时区。
6. 检查候选时间、依据与约束，创建排期并查看日志或交付包。
7. 按实际来源录入指标或查看离线报告，保持演示与公开数据结论分离。

发布复盘与实验页默认选择真实数据，可明确切换演示数据；录入时选择曝光量或粉丝数作为分母。未知、混合分母或真假来源混合时不生成整体互动率对比结论。

完整的跨平台“演示执行”选项还在 [待办](ROADMAP.md) 中，不应把现有人工确认当成已经实现的通用演示执行。

### 历史样例与工具

历史数据集中在 `examples/history/`，合成样例必须保持 `SIMULATED` 来源说明。相关脚本从项目根运行：

```powershell
backend\.venv\Scripts\python.exe examples\history\generate_demo_history.py
backend\.venv\Scripts\python.exe scripts\bootstrap_demo_pipeline.py
backend\.venv\Scripts\python.exe scripts\import_youtube_public_sample.py
```

前两项用于生成或填充演示数据，导入工具会写入配置指向的数据库；不要把演示填充命令当成普通启动步骤。公开数据导入器读取 `examples/history/YouTubeDurationData/`，并保留来源说明。其当前实验是样本内描述性分析，按时间留出的评估仍待完成。

## 可选平台连接

不使用外部平台发布也能进行内容生成、历史分析和排期研究。启用真实发送前应检查账号权限、发布开关和已知发布缺陷；“配置已保存”“连接检测通过”“草稿创建成功”“公开发布成功”是不同结果。

### Bluesky / Mastodon 图文与串帖

配图先上传到本项目并填写图片说明，发布前会按实际顺序冻结图片及说明；Bluesky 的 `alt` 和 Mastodon 的 `description` 都会保留这些说明。Bluesky 单张图上限为 1,000,000 字节，使用小于 900 KB 的 JPEG 可以给编码留出余量。

后台支持受控的串帖任务：每段是独立审核的稿件与排期，首段带图，后续段回复前一段。回复目标、顺序和 Bluesky 的 URI/CID 在写入前持久化，同任务重试不能改挂其他父帖。前一段未确认发布或结果不明时，停止创建后续段。当前页面尚无专用串帖编排入口，不会把超长单帖自动截断或自动拆开发送。

### Mastodon 的可选安全 DNS

若本机 DNS 返回错误的公网地址，Mastodon 可能在连接检测或发布时超时。在 `backend/.env` 设置 `OUTBOUND_DNS_OVER_HTTPS=true` 并重启后端，可让 Mastodon 通过固定的 Cloudflare HTTPS DNS 服务查询 A/AAAA 记录。默认值为 `false`；此选项不会修改 Windows DNS，也不会改变其他平台的解析方式。

DNS 查询沿用 `OUTBOUND_HTTP_PROXY`，校验 HTTPS 证书、拒绝重定向和内网地址；解析失败时明确报错，不回退到本机 DNS。实际请求仍固定到校验后的数字 IP，并保留原实例的 Host、TLS SNI 与证书检查。DNS 服务不会收到平台访问令牌。需要确保配置的代理能访问该解析服务及 Mastodon 实例。

若之前的发布已经返回“结果不明”，不要直接新建任务补发。先从平台核对是否已有帖子，再按原任务的恢复流程处理；Mastodon 的幂等键有效期有限，不能把旧任务当作无限期安全重试。

| 平台       | 配置与操作                                                    | 实际边界                                         |
| ---------- | ------------------------------------------------------------- | ------------------------------------------------ |
| 微博       | 开放平台应用 App Key/App Secret，OAuth 回调地址与配置完全一致 | 连接检测取得账号标识不代表具备发布权限           |
| X          | 官方 OAuth 2.0 + PKCE，配置应用回调和所需授权范围             | 当前发送文字；平台额度与权限需要账号实际验证     |
| 微信公众号 | 本机 Chrome 扫码保存草稿；可选 AppID/AppSecret 与官方接口     | 草稿不是公开发布，正式分支及终态查询存在已知问题 |
| 小红书     | 人工下载发布包并回填结果；可选本机 MCP                        | MCP 是实验性本机能力，不能包装为官方连接         |
| 今日头条   | 本机 Chrome 扫码会话与账号真实发布开关                        | 登录过期、验证码和页面变化需要人工处理           |

本地 OAuth 回调分别为：

- 微博：`http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback`。
- X：`http://127.0.0.1:8000/api/platform-accounts/X/oauth/callback`。

正式域名与反向代理部署时，使用系统显示的对应回调地址，平台后台与应用配置必须一致。微博 `21324` 通常需要检查同一应用的 App Key/App Secret；微信 `40013/40125/40164` 分别涉及 AppID、AppSecret 与出口 IP 白名单。不要把模型密钥填到平台凭证中。

按需配置本机连接：

```dotenv
EXPERIMENTAL_BROWSER_PUBLISHING_ENABLED=true
XHS_MCP_BASE_URL=http://127.0.0.1:18060/mcp
TOUTIAO_BROWSER_PUBLISHING_ENABLED=true
TOUTIAO_BROWSER_HEADLESS=true
WECHAT_BROWSER_PUBLISHING_ENABLED=true
WECHAT_BROWSER_HEADLESS=true
WECHATSYNC_CLI_ENABLED=false
```

开关只启用相应能力，真实发送仍受任务模式与账号级设置约束。浏览器会话保存在本机 `var/sessions`；如果显式配置旧的自定义浏览器目录，以该配置为准。Wechatsync 是可选草稿后备，需要独立安装及登录。Docker 要使用本机扫码能力，需要额外提供浏览器环境。

## 单实例调度边界（D-01）

当前调度器、启动恢复和持久化派发扫描都在同一个后端进程中运行。启动时后端会尝试获取 `var/run/scheduler.lock` 的操作系统文件锁：

- 获取成功的实例标记为 `schedulerRole=active`，执行启动恢复、APScheduler 和派发扫描。
- 未获取到的实例以 `schedulerRole=standby` 启动，仅提供 API，不参与恢复或派发，并在日志中说明原因。`/api/health` 会返回当前角色。
- 锁随进程退出自动释放，正常重启不会留下陈旧锁。

**部署约束**：这套机制只保护同一主机/同一共享运行目录下的多进程。不要在同一运行目录之外启动第二个参与调度的后端，也不要让两个容器各自持有独立的 `var/` 同时连接同一个业务库来执行恢复。需要多主机/多实例时，必须改为数据库租约 + owner/心跳 + 原子接管，并单独验收“活跃任务不被误判、接管后不重复外发”。

派发扫描周期由 `DISPATCH_POLL_SECONDS`（默认 15 秒）控制，单个派发意图最多尝试 `DISPATCH_MAX_ATTEMPTS`（默认 10）次。派发失败会记录在 `task_dispatch.last_error`，业务任务本身不会被删除。

## 互动采集与机器学习

Bluesky/Mastodon新发布成功后，后台自动采集1、24、72小时互动，只有24小时至24小时15分钟的完整观测用于同一训练目标。登录后的“数据”页可以刷新、查看失败原因和手动采集；手动采集不会发送帖子。管理员在“设置→互动学习”管理达到验证门槛的平台模型。没有自有成熟样本时维持统计推荐，并可独立运行公开研究实验。

在项目根目录使用以下命令：

```powershell
# 可选训练依赖，与普通运行环境分离锁定；运行已有统计功能不需要安装。
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-ml.lock.txt

# 只读检查真实数据来源和窗口。
backend\.venv\Scripts\python.exe scripts/audit_ml_data.py

# 不需要自己的发帖数据：获取固定提交、校验SHA-256并运行公开YouTube对照实验。
backend\.venv\Scripts\python.exe scripts/train_engagement_model.py --youtube

# 将来有真实成熟观测后，按平台冻结导出；也可改为MASTODON。
backend\.venv\Scripts\python.exe scripts/export_ml_dataset.py --platform BLUESKY
# 使用上一步实际输出的目录，不要把占位路径直接执行。
backend\.venv\Scripts\python.exe scripts/train_engagement_model.py --dataset var/datasets/ml/<datasetId>
```

下载与模型训练均在本机进行；出站访问沿用`OUTBOUND_HTTP_PROXY`。CSV、JSONL、模型及运行JSON统一位于被Git忽略的`var/datasets`、`var/models`、`var/reports/ml`，不会混在源码根目录。同一数据/训练版本/种子禁止覆盖已冻结的模型，重复执行会明确报已存在；需要独立复现时用`--models var/models-reproduction`指定独立输出目录。

YouTube目标为观看时长比例，缺少原帖正文、账号与确切采集时点，属于回顾性研究，不是Bluesky/Mastodon24小时互动模型。该模型不可启用到两个发布平台。平台模型仍需本平台真实样本、时点可见特征、足够支持、滚动验证、独立测试优势与区间支持；管理员也不能绕过这些门槛。模型文件只接受项目生成的原生CatBoost/LightGBM格式和JSON清单，不支持上传pickle/joblib。

后台采集仅调度主实例执行；数据库任务领取有五分钟租约，429按Retry-After和退避重试，最多六次；执行器提交遵循原派发上限。数据库恢复会重新武装缺失/中断任务，不自动重发帖子。观察窗口已错过会明确被排除，不能把稍后的手动读取冒充24小时数据。

## 排障与验证

| 现象                        | 检查步骤                                                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 无法识别 `contentpilot.ps1` | 进入项目根，确认后缀为 `.ps1`，用 Tab 补全                                                                                                                  |
| 脚本执行被禁止              | 当前 PowerShell 窗口设置 `Set-ExecutionPolicy -Scope Process Bypass`                                                                                        |
| 端口占用或启动失败          | 先 `status`，再查看 `logs`；确认占用者后处理                                                                                                                |
| 数据库连接失败              | 检查 `backend/.env`、服务与凭证；按所选数据库执行迁移                                                                                                       |
| 模型生成失败                | 检查服务商、模型和服务错误，按任务终态处理                                                                                                                  |
| 登录或平台连接失败          | 分开检查本地会话、官方授权、权限和账号开关                                                                                                                  |
| 上传图无法访问              | 检查运行目录配置与文件、`/uploads` 映射、反向代理                                                                                                           |
| Mastodon 连接超时           | 确认服务器网址可达；无法直连时在 `backend/.env` 设置 `OUTBOUND_HTTP_PROXY` 并重启后端；Docker 部署需填容器可达地址（如 `http://host.docker.internal:7892`） |

检查入口为 `.\contentpilot.ps1 test`。浏览器测试使用隔离服务/数据，不能用现有页面截图或只断言页面宽度替代业务验证。部署与演示验收重点是实际保存内容、任务终态、错误、幂等以及重启后的状态；已知边界见 [ROADMAP](ROADMAP.md)。
