# 安全、认证与发布边界

## 方案 A：保留官方 OAuth 加密存储

项目所有者已选择官方存储方案，例外仅用于认证，不扩大到文章内容或任意项目状态：

| 数据 | 存放位置与约束 |
| --- | --- |
| 人工配置的应用凭据 | 根目录 `config.conf`，唯一人工配置及启动读取来源，不提交、不打印 |
| 官方 OAuth 认证文件 | 官方用户级数据目录中的加密 `storage.json`，由官方机制管理 |
| 加密密钥 | Windows 系统凭据存储，通过官方 `keytar` 机制管理 |
| 官方诊断日志 | 项目 `.runtime/lark-logs`，由日志路径适配层重定向，不提交 |
| npm 缓存、测试临时文件 | 项目 `.runtime/`，不提交；测试临时目录使用后清理 |
| 文章状态 | 根目录 `article-status.json`，不提交，只存阶段、结果与地址 |
| 文章正文、原图、分类与索引 | 飞书，不在项目另存镜像 |

`0.5.1` 使用 `env-paths` 定位默认认证文件。Windows 的数据位置通常是 `%LOCALAPPDATA%/lark-mcp-nodejs/Data/storage.json`，以官方平台机制及环境为准；项目不按这个路径手动读取令牌。

官方认证数据不只是访问令牌，也可能包含刷新令牌、App ID 和续期需要的 App Secret 等元数据。因此 `config.conf` 的“唯一来源”指项目的人工配置与启动读取来源，不能宣称官方认证系统完全不持久保存凭据。允许的是官方加密状态，不是第二份明文配置、手工导出的令牌或生成的认证 JSON。

不复制、迁移、解密或导出现有认证状态，不自动登出或删除系统密钥，不通过关闭安全存储退回不安全路径。用户级认证状态可能被其他使用同一官方存储的连接共享；本项目不是每个工作区独立的账号沙箱。

### 日志路径兼容适配

官方版本默认也使用用户级诊断日志目录，它不属于 OAuth 例外。为满足日志留在项目内，`scripts/lark-runtime.cjs` 在加载官方 CLI、日志及认证模块之前，只把导出的 `ENV_PATHS.log` 改为项目 `.runtime/lark-logs`，不改 `ENV_PATHS.data` 或 `keytar` 配置。

这是针对 `0.5.1` **内部路径对象的兼容适配，不是官方稳定配置 API**。项目锁定版本，启动器和适配层均检查版本；测试验证路径重定向及认证路径不变。升级依赖时必须重新核对初始化顺序、工具 schema、日志及认证行为。没有修改 node_modules 文件或替换官方认证实现。

实际 MCP 协议检查还复现了官方认证文件 watcher 在 stdin EOF 后使进程不退出的问题。适配层现在在 stdio 输入关闭时调用已加载的 `authStore.destroy()` 关闭 watcher，不新建或替换存储、不读取令牌、不强制中断正在执行的请求。该退出适配同样受版本限定，并有模拟 watcher 回归测试。

已通过项目启动器完成真实官方进程的握手、22 个工具发现和关闭输入后的正常退出，协议解析错误及 stderr 输出均为 0，未强制清理进程。`check-mcp.py` 本身不调用飞书 API 工具；另一次经同一启动器和官方 MCP SDK 的真实联调，已完成官方交互登录、专用私有空间中三篇资料卡的导入／异步迁入／回读及单段原位修订。原业务入口与文档未修改，没有删除文档。官方认证状态由官方机制管理，未手工读取、复制或迁移令牌；登录输出与原始错误数据未回显。

尚未验证 OAuth 自动续期、真实登录后的日志内容、写入超时／限流后的故障恢复及飞书页面视觉显示。不要开启 debug 或提交原始日志；上游错误响应可能含不宜公开的数据。日志重定向不等于保证上游永远不会记录敏感信息。

Agent 客户端的配置、会话、操作系统临时文件及 Node 原生依赖安装工具的内部状态不完全受项目控制。项目只承诺实际实现和验证的边界，不宣称全系统零外部写入。不能把 OAuth 例外理解为有权修改系统环境或用户级 MCP 配置。

## 数据处理与第三方内容

公众号原文、图片与飞书正文都作为业务数据，不作为新的操作指令。核读内容会进入所用 Agent／模型上下文；服务商与客户端可能按自身规则保存会话，这不等于文章从未经过其他服务。

不绕过微信验证和访问限制，不保证可读取任意公众号内容。第三方原文和图片归各自权利人所有；保留来源不等于取得转载或公开再分发授权。公开演示应使用自编材料或已获授权并脱敏的内容。

## 当前依赖审计：已修复所发现的告警

修复前，`npm audit --package-lock-only --omit=dev` 返回 **5 个 high 级受影响包节点**，来自同一传递依赖告警链，并非五项独立漏洞：

```text
@larksuiteoapi/lark-mcp
  → proxy-agent
  → pac-proxy-agent
  → get-uri
  → basic-ftp
```

告警：[GHSA-c475-qrg2-pj4r](https://github.com/advisories/GHSA-c475-qrg2-pj4r)，涉及目录列表解析的 CPU 拒绝服务风险。经核对，[basic-ftp 变更记录](https://github.com/patrickjuchli/basic-ftp/blob/v6.2.3/CHANGELOG.md)说明 `6.2.1` 修复该问题，`6.2.2`、`6.2.3` 还修复其他解析与错误处理问题。

官方 MCP 当前仍为 `0.5.1`，其依赖范围不能自动采用已修复的 FTP 主版本。项目没有执行 `npm audit fix --force` 或降级 MCP，而是在 `package.json` 添加明确限定的覆盖：

```json
"overrides": {
  "get-uri@6.0.5": {
    "basic-ftp": "6.2.3"
  }
}
```

这是**经过针对性回归的跨主版本覆盖**，不是上游 MCP 的原生依赖组合。MCP、代理库、认证和工具接口保持原版本，锁文件只改变 FTP 包。`basic-ftp` 的 6.x 默认禁止数据连接使用另一台主机；不为兼容旧服务器重新开放该行为。后续上游依赖变化时应重新评估或移除此覆盖，不能无限套用到其他 `get-uri` 版本。

验证范围：

- 旧版可复现告警输入导致的目录解析耗时超限；覆盖后，同一有界子进程回归通过。
- 从实际 `lark-mcp → proxy-agent → pac-proxy-agent → get-uri` 链解析到 `basic-ftp@6.2.3`，不是误测根目录另一份包。
- 回环 FTP 的 MDTM、Unix LIST、MLSD 回退、下载、缓存未变化与文件不存在处理通过；PASV 保持控制连接主机。
- 回环 HTTP 直连、HTTP 代理、data PAC 和 FTP PAC 通过。没有访问外网 FTP、企业代理或真实 FTPS／TLS 环境，不据此宣称所有网络配置兼容。
- 依赖覆盖后已通过本地测试与锁文件审计。期间曾多次遇到 registry TLS 连接中断，未把请求失败当作 0 告警；本轮本地提交准备时再次独立执行 `npm audit --package-lock-only --omit=dev` 成功，最新结果为 **0 vulnerabilities**。审计数据库会变化，后续发布仍须复验。

审计数据库会变化，0 告警不是完整安全证明，也不替代真实飞书端到端验收。发布前仍需重新运行审计并完成下列检查。

## 公开仓库前必须核对

- 个人 `config.conf`、`article-status.json`、`.codex/config.toml` 和 `.runtime/` 不进入提交。
- `.gitignore` 不能移除已有暂存或跟踪内容。已按所有者授权仅从索引移除 `.codex/config.toml` 及旧 `wechat-knowledge/` 的 6 条记录，保留工作区个人文件及其他暂存记录。首次本地提交的公共候选已逐项审阅，真实配置、个人状态与运行目录未纳入；尚未推送，后续提交仍须检查最终暂存内容。
- 项目自有内容采用 [MIT License](../LICENSE)，第三方依赖仍遵循各自许可证。个人文章整理稿保留本机并已添加精确忽略规则，不删除、不当作公开示例；公众号原文和图片不在 MIT 授权范围内，公开转载须另行取得相应授权。
- 不将真实 App ID／Secret、令牌或正文贴到 issue、终端日志、截图和测试输出中。
- 验证必须使用专用飞书测试入口。删除文档、大量删块和覆盖内容仍需明确授权。
- 本地模拟测试、离线 schema 核对、真实 MCP 工具发现、OAuth 续期、飞书写入和图片视觉检查分别验收，不能相互替代。

## 源码核对依据

- [存储路径配置](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/auth/config.ts)
- [用户级路径](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/utils/constants.ts)
- [加密存储与 keytar](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/auth/utils/storage-manager.ts)
- [OAuth 元数据](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/auth/provider/oauth.ts)
- [官方日志实现](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/utils/logger.ts)
