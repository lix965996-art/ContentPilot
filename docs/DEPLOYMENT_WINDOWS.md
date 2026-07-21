# Windows 部署与启动

## 前置环境

- Windows 10/11；
- Python 3.12；项目已有 `.venv` 时不依赖当前 Conda 激活状态；
- Node.js 20+；
- MySQL 8，默认 `root / 123456 @ 127.0.0.1:3306`。

用户的 Conda 位于 F 盘时无需移动。首次安装脚本会依次检查 `py -3.12` 和 `F:\anaconda3`、`F:\miniconda3` 等常见路径。若 F 盘环境不是 Python 3.12，请保留项目现有 `.venv` 或安装 3.12 环境。

## 推荐启动

第一次或依赖有变化时双击 `首次安装或更新依赖.bat`。之后只需双击 `启动 ContentPilot.bat`；它不会重复安装依赖，会：

1. 检查 venv、Node 和 Vite；
2. 检查端口是否被非本项目进程占用；
3. 后台启动 API 与 Web；
4. 写日志到 `logs/api*.log` 和 `logs/web*.log`；
5. 等待两个健康地址返回 200；
6. 打开浏览器。

`查看运行状态.bat` 查看精确 PID；`停止 ContentPilot.bat` 校验 PID 和启动时间后停止该进程树，不按端口误杀其他程序。

兼容命令行入口：`scripts\start-dev.bat`、`scripts\stop-dev.bat`、`scripts\init-db.bat`、`scripts\run-tests.bat`。

## 环境变量

复制 `backend/.env.example` 为 `backend/.env`。生产或联网演示至少修改：

```env
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/socialflow?charset=utf8mb4
JWT_SECRET=至少32位随机字符串
LLM_PROVIDER=mock
PUBLISH_MODE=mock
```

OpenAI 兼容模型还需要 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。无密钥保持 mock 即可完全离线运行。

## 常见错误

- 端口 5173/8000 占用：查看提示，不要直接杀未知进程；关闭占用程序或修改启动端口及 Vite 代理。
- MySQL 连接失败：确认 MySQL80 服务、账号密码和数据库端口；运行 `scripts\init-db.bat`。
- 首次没有 Chromium：在 `frontend` 执行 `npx playwright install chromium`。
- 启动失败：查看 `logs/api-error.log` 或 `logs/web-error.log`。
- 页面提示外部模型失败：系统会回退 Mock；核对 Base URL 是否包含正确版本路径和 Key。

正式公开部署前必须修改演示账号、JWT 密钥、数据库密码和 CORS 白名单，并使用 HTTPS 反向代理。
