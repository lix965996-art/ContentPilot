# SocialFlow AI

面向自媒体运营者和校园新媒体团队的社交媒体内容适配排期系统。系统把“原文 → AI 多平台版本 → 配图 → 发布时间推荐 → 日历排期 → 模拟/人工发布 → 数据复盘 → 对照实验”连成一个可运行的工作流。

## 功能

- Vue 3 + TypeScript 现代运营工作台，适配桌面与移动端；
- FastAPI + SQLAlchemy + MySQL 8，Alembic 管理数据库迁移；
- JWT access/refresh token、BCrypt、ADMIN/OPERATOR/VIEWER RBAC；
- 文章 CRUD、版本历史、审核和审计日志；
- 微博、小红书、微信公众号生成；支持 OpenAI 兼容接口与离线 Mock 降级；
- 图片关键词、本地备用图库与来源记录；
- 可解释发布时间评分、FullCalendar 拖拽排期；
- APScheduler、MockPublisher、ManualConfirmPublisher、日志、重试与幂等；
- CSV/XLSX 数据导入、ECharts 复盘、HTML 报告；
- 内容效率和发布时间对照实验。

所有示例互动数据、平台先验和本地生成结果都醒目标记 `SIMULATED` 或 `MOCK`，不冒充真实平台数据。

## 最方便的 Windows 启动方式

首次使用只运行一次：

```text
首次安装或更新依赖.bat
```

以后双击：

```text
启动 SocialFlow AI.bat
```

启动器不会每次重装依赖，不会弹出两个长期占用的命令窗口。它会在后台启动服务、写入 `logs/`，等待健康检查通过后打开浏览器。停止和检查状态分别使用：

```text
停止 SocialFlow AI.bat
查看运行状态.bat
```

兼容已存在的 `backend/.venv`，首次创建环境时会检查 `py -3.12` 以及 F 盘常见 Conda 安装路径。

- Web：<http://127.0.0.1:5173>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 演示账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 管理员 | `admin` | `Admin@123456` |
| 内容运营者 | `operator` | `Operator@123456` |
| 查看者 | `viewer` | `Viewer@123456` |

演示密码只用于本地。部署前必须修改密码和 `JWT_SECRET`。

## 测试

```bat
scripts\run-tests.bat
```

也可以分别运行：

```bat
cd backend
.venv\Scripts\python.exe -m ruff check app alembic
.venv\Scripts\python.exe -m pytest

cd ..\frontend
npm run format:check
npm run lint
npm run build
npm run test:run
npm run test:e2e
```

## 外部服务与降级

- 默认 `LLM_PROVIDER=mock`，不需要 API Key；配置 OpenAI 兼容接口后可调用 DeepSeek、通义千问或 OpenAI 兼容模型；调用失败自动回退 Mock，并记录警告。
- 无 Unsplash Key 时使用 10 张本地 SVG 备用图；页面明确标记 `LOCAL FALLBACK`。
- 默认发布器为 MockPublisher，不访问任何真实社交平台；人工模式等待运营者手工确认。
- 不使用 Selenium、Cookie 注入或非官方发布接口。

完整说明见 [Windows 部署](docs/DEPLOYMENT_WINDOWS.md)、[系统设计](docs/SYSTEM_DESIGN.md)、[API 设计](docs/API_DESIGN.md) 和 [测试报告](docs/TEST_REPORT.md)。
