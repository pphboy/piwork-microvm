# MicroVM Launcher Lifecycle Spec Delta

## Purpose

定义用户单次启动 Piwork MicroVM 时依赖检查、唯一数据所有者、真实就绪和有序关闭的可观察行为，使启动失败可诊断，普通退出不会破坏或清空已有安装与 Work 数据。

## ADDED Requirements

### Requirement: 提供 Linux 单命令入口

launcher SHALL 支持无参数启动、`--data-dir DIR`、`--port PORT` 和 `--help`，默认使用合理且明确的 CPU/内存配置；提供 `--cpus` 和 `--memory` 时 SHALL 校验其值。`--port` SHALL 默认 7171，仅接受 1–65535 的整数，并拒绝与固定 Service 范围 17891–17954 重叠的值。非法端口 SHALL 在 KVM 检查、缓存提取或用户数据写入之前明确失败，不用 0 请求自动分配，不静默回退。`--help` SHALL 显示端口用途、默认值和限制，无需 KVM、启动 VM 或写入用户数据即可成功。运行平台 SHALL 限于 Linux x86-64 + KVM。

#### Scenario: 默认启动与帮助
- **WHEN** 用户运行 `./piwork-microvm --help` 或在满足条件时无参数运行
- **THEN** 分别显示完整参数/数据说明，或自动准备资源并启动唯一 VM，不要求手写 QEMU 命令或 Docker 操作

#### Scenario: 参数错误
- **WHEN** 用户传入未知参数、无效 CPU/内存、缺失或非数字的端口、0、负数、超过 65535 或落入 17891–17954 的端口，或不可用数据路径
- **THEN** 程序以非零状态退出并给出明确原因，不启动 VM、不重置已有数据

#### Scenario: 自定义 Host 主入口
- **WHEN** 用户以 `--port 8080` 启动且 KVM、资源、所选端口和 Service 端口均可用
- **THEN** launcher 将 Host `127.0.0.1:8080` 转发到 Guest 7171，并使用 `http://127.0.0.1:8080` 检测就绪、验证私有首次设置链接及输出访问地址

### Requirement: 在启动前验证 KVM 和资源

launcher SHALL 检查 `/dev/kvm` 存在、当前身份可读写并可完成 KVM API 检查，检查缓存完整性、必要端口、数据目录和持久盘可用性。缺少硬件加速或权限时 MUST NOT 自动改为 TCG、其他机型或宿主运行 Piwork。

#### Scenario: KVM 缺失或权限不足
- **WHEN** KVM 不存在、无法打开或 API 检查失败
- **THEN** 程序在启动 QEMU 前以非零状态说明 KVM/权限问题，没有软件模拟回退

### Requirement: 一个 VM 独占一组数据

launcher SHALL 以 `-M microvm`、KVM、host CPU 和 VirtIO-MMIO 启动一个 VM，禁止使用 PCI 设备。launcher SHALL 在准备可写数据前获得持续有效的数据/磁盘独占锁，并保证 launcher 异常退出但 QEMU 仍运行时其他实例不能写同一磁盘；只有全部相关写者退出后才能释放占用。

#### Scenario: 同一数据二次启动
- **WHEN** 原 launcher 或其 QEMU 仍使用同一持久盘，另一个进程再次启动
- **THEN** 后者明确失败而不启动第二个可写 VM；通过端口前置检查后仍须报告安装占用，更换主入口端口、路径拼写或使用同一盘的别名均不能绕过磁盘锁

#### Scenario: 正常停止后更换主入口端口
- **WHEN** 用户正常停止安装后，使用相同 data-dir 和不同的合法 `--port` 再次启动
- **THEN** 继续复用原安装、持久盘、管理员、配置、Work 和 Service 数据，不要求重新 QuickStart；浏览器在新的 origin 重新登录并重新取得 Service 授权入口，不沿用旧 origin 的会话授权

#### Scenario: 核实实际虚拟化方式
- **WHEN** 真实验收检查 QEMU 运行状态和 Guest 设备
- **THEN** 确认 microvm、KVM enabled、唯一 VM 和 MMIO 设备，而非仅从脚本中的参数文字推断

### Requirement: 区分引导可访问与完整运行就绪

launcher SHALL 根据 Guest 阶段状态、存活的 QEMU 以及本次所选 Host 主入口上的 `/healthz` 和 `/readyz?profile=docker-delivery` HTTP 探针等待服务，不采用固定 sleep 宣布成功。空安装 SHALL 在 Docker/镜像准备成功且现有引导可访问后输出 `http://127.0.0.1:<PORT>`，明确需要完成 QuickStart；不得等待必须先有人配置模型才会成功的完整 ready 探针。已配置安装 SHALL 继续观察完整交付 readiness，报告真实准备或失败状态。

上述 URL SHALL 使用浏览器规范 origin，HTTP 80 端口省略 `:80`；该表示仍指向所选 Host 端口，不改变实际转发或检查范围。

#### Scenario: 空安装没有模型
- **WHEN** Guest 和引导页面已就绪但尚无管理员或模型配置
- **THEN** 用户及时得到可访问入口和本机首次授权取得方式，launcher 保持运行，不将待配置误报为 Guest 启动失败或完整 Work 就绪

#### Scenario: 配置后准备成功或超时
- **WHEN** 已有配置的安装准备依赖，随后完整交付探针成功或达到有界启动期限
- **THEN** 分别报告运行就绪，或提供失败阶段、脱敏日志路径及可重试方向；失败不能只输出笼统的端口等待超时

### Requirement: 首次设置授权和日志不泄漏秘密

launcher/Guest SHALL 保留现有一次性首次设置证明和登录语义，不创建默认管理员或在无授权情况下开放 bootstrap。真实 API Key、密码、operator/用户凭证、首次设置证明及浏览器票据 MUST NOT 进入运行日志、验收报告或公开输出。安装者 SHALL 能通过仅当前 Host 用户可读的本地授权交付方式进入现有设置页面；可选浏览器打开器缺失不能成为启动依赖。

#### Scenario: 首次引导需要授权
- **WHEN** 空安装产生首次设置证明
- **THEN** 安装者获得仅本机私有的引导入口，该链接使用本次所选主入口 origin；普通日志只显示无凭证的访问地址和安全提示，匿名打开主地址仍不自动获得创建管理员权限

#### Scenario: 故障与诊断
- **WHEN** 启动、供应商连接或 Guest 服务发生错误
- **THEN** 日志保留阶段、退出状态和诊断上下文，秘密值与携带授权的 URL 不被写入

### Requirement: 有序关闭并如实报告强制终止

收到 Ctrl+C、SIGTERM 或正常停止请求时，launcher SHALL 先请求 Guest 正常关闭，由 Guest 停止 Piwork 并等待其 Work drain，随后停止 Docker/containerd、同步并卸载持久文件系统，最后等待 QEMU 退出。关闭预算 SHALL 覆盖现有 Piwork 的 45 秒关闭预算和后续磁盘收尾。超时或关闭未确认时 SHALL 明确报告异常关机，不把强制 kill 记为正常成功；任何路径都不得删除用户数据。

#### Scenario: Work 运行中停止
- **WHEN** 用户在真实 Work/Service 运行时按 Ctrl+C
- **THEN** Core 按既有契约停止本安装受管运行容器并保留持久意图，磁盘完成同步、QEMU 退出且锁释放，下一次启动可恢复

#### Scenario: Guest 卡死
- **WHEN** Guest 在关闭期限内无法确认正常退出
- **THEN** launcher 说明未确认阶段及采用的有界终止动作，以非零状态结束，保留磁盘和诊断，不声称已完成干净卸载
