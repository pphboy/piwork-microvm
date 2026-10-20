# Proposal

## Why

Piwork 已有包含 Core、工作台、管理界面和首次引导的统一 Linux Go 入口，但当前安装仍要求宿主 Docker。需要一个 Linux x86-64 可执行文件，自动启动真正的 KVM MicroVM，在浏览器内完成现有 QuickStart、Work、AI、Files 和 Service 流程，并在停止或重建 VM 后保留数据。

## What Changes

- 新增可重建的 Guest：Linux kernel、RootFS/init、Docker Engine/containerd，以及从同一 Piwork 源码构建的统一服务端和生产 Agent/helper 镜像。按依赖顺序启动，必须能创建真实 Work 容器。
- 新增 Go launcher，检查 KVM、端口、资源和单实例锁，以 `-M microvm`、KVM 和 VirtIO-MMIO 启动一个 VM，按真实状态等待引导/运行就绪，并协调正常关闭。
- 通过 QEMU user-mode NAT/DHCP/DNS 提供出站连接，仅向 Host `127.0.0.1` 转发主入口和 17891–17954。新增 `--port PORT` 选择 Host WebUI/Core 端口，默认 7171，始终转发到 Guest 7171；Guest 公开 origin、首次设置链接、Host 探针和输出地址同步使用所选端口，复用既有 Service 授权网关及 WebSocket/SSE 行为。
- 同时提供 Host 普通文件的真实 9P 共享与 ext4 持久磁盘。Core SQLite、Work 私有历史/Memory、Docker 内部存储和需要数据库语义的 Service 数据保留在 ext4；共享范围及 Work 文件接入方式必须明确，不能把磁盘镜像称为直接目录共享。
- 生成 `dist/piwork-microvm` Linux ELF，内含 QEMU 及运行库/固件、kernel、RootFS、Piwork 和必要镜像，首次启动校验并解包，后续复用缓存和持久盘。依赖宿主 QEMU 的版本仅是开发阶段产物。
- 增加真实 KVM 验收入口及所属证据，覆盖浏览器引导、真实 Work/Service、网络、共享、正常关闭、二次启动恢复、失败路径及干净 Host 分发；缺少 AI Key 时如实区分确定性验证与真实供应商调用。

## Capabilities

### New Capabilities

- `microvm-guest-runtime`：Guest 的可重现构建、完整 Piwork 运行依赖、启动顺序及真实容器运行能力。
- `microvm-launcher-lifecycle`：命令行、前置检查、唯一 VM/数据所有者、分阶段就绪、无秘密日志及正常关闭。
- `microvm-network-access`：仅回环端口转发、Guest/Work 出站、现有浏览器及 Service 网关连接。
- `microvm-persistent-storage`：Host 共享文件、ext4 数据边界、数据库可靠性、持久身份和重启恢复。
- `microvm-single-binary-delivery`：自包含 ELF、可信构建输入/缓存、重建命令及真实 KVM 交付证据。

### Modified Capabilities

无。本项目的 `openspec/specs/` 尚无主规格；上述能力定义 MicroVM 交付层。上游 Piwork 的两卷存储、Work/Service 生命周期、授权、首次设置和发行镜像身份契约作为兼容边界，不在此重新定义。

## Impact

- 实现归属当前独立仓库 `/home/p/Projects/piwork-microvm`，拟新增 `cmd/`、`internal/`、`guest/`、`scripts/` 和构建入口；不直接修改旁边已有 Piwork 工作区。
- 源码依据为目标仓库本地 clone `/home/p/Projects/piwork`，当前提交 `efce08c228c12f10d18a968b69c3398bb0e783e1`。构建必须显式锁定源码并记录实际输入，不纳入其无关未跟踪 `promo/`。复用 `cmd/piwork-serve/`、`internal/app/`、Makefile、`scripts/build-go.sh`、`Dockerfile.agentd` 及 native helper Dockerfiles；如确需小范围 Guest 存储适配，以本项目可审阅补丁维护，不重构 Core。
- 新增构建依赖包括固定版本的 Linux、Guest 基础系统、Docker 28+、QEMU、镜像构建工具，以及上游 Go 1.25.5/Node 24 工具链。最终 Host 运行仅要求受支持 Linux x86-64、可访问的 KVM、足够磁盘/内存及可用端口。
- 只做 Linux + KVM、一个 VM，不新增 Infra Daemon，不改 UI、既有业务 API 或产品使用流程；不推送远程、不发布 Release。
- `--port` 仅选择本次启动的 Host 主入口，不改变 Guest Core/Agent 内部端口、Service 端口范围、数据目录关联或单实例锁。参数接受 1–65535 的整数，但排除 17891–17954；占用或权限不足时明确失败，不自动换端口。新增端口行为需用重建后的单文件产物在真实 KVM 中验证，原验收结果不代替此项验证。
- 初始提案阶段只读确认了 KVM API 12、QEMU 10.0.8 的 microvm/MMIO 设备与 user 网络可用；后续基线及端口增量的实际构建、KVM 测试结果和版本边界记录在 [acceptance.md](acceptance.md)，不以初始环境检查替代运行验收。
