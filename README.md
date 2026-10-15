# feishu-worker

**面向已有 Codex 等 Agent 工具的用户，将微信公众号技术文章整理为易懂、可汇报、可迁移使用的知识资料卡，并通过飞书 MCP 归档到个人知识库。**

这是一个 **Agent Skill + Windows 项目模板**，不是独立的模型服务、新的飞书 MCP Server 或无人值守采集平台。模型与会话由用户现有 Agent 提供，飞书访问使用官方 `@larksuiteoapi/lark-mcp`。

## 能做什么

- 核读公众号原文，提取标题、来源、正文和图片地址，识别验证页与不完整内容。
- 围绕核心问题组织背景、方法、证据、适用边界和实践建议，形成汇报式资料卡，而不是固定栏目填空。
- 按需核对论文、代码等一手来源，区分实际核验、公众号转述及整理者建议。
- 归档到用户指定且已核验的飞书总索引下，维护文章子页面与索引链接。
- 修订原文档，处理失败与未知阶段，回读正文和目录关系，避免自动生成重复版本。

工作流定义只有一处：[feishu-wechat-knowledge/SKILL.md](.agents/skills/feishu-wechat-knowledge/SKILL.md)。项目开发及云文档操作约束见 [AGENTS.md](AGENTS.md)。

## 当前状态与支持边界

| 项目 | 状态 |
| --- | --- |
| 操作系统 | Windows；本地测试环境为 Windows PowerShell、Node.js 22、Python 3.12 |
| Agent | Codex CLI 0.160.0 已在官方 `unelevated + workspace-write` 备用沙箱中通过原件修订、新文章导入／迁入及新会话同链接去重复用；默认 elevated 的 ACL 刷新故障仍未修复 |
| MCP | 固定 `lark-mcp@0.5.1`，提交锁文件，启动时不使用 npx 下载 |
| 本地测试 | 38 项通过，覆盖配置、公众号解析、日志适配、FTP／代理、模拟 stdio 及导入文件名 schema 边界；不调用真实飞书 API |
| 干净目录安装 | 最新公共提交快照导出后，`npm ci` 和 38 项测试通过；未复制真实配置或状态，缺配置时安全失败；临时安装与缓存已清理 |
| 实际 MCP 协议 | 通过项目启动器完成握手、22 个工具发现及 stdin 关闭后退出；另通过同一启动器与官方 MCP SDK 完成真实 API 调用 |
| 真实飞书验收 | 官方 SDK 三类样例及 Codex 新文章首次收录／迁入／同链接去重通过；原样例 7 图、新卡 4 图结构已核验；用户确认新卡 4 图与排版正常，旧三卡未逐页视觉回归；续期及真实故障恢复未验证 |
| 安全审计 | 最新独立锁文件审计为 0；已修复已知告警，不等于完整安全证明，详见 [安全说明](docs/security.md) |
| 发布阶段 | Windows + Codex 预览版的本地门槛通过；可公开源代码，创建 GitHub Release 前仍应确认首次远端 Windows CI 通过 |

三轮进度、未完成项和发布检查见 [TODO.md](TODO.md)。建议首发标记为预览版，而非稳定版或无人值守生产服务。其他 Agent 客户端及非 Windows 平台尚未验证。

## 工作方式

```text
公众号链接
  → Agent 核读原文与必要的一手来源
  → 汇报式知识资料卡
  → 官方飞书 MCP 写入／修订
  → 总索引父页面 → 文章子页面
  → 回读正文、来源、目录与索引
  → 本地更新 article-status.json
```

资料卡先回答一个核心问题，再按文章内容展开。论文、工程案例、产品评测可以有不同章节；不强制三个知识点、七个模块或固定字数。重要数字就近说明条件与来源；读不到的资料不伪装成已经核验。

## 快速开始（Windows）

### 1. 准备环境并安装依赖

需要 Node.js **20 或更高版本**、npm、Python **3.10 或更高版本**和支持 Skill、MCP stdio 的 Agent。Python 脚本只使用标准库。

下载或克隆项目后，在项目根目录的 PowerShell 中运行：

```powershell
node --version
python --version
npm ci
```

项目 `.npmrc` 使用公共 npm registry，并将 npm 缓存指向 `.runtime/npm-cache`；不修改全局 npm 配置。可显式调整项目 registry 以适应网络条件，但应重新核对锁文件和审计结果。上游 `keytar` 依赖原生模块，安装可能需要下载预编译产物；不要通过管理员权限或全局安装来掩盖具体错误。

### 2. 配置飞书应用

在[飞书开放平台](https://open.feishu.cn/app)创建自己的应用。仅当本地文件不存在时复制模板：

```powershell
if (-not (Test-Path -LiteralPath .\config.conf)) {
    Copy-Item .\config.conf.example .\config.conf
}
```

在本机编辑 `config.conf`，将占位值替换为自己的应用凭据：

```ini
APP_ID=cli_your_app_id
APP_SECRET=your_app_secret
```

格式为 `KEY=VALUE`，按首个 `=` 分隔；支持空行、整行 `#` 注释及成对外层引号。必填键不可重复、缺失、为空或仍为占位值。不执行文件内容，不把真实值放入命令行或客户端 JSON。

检查本地配置和安装，不启动 OAuth、不调用飞书 API：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-feishu-mcp.ps1 -Check
```

### 3. 开通权限并授权

按 [Windows 接入说明](docs/windows-setup.md)开通用户身份权限、配置 OAuth 回调地址，并确认自己的账号可以编辑目标知识库。

需要首次授权或新增 scope 后重新授权时，关闭项目 MCP 连接，再运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-feishu-mcp.ps1 -Login
```

此命令有交互，会启动官方登录流程。它不是 `-Check`；本轮已通过该命令完成官方交互登录，并在专用测试空间调用 API，未手工读取令牌。交互登录成功不等于已验证自动续期。

**存储边界：** 应用配置从根目录 `config.conf` 读取；官方 OAuth 机制使用用户级加密认证文件及 Windows 系统密钥存储，这是已明确允许的例外，不要求把它迁入项目。官方诊断日志通过版本限定的适配层重定向到 `.runtime/lark-logs`，不改认证位置、不复制旧令牌。详情见 [安全说明](docs/security.md)。

### 4. 配置 Agent 的项目级 MCP

Codex 示例在 [.codex/config.toml.example](.codex/config.toml.example)。没有现有配置时才复制：

```powershell
if (-not (Test-Path -LiteralPath .\.codex\config.toml)) {
    Copy-Item .\.codex\config.toml.example .\.codex\config.toml
}
```

将其中两处 `C:/path/to/feishu-worker` 改成本项目的绝对路径；Windows 路径使用 `/`，有空格也保留在字符串内。已有配置时手工合并，不能覆盖原来的 MCP 设置。

在 Agent 中信任该项目并重新加载项目配置，确认发现名为 `feishu` 的连接与文档工具。工具能发现不代表已经有 API、OAuth 或目标文档权限。其他 Agent 应在其项目级配置中调用同一 PowerShell 启动器；不自动修改用户级配置。

Codex CLI 的原生 MCP 读写与本地命令执行需要分别验收。本机 `0.160.0` 已在官方备用沙箱中完成自动读取 Skill、重读原文与关键图、修订原件、核对 Wiki／索引及更新本地状态；没有关闭沙箱或持久修改客户端配置。另已用新来源完成 Markdown 导入、异步迁入、最终父节点与索引回读，并在独立新会话重提同链接确认复用原件；没有再次导入或创建重复文档。备用模式的隔离差异、非交互审批与排障见 [Windows 接入说明](docs/windows-setup.md#codex-cli-验收与沙箱限制)。

### 5. 指定归档入口并提交文章

已有 `article-status.json` 时直接保留。首次使用可以从空状态示例初始化：

```powershell
if (-not (Test-Path -LiteralPath .\article-status.json)) {
    Copy-Item .\article-status.example.json .\article-status.json
}
```

在 Agent 中给出你有编辑权限的飞书总索引页面地址和公众号链接，例如：

```text
使用 $feishu-wechat-knowledge 整理以下公众号技术文章，生成适合技术分享的汇报式资料卡。
我的总索引地址是：<填写自己的飞书 Wiki 页面地址>
文章链接是：<填写完整公众号原链接>
请先核验总索引，归档为文章子页面，并回读正文、来源和目录关系。
```

首次使用缺少入口时会先询问，不默认采用他人的知识库，也不自动创建新空间。后续复用已核验的 `index.document_url`。用户明确授权新建隔离测试入口时，按 Skill 核验并记录在同一状态文件的 `test_index` 中，不替换业务入口；只有明确的测试任务才使用它。已有文章先读再修订；删除、大量删块和覆盖仍需明确授权。

## 本地测试

```powershell
npm test
```

测试使用项目内临时目录、合成配置、自编页面和仅绑定 `127.0.0.1` 的 FTP／HTTP 服务，不读取真实凭据、不请求真实公众号或飞书，不保存用户文章内容。包含经实际 MCP 依赖链解析的 FTP 安全回归与代理兼容检查。Windows 之外会跳过 PowerShell 测试。

新增的 [Windows CI](.github/workflows/tests.yml)执行依赖安装、本地测试与锁文件审计，不需要飞书凭据；工作流尚未在 GitHub 远端执行。

需要检查实际官方 MCP 握手、工具发现和关闭行为时，可单独运行：

```powershell
python -B .\scripts\check-mcp.py
```

此命令通过项目启动器读取现有配置，官方进程可能按方案 A 初始化认证存储；只发送 `initialize`、`notifications/initialized` 和分页 `tools/list`，不执行文档工具，不登录、不验证 scope 或文档权限。仅输出检查结果，不输出令牌、工具正文或原始诊断信息。它不属于 `npm test`，不能在无凭据的 CI 中替代本地隔离测试。

安全审计命令（发现告警时会非零退出）：

```powershell
npm audit --package-lock-only --omit=dev
```

## 数据、隐私与限制

- 文章正文、原图、分类与总索引只持久保存到飞书；本地 `article-status.json` 只保存来源、处理阶段、结果和地址。
- `config.conf`、个人状态、个人 `.codex/config.toml`、依赖及运行目录不应提交。忽略规则不会自动移除已暂存或已跟踪的文件，首次发布前必须检查索引。
- 原文及飞书内容会进入所用 Agent／模型的处理上下文；模型服务商和客户端自身的会话保留机制不由本项目控制。不要把敏感文章交给未经批准的模型服务。
- 不绕过微信验证、登录或访问控制。页面解析成功只表示提取到了结构，不保证内容完整或结论正确。
- 图片地址存在、图片块存在、视觉显示正常是不同检查；不保证任意图片上传下载或所有原图都能嵌入。
- 项目自有代码、技能规则与说明文档采用 [MIT License](LICENSE)。第三方依赖遵循各自许可证，公众号原文和图片归各自权利人所有，不因项目开源而获得转载授权。项目不附带个人文章库。

## 项目文件

```text
.agents/skills/feishu-wechat-knowledge/  # 唯一工作流规则、技能入口和内存读取脚本
.codex/config.toml.example             # 客户端配置示例
scripts/start-feishu-mcp.ps1           # 配置校验、固定依赖及用户身份启动
scripts/lark-runtime.cjs               # 0.5.1 日志与 stdin EOF 退出适配，不改 OAuth 存储
scripts/check-mcp.py                   # 实际协议检查，不调用飞书 API 工具
config.conf.example                   # 无真实凭据的模板
article-status.example.json           # 无个人入口的空状态示例
tests/                                # 隔离本地测试
docs/                                 # 接入和安全说明
TODO.md                               # 分轮进度及验收阻塞
```
