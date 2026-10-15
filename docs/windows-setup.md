# Windows 接入与排障

本项目面向已经使用 Agent 工具的用户。先按 [README](../README.md) 安装、配置，再按本文核对飞书权限。已通过项目启动器验证实际 MCP 协议，并通过官方 MCP SDK 使用同一启动器完成交互登录、专用私有空间中的三类资料卡写入／迁入／回读及原文档局部修订。图片块与素材标识已验证；另已通过 Codex CLI 0.160.0 的官方备用沙箱完成单篇原件修订端到端。默认 elevated 仍有初始化故障；Codex 新增导入／迁入分支、OAuth 自动续期、真实故障恢复及页面视觉检查尚未完成。

## 1. 飞书应用与调用身份

1. 在[飞书开放平台](https://open.feishu.cn/app)创建应用，将真实 `APP_ID`、`APP_SECRET` 仅配置在项目根目录 `config.conf`。
2. 在「权限管理」中开通下表的**用户身份权限**，按平台要求发布、审批。
3. 在安全设置中配置 OAuth 回调地址。锁定版本默认使用 `http://localhost:3000/callback`，以官方登录实际提示为准。
4. 使用拥有目标总索引及知识库编辑权限的账号授权。迁入云文档还需满足原文档管理权限；应用开通权限不能代替资源授权。

启动器统一申请：

```text
docx:document drive:drive wiki:wiki offline_access
```

这是覆盖现有工作流的权限组合，不是最细粒度或飞书全部权限。不要为排查一个错误随意增加通讯录、消息或其他无关权限。

| 用途 | 启动器中的工具标识 | 用户身份权限 |
| --- | --- | --- |
| 搜索、Markdown 导入和导入结果 | `docx.builtin.search`、`docx.builtin.import`、`drive.v1.importTask.get` | `drive:drive` |
| 文档信息、正文和块读取 | `docx.v1.document.get`、`docx.v1.document.rawContent`、`docx.v1.documentBlock.get`、`docx.v1.documentBlock.list` | `docx:document` |
| 局部修改、追加块、删除指定块 | `docx.v1.documentBlock.patch`、`docx.v1.documentBlockChildren.create`、`docx.v1.documentBlockChildren.batchDelete` | `docx:document` |
| 搜索、列举、读取和创建知识空间 | `wiki.v1.node.search`、`wiki.v2.space.list`、`wiki.v2.space.get`、`wiki.v2.space.create` | `wiki:wiki`；节点搜索仍受资源访问限制 |
| 解析节点、列举和创建子节点 | `wiki.v2.space.getNode`、`wiki.v2.spaceNode.list`、`wiki.v2.spaceNode.create` | `wiki:wiki` |
| 迁入、移动、改名和异步任务结果 | `wiki.v2.spaceNode.moveDocsToWiki`、`wiki.v2.spaceNode.move`、`wiki.v2.spaceNode.updateTitle`、`wiki.v2.task.get` | `wiki:wiki` |
| 删除已明确授权的重复云文档 | `drive.v1.file.delete` | `drive:drive` |
| 令牌续用 | OAuth 流程 | `offline_access` |

工具清单和 scope 只由 [`scripts/start-feishu-mcp.ps1`](../scripts/start-feishu-mcp.ps1)维护。表中列出工具不代表授权 Agent 自动删除文档。所选版本的 22 个工具已离线核对 schema 与用户身份兼容性，未据此宣称全部真实 API 可用。

## 2. 校验与授权

在项目根目录 PowerShell 中：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-feishu-mcp.ps1 -Check
```

`-Check` 校验配置、Node 版本、已安装包版本和入口文件，不导入官方 OAuth 模块，不访问令牌库，不验证 API 权限。

首次使用或 scope 变更后，关闭该项目的 MCP 连接，再运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-feishu-mcp.ps1 -Login
```

浏览器授权完成后重新连接 MCP。`-Login` 只执行官方交互登录，不启动 stdio 服务；正常 Agent 连接不要附加 `-Login` 或 `-Check`。

官方 `0.5.1` 可能复用旧令牌，因此仅重启不一定获得新增 scope。不要用复制令牌、另换账号、临时把令牌塞进参数或扩大权限来绕过。项目启动器会移除继承的 `USER_ACCESS_TOKEN`，只从文件读取应用配置。

## 3. 客户端接入

使用 [.codex/config.toml.example](../.codex/config.toml.example)创建本机配置，将两处项目绝对路径改正确。该文件没有凭据，不需要在 `env` 里再填 App Secret。

- 配置属于当前项目，不自动安装到用户级 Codex 配置。
- 部分客户端只在信任项目后加载项目配置；按客户端界面确认信任、重载和工具发现。
- 技能位于 `.agents/skills/feishu-wechat-knowledge`。提示词中可使用 `$feishu-wechat-knowledge`；若客户端不自动发现，明确让 Agent 读取对应 `SKILL.md`。
- 其他 Agent 的配置格式需单独适配，不直接复制 Codex TOML 当作通用 MCP JSON。
- stdio 服务由客户端管理。不要把 `-Login` 的人类提示输出接到 MCP 协议通道。

可在本机单独检查实际 MCP 协议：

```powershell
python -B .\scripts\check-mcp.py
```

它通过同一项目启动器只执行握手及分页工具发现，不执行任何飞书 API 工具，不进行浏览器登录；官方进程可能初始化已批准的认证存储。输出包含工具数量、协议错误数、stderr 字节数及关闭 stdin 后是否退出，不输出原始协议内容和诊断数据。成功不能证明 scope、目标资源权限或 OAuth 续期有效。

实际检查发现并修复了 `0.5.1` 文件 watcher 阻止 stdio 退出的问题：版本限定的适配层在 EOF 时关闭已加载的官方 watcher，不强制退出正在执行的请求。如果检查报告强制清理或协议错误，不把它标为通过。

### Codex CLI 验收与沙箱限制

本机使用 `codex-cli 0.160.0`。先完成原生 MCP 读写隔离检查，随后在官方备用沙箱中完成单篇工程文章的原件修订端到端：Codex 自行读取实际 Skill／状态、运行公众号读取脚本并核读全文与关键图，修订同一资料卡 1 段、测试索引 1 段，回读 Wiki／正文／索引并更新本地原记录。其余卡片块、文档与节点标识、3 个子页面及索引链接保持不变；未新建或删除文档。新增导入／迁入分支未通过 Codex 重跑；本次按查重规则复用原件。没有改用自建协议客户端或直接请求飞书 HTTP API。

- 初次调用已自动识别项目 Skill，但本地命令报 `sandbox_setup_error`。`codex doctor --json` 显示 elevated provisioning 失败；默认 daemon 模式的最小命令也报 `helper_unknown_error: setup refresh had errors`。后续只读诊断将范围缩小到 ACL 刷新：技能目录所属者为沙箱账号，deny ACE 更新失败，另有一处用户目录 read ACE 更新失败。未手工重置所属者或 ACL，未重装、修改系统环境或用户级配置。默认 elevated 仍未修复，不把备用模式成功称为已修复它。
- 此前隔离 MCP 验收曾由指令提供公开规则，只能证明原生通道；本轮备用沙箱下的原件修订则由 Codex 自行读取实际 Skill／状态及运行本地脚本，二者分别记录。
- 非交互调用的 `-a never` 在本机拒绝了需要审批的 MCP 请求，不能据此认定飞书权限不足。改用此版本支持的 `--approve-for-me` 后，经正常自动审阅完成上述操作；没有使用 `--dangerously-bypass-approvals-and-sandbox`。自动审阅不保证批准任意请求，任务仍须明确限定专用测试资源与允许修改的范围。
- 本次使用 `--no-daemon` 和 `--ephemeral`，不持久保存该次会话文件，也不将原始协议或文章正文重定向为本地报告。客户端的其他认证、诊断及系统状态仍遵循客户端机制，不宣称全系统零写入。

#### 会话级官方备用沙箱

按[官方 Windows 沙箱指引](https://developers.openai.com/codex/windows)，elevated setup 无法完成且策略允许时，可以使用 `unelevated`。它使用受限令牌和 ACL 文件系统边界，**网络隔离较弱且不支持拒绝读取路径**，不是关闭沙箱，也不是与 elevated 等价的安全保证。先遵循组织管理策略，不能用它绕过强制要求。

已在本机 0.160.0／PowerShell 验证的最小探针（项目目录运行）：

```powershell
codex -c windows.sandbox=unelevated sandbox --permission-profile :workspace -- powershell.exe -NoProfile -Command "Write-Output CODEX_SANDBOX_PROBE"
```

预期输出 `CODEX_SANDBOX_PROBE`，退出码为 0。`-c` 只对本次调用生效，不改保存的配置。实际原件修订的 `codex exec` 同样使用 `-c windows.sandbox=unelevated` 与 `--sandbox workspace-write`，并通过 `-c sandbox_workspace_write.network_access=true` 仅为该次会话允许读取原文／原图的网络访问；继续采用 `--approve-for-me` 正常自动审阅及 `--ephemeral`。未使用无沙箱模式。不要把这些选项默认写入所有用户或其他项目的配置。

可在项目目录检查本机 Codex：

```powershell
codex --version
codex doctor --json
```

诊断发现问题时可能非零退出，默认模式的报告仍可能显示 elevated 故障。报告只在本机核对；提交 issue 前仅提取错误类别，不公开完整报告、个人路径、连接配置或认证信息，不读取或分享 `.sandbox-secrets`。默认模式的修复仍需按官方 setup／权限指引单独处理，不能复制令牌或换账户绕过。PowerShell 中文状态写入的编码约束见 Skill「存储约定」；只设置 Python 编码不保证发送端管道保留中文。

## 4. 归档入口

首次使用将自己的总索引地址交给 Agent；空的 `article-status.example.json` 不是已经初始化成功的知识库。Agent 必须先读取目标、解析实际文档标识并核对父子关系，才能保存入口并创建文章子页面。

`/wiki/` 后面是节点标识，不是 Docx 标识。具体工作流和超时重试规则只维护在 Skill 中，不在接入文档另设一套。

测试时使用专用总索引页面。用户明确授权新建隔离测试入口时，按 Skill 核验并保存在同一状态文件的 `test_index`，不替换业务 `index`；未获此授权时仍需先取得指定入口。不要以验证模板为理由重写或清理个人业务知识库；测试删除仍需明确授权。

## 5. 常见问题

| 现象 | 检查方向 |
| --- | --- |
| 配置缺失、重复、为空或占位值 | 编辑根目录 `config.conf`；不要把原始配置行贴到 issue |
| 本地依赖缺失或版本不符 | 根目录执行 `npm ci`；启动器不会退回 npx 或全局安装 |
| `keytar` 安装失败 | 查看原生模块／预编译产物下载错误及 Node 支持情况；不为排障导出认证存储 |
| 回调地址不匹配 | 对照实际提示核对应用安全设置、协议、主机和端口 |
| 工具能发现但 API 拒绝 | 分别核对应用权限、用户实际 OAuth 授权、调用身份及目标资源权限 |
| Codex 本地命令报 `sandbox_setup_error` | 核对 doctor 与沙箱日志；本机 elevated 的 ACL 刷新仍失败，官方会话级 unelevated 备用模式已通过，不能声称默认模式已修复 |
| Codex 非交互 MCP 审批被拒绝 | 区分客户端审批策略与飞书 API 权限；`-a never` 不会代替授权，按客户端正常审批流程处理 |
| 新增权限后仍缺 scope | 关闭 MCP 后显式 `-Login` 重新授权，再连接；不是只重启 |
| 入口不可访问或文章列表为空 | 保留已知地址，核对权限与分页；不当作不存在后新建 |
| 公众号验证页或正文缺失 | 停在读取阶段，如实报告；不从标题生成完整汇报 |
| 图片链接可用但文档没有图 | 分开检查图片块、素材标识和视觉渲染，不宣称已经嵌入 |
| 写入超时 | 先查询结果；未知不是失败，不直接重新导入 |
| 日志适配报版本错误 | 恢复固定依赖并检查适配测试，不手改 node_modules 跳过版本保护 |

诊断日志位于 `.runtime/lark-logs`，不是文章缓存，但也不应直接公开。关闭 MCP 后保留必要认证状态，不自动删除或迁移用户级认证数据。

## 官方参考

- [Codex 官方 Windows 沙箱与备用模式](https://developers.openai.com/codex/windows)
- [Codex 官方审批与网络边界](https://developers.openai.com/codex/agent-approvals-security)
- [所选版本 README](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/README_ZH.md)
- [所选版本 CLI](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/cli.ts)
- [官方登录实现](https://github.com/larksuite/lark-openapi-mcp/blob/v0.5.1/src/cli/login-handler.ts)
- [飞书开放平台 API](https://open.feishu.cn/document/home/index)

工具元数据、开放平台权限及实际 API 行为共同决定支持范围，不能用任意一个替代其余条件。
