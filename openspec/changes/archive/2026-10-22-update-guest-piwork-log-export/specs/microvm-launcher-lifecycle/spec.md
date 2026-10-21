# MicroVM Launcher Lifecycle Spec Delta

## MODIFIED Requirements

### Requirement: 提供统一且无副作用的命令行入口

两平台 SHALL 支持无参数、`--data-dir DIR`、`--port PORT`、`--core-port PORT`、`--cpus N`、`--memory MiB`、`--no-open` 和 `--help`。默认 SHALL 使用 2 vCPU、4096 MiB 内存、UI 17891 和 Core 17871。两个 Host 端口 SHALL 接受 1–65535 的整数、不得相同，且均 MUST NOT 为内部 Agent RPC 保留端口 7172；不额外排除旧 Service 端口池。无效参数 SHALL 在访问虚拟化、准备数据或启动 VM 前失败，`--help` SHALL 无需虚拟化能力且不写用户数据。

#### Scenario: 查看帮助与参数错误
- **WHEN** 用户查看帮助，或输入缺值、非整数、越界/重叠端口、无效资源或未知参数
- **THEN** 分别只显示完整帮助，或返回可理解的非零错误，不创建磁盘、不启动 VM

#### Scenario: 选择数据目录和端口
- **WHEN** 用户指定可用安装根目录和合法 `--port 8080`
- **THEN** launcher 使用该目录内的持久盘，并以 `http://127.0.0.1:8080` 作为本次浏览器入口

#### Scenario: UI 或 Core 指定 7172
- **WHEN** 任一 Host 端口选项指定 7172
- **THEN** launcher 在环境和数据访问前说明内部 Agent RPC 保留限制并返回参数错误，帮助和双语说明反映这一兼容变化

### Requirement: 复用原版首次引导且不泄漏秘密

Launcher SHALL 使用锁定上游 Piwork 的原有首次引导，不创建默认管理员、不修改业务授权或绕过 QuickStart。本次冻结输入 SHALL 延续原有浏览器创建首位管理员和正常登录，不使用私有设置链接。真实 API Key、Token 和密码 MUST NOT 写入普通日志。浏览器自动打开不可用或指定 `--no-open` 时 SHALL 输出当前回环访问地址。

#### Scenario: 原版管理员创建及登录
- **WHEN** 新安装就绪并进入当前回环地址
- **THEN** 用户通过原版页面创建首位管理员、确认密码并正常登录；已初始化安装仍要求正常登录，保留原有 CSRF、会话及 Work 权限
