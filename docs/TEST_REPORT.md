# 测试报告

测试日期：2026-07-21；环境：Windows、Python 3.12.13、Node 20.19.6、MySQL 8、Chromium。

| 检查 | 结果 |
|---|---|
| Ruff 格式与静态检查 | 通过，56 个 Python/迁移文件 |
| pytest | 14 通过 |
| Prettier | 通过 |
| ESLint | 通过，0 warning |
| vue-tsc + Vite production build | 通过；业务路由已懒加载 |
| Vitest | 3 通过 |
| Playwright Chromium | 3 通过 |
| Alembic MySQL | `d7bc40428afb (head)` |
| MySQL seed | 12 篇文章、36 个平台版本、20 个排期、14 天指标、2 个实验、平台规则与 10 张本地图 |
| API/Web 健康 | 8000/5173 HTTP 200，数据库 connected |
| 启动与部署 | 单一 PowerShell 入口的 stop/status/start/status 实测通过；Compose 配置纳入仓库 |

## 集成覆盖

- operator 新建原文、生成三平台版本、轮询 taskId；
- 发布时间算法返回 `weighted-v1`、理由与备选；
- 创建未来排期、执行 MockPublisher、重复调用保持 `MOCK_SUCCESS`；
- 手工互动数据计算总互动和互动率；
- 实验创建、开始、结束与统计；
- viewer 写接口返回 403；operator 管理员 API 返回 403；
- 浏览器登录、真实工作台、内容、AI、日历、复盘页面。

## 已知非失败警告

Vite 会提示 Element Plus/ECharts 所在共享入口 chunk 超过 500 kB；功能不受影响，重型业务页面已改为懒加载。生产部署可进一步按 Element Plus 按需导入拆分 vendor。本项目本地答辩模式不把该性能提示当作运行错误。

## 数据真实性

自动 seed 的互动、先验和实验样本均为 `SIMULATED`；本地生成和发布为 `MOCK`。测试只证明软件流程、计算和权限可用，不证明真实平台效果。
