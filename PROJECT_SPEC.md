# ContentPilot 项目规格摘要

项目严格依据 `socialflow_ai_codex_final_prompt.md` 实现，固定技术栈为 Vue 3 + TypeScript + FastAPI + MySQL 8。

核心研究问题：

1. 大语言模型辅助生成三平台版本，能否降低人工改写时间并保持事实一致性；
2. 结合平台先验与账号历史的可解释推荐时间，能否提高互动率。

系统边界：真实社交平台权限不可得时，只提供 Mock 发布与人工确认；所有模拟数据必须标记；系统不以自动化浏览器绕过平台权限。完整需求和验收项见 [需求文档](docs/REQUIREMENTS.md)。
