# MicroVM Network Access Spec Delta

## Purpose

定义 Host 浏览器、Guest 以及真实 Work 容器之间的网络边界，使 Piwork 主入口和受保护的 Service 能经 NAT 使用，并避免仅验证首页可达就误判完整业务网络已经接通。

## ADDED Requirements

### Requirement: 使用 user-mode NAT 提供 Guest 网络

VM SHALL 通过 QEMU user-mode networking 和 VirtIO-MMIO 网卡取得 DHCP 地址、默认路由及 DNS。Guest 和真实 Work 容器 SHALL 均能解析外部域名并建立出站 HTTPS 连接；无需 Host TAP、bridge、root 网络配置或新的 Infra Daemon。Guest Docker 管理的 Work bridge/NAT 保留既有语义。

#### Scenario: Guest 与 Work 分别联网
- **WHEN** 分别从 Guest 和真实 Work 网络中的容器请求外部 HTTPS 与域名解析
- **THEN** 两者均成功，证据区分测试来源；Host 自己联网或预下载镜像不能替代其中任一个测试

### Requirement: 主站和全部 Service 端口仅绑定回环

VM SHALL 通过 QEMU `hostfwd` 将 Host `127.0.0.1:<PORT>` 转发到 Guest 7171，其中 PORT 由 `--port PORT` 指定且默认 7171；同时逐端口转发 Host `127.0.0.1:17891–17954` 到相同 Guest 端口。所有转发 SHALL 仅监听 IPv4 回环地址，不转发内部 Agent RPC、Docker API 或控制通道；主入口参数不改变 Service 端口范围。

#### Scenario: 检查监听范围
- **WHEN** VM 以默认端口或合法自定义主入口端口运行，Host 检查所选端口和全部 Service 端口监听
- **THEN** 全部 65 条转发仅在 IPv4 回环地址，主入口到达 Guest 7171，Guest 7172、Docker socket/API 及 Guest 管理通道没有新增转发

#### Scenario: 原默认端口被其他程序占用
- **WHEN** Host 7171 已被其他程序占用，用户以可用的 `--port 8080` 启动且全部 Service 端口可用
- **THEN** 主入口通过 `127.0.0.1:8080` 到达 Guest 7171，不检查或绑定 Host 7171，不访问或影响占用它的程序

### Requirement: 保留主站来源和受保护 Service 链路

Piwork SHALL 对浏览器发布 `http://127.0.0.1:<PORT>` 及 Host 可访问的受控 Service URL，公开 origin、首次设置链接和主站来源校验 SHALL 与本次选择的 Host 端口一致。Guest Core 仍监听 7171，内部托管客户端和 Agent 回连 SHALL 到达实际 Guest Core，不因公开 origin 的 Host 端口与 Guest listener 不同而误连其他进程。Service SHALL 继续使用既有来源隔离、认证、Cookie 与撤销机制，不能以直接发布容器端口替代。

公开 origin SHALL 采用浏览器的规范表示；PORT 为 HTTP 默认端口 80 时省略 `:80`，转发仍使用 80。此规范化 SHALL 同时用于来源校验、首次设置链接、Host 探针和输出，不能放宽既有来源检查。

#### Scenario: 完成浏览器引导
- **WHEN** 用户从默认或自定义端口的 Host 公开主地址完成首次授权、创建管理员、登录和 QuickStart
- **THEN** 来源/CSRF 校验、资源和后台请求均成功，Service 链接不包含 Guest 私网地址，平台凭证不交给应用

#### Scenario: 真实 Work Service 可访问
- **WHEN** 通过既有 Piwork 接口在真实 Work 中部署 HTTP Service 并从工作台打开
- **THEN** Host 浏览器通过 17891–17954 中的受控入口读取真实响应，未授权请求被拒绝，停止 Work/Service 后原访问权限按既有边界撤销

### Requirement: 支持实际业务的持续连接

网络集成 SHALL 在默认和自定义主入口配置下，分别对同一真实 Service 验证 HTTP、WebSocket 升级/双向消息及 SSE 或现有业务流式连接，保留路径、查询与受支持的会话行为；仅 TCP 建连或主入口的 HTTP 200 不能作为此项通过依据。

#### Scenario: 跨 NAT 的 Service 流式连接
- **WHEN** Host 浏览器通过受授权 Service 入口收发 WebSocket 消息并接收流式响应
- **THEN** 内容与 Guest 内服务实际输出一致，连接不被转发层错误截断，关闭/撤权继续遵守既有规则

### Requirement: 端口冲突明确失败

launcher SHALL 检查本次所选主入口和全部 64 个 Service Host TCP 端口，明确指出冲突或不可用的地址和端口；QEMU 在检查后因竞争而绑定失败时 SHALL 给出同样可理解的错误。端口缺项不得静默跳过、扩大监听地址或选择未公开的替代端口。

#### Scenario: 主站或 Service 范围被占用
- **WHEN** 本次所选主入口端口或 Service 范围内任一端口被其他进程占用
- **THEN** 启动以非零状态报告具体冲突，不保留半启动 VM、不修改原用户数据或影响占用端口的进程
