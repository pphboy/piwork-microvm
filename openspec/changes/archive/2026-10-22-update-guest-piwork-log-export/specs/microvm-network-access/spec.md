# MicroVM Network Access Spec Delta

## MODIFIED Requirements

### Requirement: 仅将 UI 和 Core 两个入口转发到回环地址

Host `127.0.0.1:<PORT>` SHALL 转发到 Guest UI/ControlPlane 的实际 PORT，PORT 由 `--port` 选择且默认 17891；Host `127.0.0.1:<CORE_PORT>` SHALL 转发到 Guest Core API 的实际 CORE_PORT，CORE_PORT 由 `--core-port` 选择且默认 17871。Guest 两项 HTTP 监听 SHALL 默认与现有端口相同，并随所选 Host 端口联动，内部 Core 客户端和浏览器 origin SHALL 使用对应实际端点；MUST NOT 仅更换 Host 转发而仍假定 Guest 固定监听。仅这两个入口 SHALL 被发布；MUST NOT 预占或转发旧 17891–17954 Service 端口池，也不转发 Docker API、内部 Agent RPC、QMP/QGA 或目录共享通道。Guest 的两项 HTTP 监听 SHALL 可由 NAT 到达，Host 监听 SHALL 始终限定 IPv4 回环地址。适配 MUST NOT 新增反向代理或放宽上游 Host/Origin/CSRF 和 Service 授权。

#### Scenario: 验证监听与真实转发
- **WHEN** 使用默认或自定义主入口启动并检查全部监听
- **THEN** 实际只有两个 IPv4 回环转发，分别到达与所选 Host 端口一致的 Guest UI/Core，默认仍为 17891/17871，局域网不能直接访问；UI 承载浏览器页面、登录、引导及 Service Proxy，Core API 供 CLI/backend 使用

#### Scenario: 同时运行独立安装
- **WHEN** Windows 与 Linux 实例使用各自的数据盘、不同的 UI 端口和不同的 Core 端口启动
- **THEN** 两者能同时运行并访问原版 Service，不竞争旧 Service 端口池；不得放宽同一磁盘的独占保护

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
