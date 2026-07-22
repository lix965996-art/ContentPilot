# 测试报告

测试日期：2026-07-22；环境：Windows、Python 3.12.13、Node 20.19.6、MySQL 8、Chromium。

| 检查 | 结果 |
|---|---|
| Ruff 格式与静态检查 | 通过，77 个 Python/迁移文件 |
| pytest | 39 通过 |
| Prettier | 通过 |
| ESLint | 通过，0 warning |
| vue-tsc + Vite production build | 通过；业务路由已懒加载 |
| Vitest | 3 通过 |
| Playwright Chromium | 13 通过 |
| Alembic MySQL | `20260722_0008 (head)` |
| MySQL seed | 12 篇文章、36 个平台版本、20 个排期、14 天指标、2 个实验、平台规则与 10 张本地图 |
| API/Web 健康 | 8000/5173 HTTP 200，数据库 connected；硅基流动模型列表真实连接通过 |
| 启动与部署 | 单一 PowerShell 入口的 stop/status/start/status 实测通过；Compose 配置纳入仓库 |

## 集成覆盖

- operator 新建原文、生成三平台版本、轮询 taskId；
- 发布时间算法返回 `weighted-v1`、理由与备选；
- 真实发布适配器边界拦截官方 HTTP 响应，验证成功结果与幂等；
- 未通过官方连接验证的微博和公众号账号无法创建发布任务；
- 小红书人工交付包、下载和发布后链接确认；
- 手工互动数据计算总互动和互动率；
- 实验创建、开始、结束与统计；
- viewer 写接口返回 403；operator 管理员 API 返回 403；
- 浏览器登录、真实工作台、内容、AI、日历、复盘页面。

## 已知非失败警告

Vite 会提示 Element Plus/ECharts 所在共享入口 chunk 超过 500 kB；功能不受影响，重型业务页面已改为懒加载。生产部署可进一步按 Element Plus 按需导入拆分 vendor。本项目本地答辩模式不把该性能提示当作运行错误。

## 数据真实性

测试环境会拦截外部 HTTP 边界，不会调用或收费于真实账号；产品运行时没有模拟连接或模拟发布成功路径。主动开启的演示互动样本仍标记为 `SIMULATED`，不证明真实平台效果。
