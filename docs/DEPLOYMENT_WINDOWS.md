# ContentPilot 启动与部署

## 正式环境：Docker Compose

正式环境使用 `compose.yaml` 管理三个服务：

- `web`：Nginx 提供前端静态文件，并反向代理 `/api` 与 `/uploads`；
- `backend`：FastAPI API、数据库迁移、初始化和任务调度；
- `db`：MySQL 8.4，数据写入命名卷 `mysql_data`。

首次部署：

```powershell
Copy-Item .env.example .env
# 修改 .env 中的数据库密码、JWT_SECRET 和 PLATFORM_CREDENTIAL_KEY
docker compose up -d --build
docker compose ps
```

`backend` 每次启动都会幂等执行 Alembic migration 和基础数据 seed。`web` 只会在 API 健康检查通过后启动。MySQL 数据与用户上传文件保存在 Docker 卷中，普通的 `docker compose down` 不会删除它们。

更新与排障：

```powershell
docker compose up -d --build
docker compose logs -f backend
docker compose logs -f web
docker compose logs -f db
docker compose down
```

不要在生产环境提交 `.env`，不要使用示例密钥，也不要轻易执行 `docker compose down --volumes`。

## Windows 本地开发

本地模式需要 Python 3.12、Node.js 20+ 和 MySQL 8。所有用户操作统一通过根目录的 `contentpilot.ps1`：

```powershell
.\contentpilot.ps1 setup
.\contentpilot.ps1 start
.\contentpilot.ps1 status
.\contentpilot.ps1 logs -Follow
.\contentpilot.ps1 stop
```

启动器会：

1. 检查后端虚拟环境和前端依赖；
2. 执行 Alembic migration；
3. 分别启动 API 与 Vite 开发服务器；
4. 将 PID 和启动时间写入 `.runtime/`；
5. 将日志写入 `logs/`；
6. 等待健康检查通过后打开浏览器。

本地 Web 为 `http://127.0.0.1:5173`，API 文档为 `http://127.0.0.1:8000/docs`。

## 常见问题

- PowerShell 拒绝执行脚本：先运行 `Set-ExecutionPolicy -Scope Process Bypass`；
- 端口 5173/8000 被占用：运行 `.\contentpilot.ps1 status`，不要直接结束未知进程；
- MySQL 连接失败：检查 `backend/.env`，需要时运行 `.\contentpilot.ps1 db`；
- 本地启动失败：运行 `.\contentpilot.ps1 logs`；
- Docker 启动失败：运行 `docker compose ps` 和 `docker compose logs` 查看具体服务。
