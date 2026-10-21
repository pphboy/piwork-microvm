# microvm-network-access Specification

## Purpose

定义两平台通过同一 NAT 访问模型 API、Piwork WebUI、Files 和受授权 Service 的行为。所有 Host 入口保持回环监听，并以真实上传下载、Work 网络及持续连接验证完整业务，而非只验证首页可达。

## Requirements

### Requirement: 使用 NAT 提供 Guest 和 Work 网络

Guest SHALL 通过 QEMU user-mode networking 和 VirtIO-MMIO 网卡获得 DHCP、DNS 和出站网络，Guest Docker SHALL 为真实 Work 提供其原有容器网络。Host SHALL 无需 TAP、bridge、额外虚拟网卡驱动或 WSL 网络转发。

#### Scenario: 双层网络访问外网
- **WHEN** 分别从 Guest 和真实 Work 容器执行 DNS 与 HTTPS 请求
- **THEN** 两者均成功，结果区分请求来源；Host 自己联网不能代替验证

### Requirement: 仅将 UI 和 Core 两个入口转发到回环地址

Host `127.0.0.1:<PORT>` SHALL 转发到 Guest UI/ControlPlane 的实际 PORT，PORT 由 `--port` 选择且默认 17891；Host `127.0.0.1:<CORE_PORT>` SHALL 转发到 Guest Core API 的实际 CORE_PORT，CORE_PORT 由 `--core-port` 选择且默认 17871。Guest 两项 HTTP 监听 SHALL 默认与现有端口相同，并随所选 Host 端口联动，内部 Core 客户端和浏览器 origin SHALL 使用对应实际端点；MUST NOT 仅更换 Host 转发而仍假定 Guest 固定监听。仅这两个入口 SHALL 被发布；MUST NOT 预占或转发旧 17891–17954 Service 端口池，也不转发 Docker API、内部 Agent RPC、QMP/QGA 或目录共享通道。Guest 的两项 HTTP 监听 SHALL 可由 NAT 到达，Host 监听 SHALL 始终限定 IPv4 回环地址。适配 MUST NOT 新增反向代理或放宽上游 Host/Origin/CSRF 和 Service 授权。

#### Scenario: 验证监听与真实转发
- **WHEN** 使用默认或自定义主入口启动并检查全部监听
- **THEN** 实际只有两个 IPv4 回环转发，分别到达与所选 Host 端口一致的 Guest UI/Core，默认仍为 17891/17871，局域网不能直接访问；UI 承载浏览器页面、登录、引导及 Service Proxy，Core API 供 CLI/backend 使用

#### Scenario: 同时运行独立安装
- **WHEN** Windows 与 Linux 实例使用各自的数据盘、不同的 UI 端口和不同的 Core 端口启动
- **THEN** 两者能同时运行并访问原版 Service，不竞争旧 Service 端口池；不得放宽同一磁盘的独占保护

### Requirement: 浏览器来源和首次引导一致

Piwork 对外 origin、Host 探针和首次设置入口 SHALL 与所选主端口一致，保留原有来源、CSRF、登录和 Service 授权行为。HTTP 默认端口 80 SHALL 使用浏览器规范 origin `http://127.0.0.1`。Guest 内部客户端 SHALL 继续连接实际 Core，不误用 Host 回环端口作为 Guest 内部服务地址。

#### Scenario: 自定义端口完成设置
- **WHEN** 用户以可用的 `--port 8080` 进入原版 QuickStart、创建管理员并登录
- **THEN** 原有 QuickStart、资源和后台请求正常，链接使用 Host origin，内部 Agent 仍能回连 Guest Core

#### Scenario: 更换端口继续使用
- **WHEN** 用户停止同一安装后改用另一合法主端口
- **THEN** 数据和身份保持，浏览器按新 origin 重新登录，不重置安装、不放宽来源校验

### Requirement: 通过原有 Files 上传和下载

两平台 SHALL 支持通过 Piwork 原有 Files 将文件上传到当前 Work workspace，并下载相同字节。Guest 的 Agent 和获准 Service SHALL 看到同一卷中的文件。操作 MUST NOT 要求 Host 目录映射、手工复制到镜像或新增产品 UI。

#### Scenario: 上传下载和跨进程读取
- **WHEN** 用户在真实 Work 中上传包含中文名称的文本和二进制文件，随后由 Agent/获准 Service 读取并从浏览器下载
- **THEN** 文件路径、长度和内容哈希符合原有 Files 语义，所有消费者访问同一持久卷，下载字节与预期一致

### Requirement: 验证真实 Service 和持续连接

Host 浏览器 SHALL 能通过原有授权网关使用真实 Work Service 的 HTTP、WebSocket 和 SSE 或现有流式响应，保持访问撤销和 workspace grant 行为。MUST NOT 用直接发布容器端口绕过 Piwork 授权。

Service SHALL 通过上游 UI 同源 `/services/<workId>/<serviceId>/<port>/` 路径访问，无额外 Host Service 端口。验证夹具 SHALL 遵守上游动态路径前缀语义，不能修改 Piwork 业务代码来补偿旧夹具假设。

#### Scenario: Service 访问及撤权
- **WHEN** 用户打开一个真实 Work Service，完成 HTTP、WebSocket 双向消息和流式读取，然后撤权或停止该 Service
- **THEN** 授权期间内容正确，之后访问按原有规则拒绝；无授权或无 workspace 权限的调用不能读取文件

### Requirement: 端口冲突明确且不干扰其他程序

所选 UI 或 Core 端口不可用时 SHALL 在完整启动前明确报出冲突地址；两个端口相同、越界或任一为内部 Agent RPC 保留端口 7172 时 SHALL 在访问虚拟化或数据前报错。检查后的绑定竞争 SHALL 同样被处理。MUST NOT 自动换用户端口、结束占用进程或扩大监听范围；其他旧 Service 端口被占用 SHALL 不影响启动。

#### Scenario: 默认端口已占用
- **WHEN** 默认 UI 端口被其他程序占用，用户选择可用的 8080 且所选 Core 端口可用
- **THEN** 启动使用 8080，不访问或影响占用默认端口的程序

#### Scenario: 必要端口冲突
- **WHEN** 本次 UI 或 Core 端口已占用，或 QEMU 在绑定时遇到竞争
- **THEN** 报告具体错误并清理半启动 VM，保留用户数据及其他程序

#### Scenario: 拒绝内部 RPC 保留端口
- **WHEN** 用户分别把 UI 或 Core 选项设为 7172
- **THEN** 明确说明该端口保留给内部 Agent RPC，在加速器检查和安装读写前返回非零错误，不启动 VM、不创建安装目录
