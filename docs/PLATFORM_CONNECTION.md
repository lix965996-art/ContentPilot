# 真实平台连接指南

ContentPilot 不提供模拟连接或模拟发布成功。微博与微信公众号只有在官方接口实际返回成功后才显示“已连接”；小红书在没有获批的官方内容发布接口时只显示“仅人工交付”。

## 微博：开放平台应用 + OAuth2

准备工作：

1. 登录[微博开放平台应用管理](https://open.weibo.com/apps)，创建网页应用并完成平台要求的审核。
2. 在应用信息中取得 `App Key` 和 `App Secret`。
3. 在应用的 OAuth2 回调设置中加入 ContentPilot 显示的回调地址，必须逐字一致：
   - 本地开发：`http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback`
   - Docker 本地：可使用 `http://127.0.0.1:8080/api/platform-accounts/WEIBO/oauth/callback`
   - 正式环境：`https://你的域名/api/platform-accounts/WEIBO/oauth/callback`
4. 在 ContentPilot“平台账号 → 微博 → 编辑配置”中填写 App Key、App Secret 和同一个回调地址。
5. 点击“保存并前往微博官方授权”，使用真正要发布内容的微博账号登录并同意授权。
6. 返回 ContentPilot 后点击“验证真实连接”。系统会调用微博官方 `account/get_uid` 接口，取得 UID 后才显示“已连接”。

相关官方接口：[OAuth2 authorize](https://open.weibo.com/wiki/Oauth2/authorize)、[OAuth2 access_token](https://open.weibo.com/wiki/Oauth2/access_token)。发布能力还取决于应用审核状态和获批接口权限。

### 错误码 21324

`21324 client_id或client_secret参数无效` 是微博官方返回的错误，不是 ContentPilot 本地错误。常见原因：

- 把微博登录账号、模型 API Key 或其他平台 Key 填进了 App Key；
- App Key 与 App Secret 不属于同一个微博开放平台应用；
- 复制时带入空格，或者密钥已被重置；
- 应用类型、审核状态或 OAuth 回调配置不满足当前授权要求。

应回到微博开放平台应用后台重新复制同一应用的 App Key/App Secret。截图中出现该错误时，ContentPilot 必须保持“连接无效/待授权”，不能显示连接成功。

## 微信公众号：AppID/AppSecret + IP 白名单

1. 登录[微信公众平台](https://mp.weixin.qq.com/)，进入开发接口相关设置。
2. 获取公众号真实 `AppID` 和 `AppSecret`。不要填写微信号、原始 ID、小程序 AppID 或模型服务 Key。
3. 将运行 ContentPilot 的服务器出口公网 IP 加入公众号 IP 白名单。
4. 在 ContentPilot 中选择：
   - “真实创建公众号草稿”：调用草稿接口，结果只进入草稿箱；
   - “真实提交发布”：先创建草稿，再调用发布接口，需要公众号具备相应权限，并勾选允许提交发布。
5. 保存后点击“验证真实连接”。系统会向微信官方接口获取 Access Token；只有取得真实 Token 才显示“已连接”。

官方文档：[获取 Access Token](https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html)、[新增草稿](https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html)、[发布能力](https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html)。

常见错误：

- `40013`：AppID 无效；
- `40125`：AppSecret 无效；
- `40164`：服务器出口 IP 不在白名单；
- `48001/48002`：公众号没有相应接口权限；
- `40001/40014/42001`：Token 无效或过期，需要重新验证。

## 小红书：人工交付边界

当前项目没有获批、可供普通账号使用的小红书官方笔记发布接口。小红书开放平台公开能力主要面向获准的业务场景，不能把账号密码、Cookie 或浏览器自动化包装成“官方连接”。

因此 ContentPilot 只做以下真实动作：

1. 生成小红书版本文案、标签、封面和图片顺序；
2. 到点生成 ZIP 交付包；
3. 打开[小红书创作中心](https://creator.xiaohongshu.com/)人工发布；
4. 发布完成后回填真实公开链接，任务才进入“人工发布完成”。

如果以后获得小红书书面批准的合作方接口，应新增独立官方适配器和接口验签测试，不能复用 Cookie、Selenium 或 Playwright 登录发布。

## 如何判断是不是真连接

- “保存配置”只代表密钥已加密保存，不代表连接成功；
- “验证真实连接”必须调用平台官方域名并取得真实账号标识或 Access Token；
- 微博/公众号状态不是 `CONNECTED` 时，后端会拒绝创建真实发布任务；
- 小红书始终显示 `MANUAL_ONLY`，不会显示“已连接”；
- 测试代码可以拦截外部 HTTP 边界，但产品运行代码没有模拟成功发布器。
