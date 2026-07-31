# UI 参考调研

调研日期：2026-07-21。只借鉴信息架构、密度、导航和响应式处理，没有复制参考项目源码。

| 项目 | 技术与许可证 | 借鉴点 | 本项目处理 |
|---|---|---|---|
| [vue-pure-admin](https://github.com/pure-admin/vue-pure-admin) | Vue 3、Vite、Element Plus、TypeScript、Pinia、Tailwind；MIT | 紧凑侧栏、权限路由、桌面/移动布局 | 保留固定技术栈，自行设计业务导航与组件 |
| [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin) | Vue 3、Vite、TypeScript；MIT | 工作区上下文、主题一致性、路由分包 | 采用粘性顶栏和按业务域分组导航 |
| [V3 Admin Vite](https://github.com/un-pany/v3-admin-vite) | Vue 3、Vite、TypeScript、Element Plus；MIT | 清晰的开发结构、动态权限与移动适配 | 采用页面懒加载、RBAC 路由和移动遮罩 |
| [SoybeanAdmin](https://github.com/soybeanjs/soybean-admin) | Vue 3、Vite、TypeScript；MIT | 清新配色、严格代码规范、状态反馈 | 只参考视觉节奏，不引入 Naive UI/UnoCSS |

## 截图问题与整改

- 旧工作台把 FastAPI/MySQL/JWT 状态作为主内容，业务价值弱；新版首屏改为内容、审核、排期、失败、趋势和实验。
- 旧界面空白过大、卡片层级重复；新版使用紧凑 12 列信息区和低阴影面板。
- 登录页品牌文案尺度过大且折行生硬；降低字号并保留清晰的演示账号入口。
- 原导航把关键功能标成“即将开放”；新版全部接入真实路由并按运营、分发、研究三个域组织。
- 页面大量英文标签已收敛为小型 eyebrow，关键业务文本以中文为主。

许可证：上述项目均仅用于观察与分析；本项目未复制其代码，因此没有引入第三方源文件或版权声明迁移问题。
