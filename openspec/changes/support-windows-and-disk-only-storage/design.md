# Design

## Context

动机与首发范围见 [proposal.md](proposal.md)。本次不定义旧版 9P 产品、安装识别、兼容或迁移，当前源码中的共享实现仅作为待清理项。规划阶段不修改实现、构建锁或上游源码。

以下记录变更制定时的实现基线；当前实现与完成证据见任务表及验收附件：

| 位置或环境 | 对本设计的约束 |
| --- | --- |
| 上游远程 `main` | 本次刷新后 HEAD 为 `a6c36da16ebcc0e96f0e34ef820d857f2bea4877`；`.nvmrc` 为 24，`go.mod` 为 Go 1.25.5 |
| 最新上游 `internal/app/run.go` | 统一入口包含 Core、WebUI、管理与首次设置；0.0.8 已删除私有设置链接，浏览器直接创建首位管理员；0.0.9 已拆分 UI `--listen` 和 Core `--core-listen`，Service 使用 UI 同源 `/services/...`，已移除 `--service-ports` |
| 最新上游 `scripts/build-docker-release.mjs`、Agent Dockerfile | 已有源码/UI hash、生产镜像身份和 Server 嵌入引用生成流程，可本地复用而不发布 |
| 最新上游 `internal/corestore/store.go`、`internal/dockerengine/resources.go` | Core 使用 WAL/FULL sync；Work 使用 Docker local named volumes，不能把 Core 配置目录误认为全部 Work 数据 |
| 最新上游 `apps/desktop-webui/src/files.ts` | 已有上传 PUT 和下载入口，本变更不需要新增文件 UI |
| `cmd/piwork-guest/main.go`、Guest Docker unit | Core 已绑定 `/mnt/state/core`；Docker data-root 已是 `/mnt/state/docker`，但当前启动仍强制挂 9P |
| `scripts/source.py`、`guest/patches/` | 当前构建会应用 Piwork 补丁；删除补丁文件后复用已修改 checkout 也可能残留修改，必须改用干净输入 |
| `internal/{launcher,bundle,qemu}` | launcher/bundle 是 Linux-only；控制通道、flock、额外继承 fd 和动态 loader 都需要平台拆分 |
| 固定 QEMU 10.0.8 源码 | WHPX 明确拒绝 `kernel-irqchip=split`，microvm 机器默认带 split 假设；Windows 文件后端明确拒绝 `locking=on`，普通文件以共享读写方式打开 |
| 当前 Windows 本机检查 | Windows 11 Home，build 26200；HypervisorPresent=true，HypervisorPlatform 功能已启用。尚未用原生 QEMU 验证 microvm/WHPX 启动 |

变更制定时 `openspec/specs/` 为空，因此五份规格使用 ADDED 定义首发契约，现已同步过主规格。其他实验变更和日志不作为本次最终产物的通过证据。

## Goals / Non-Goals

**Goals:**

- 平台差异集中在 Host launcher、QEMU 参数及打包，共用 Guest、原版 Piwork、磁盘布局和业务验收流程。
- 把可替换系统资源与唯一持久数据盘明确分开，使缓存修复不会变成空安装或数据重建。
- 在制作完整 Windows 包之前验证 microvm/WHPX 的硬件启动路径、设备、控制和停止，尽早解决真实兼容问题。
- 让启动失败、首次待配置、运行就绪和未确认关闭都有准确诊断；所有验证关联本次产物与源码身份。

**Non-Goals:**

- 目录共享、映射盘、9P、SMB、FUSE、双向同步或 Host ext4 驱动。
- Windows 10、macOS、ARM64、TCG、其他机型、单个 launcher 管理多 VM 或新的管理 daemon。独立安装可各自启动一个 VM。
- 修改 Piwork 业务源码/协议/UI、改变 Work/Service 卷和授权语义、默认管理员或伪造模型调用。
- 旧产品兼容/自动迁移、跨系统一键迁移、热备份、磁盘扩容和自动在线更新；不推送远程、不发布 Release。

## Decisions

### 1. 最新上游只在构建准备阶段解析，后续按完整 commit 重建

实施首次准备时向 `https://github.com/pphboy/piwork.git` 解析最新默认分支及 HEAD，更新 `build.lock.json`，记录完整 SHA、分支、解析时间和实际输入 hash。本次核对的 `9a40d444…` 是规划观察值，不要求实施时继续使用已落后的 SHA。之后普通构建只消费锁；刷新上游是显式开发操作，用户启动不联网拉源码。

在本项目受管 `dist/` 中创建独立、按 commit 标识的干净源码副本，构建前检查来源、HEAD 和工作树。移除自动应用 `guest/patches/*.patch` 的逻辑，不保留文件中混入的契约、文件辅助或快照修改。相邻 `/home/p/Projects/piwork` 的分支、未跟踪文件和修改保持原状。

沿用上游现有构建及发行身份工具生成统一服务端、WebUI 和生产 Agent/file/snapshot-helper；package-helper 按上游原规则复用 Agent。构建参数和镜像标签必须对应同一源码/UI 输入。构建生成的版本清单、镜像引用和编译标记按上游流程产生，不通过业务补丁实现。

选择这一方式，既满足“最新源码”，也能重建已验收产物。每次运行追踪浮动 `main` 会破坏离线启动、版本一致性和复现；直接复用脏 checkout 或任意历史镜像也无法证明原版来源。若上游原版有阻塞缺陷，先定位并记录，不私加 Piwork 修复补丁或静默回退旧 commit。

### 2. 共用无共享 Guest，所有持久内容放进独立 ext4 盘

继续使用固定依赖的 Linux kernel、Debian RootFS、systemd、Guest Docker 和 qemu-guest-agent。保留只读 RootFS 与 tmpfs 根 upper 的启动方式，独立 `state.qcow2` 是唯一可写业务盘，无外部 backing 文件。初始复用 64 GiB 逻辑容量的稀疏模板；Host 文件随实际分配增长，不需要运行时 mkfs 或额外 qemu-img。

Guest 数据映射保持为：

| Guest 使用方 | 持久 backing |
| --- | --- |
| Piwork `--data-dir /var/lib/piwork/core` | bind `/mnt/state/core` |
| Docker data-root | `/mnt/state/docker` |
| Docker 管理的 containerd 实际持久 root | `/mnt/state/docker/containerd/daemon`，构建/运行时核对实际配置 |
| 标准 `/var/lib/containerd` 路径 | bind `/mnt/state/containerd` |
| Work private/workspace 及 Service 声明卷 | 上游 local named volumes，位于持久 Docker data-root |
| 临时进程/容器 state、根 upper | 原有临时路径，不当作持久数据 |

删除强制 9P mount、`/etc/piwork/workspace-sharing`、`--workspace-shared-root`、Host xattr 探测、QEMU Host UID 补丁和 kernel 9P 专用补丁/配置。构建和验收不再使用共享子树。Guest 内部为持久盘做 bind mount 继续保留；它们不是 Host 目录共享。

启动依赖为 state/ext4 确认、DHCP/DNS、Docker、生产镜像身份准备、Piwork。必要存储失败即停止后续服务。业务文件经原有 Files 写入 workspace 卷，既保留权限与快照规则，也使 SQLite 保持本地 ext4 语义；无需移植 NTFS/POSIX 目录语义。

### 3. `--data-dir` 是完整安装根，缓存单独管理

默认安装根：Linux 为 `${XDG_DATA_HOME:-~/.local/share}/piwork-microvm`，Windows 为 `%LOCALAPPDATA%\PiworkMicroVM`。自定义 `--data-dir` 直接选择该根，不通过额外共享目录 hash 将磁盘藏到其他位置。

```text
<installation-root>/
  installation.json
  disks/
    state.qcow2
  logs/
```

安装元数据记录启动器安装身份、磁盘关联/格式和初始化完成状态。Piwork 自行创建业务安装身份、账号及数据库，launcher 不注入业务账号或修改 Core schema。新盘只从经过校验的模板原子创建一次；临时初始化文件仅在确认属于本次未完成的新安装时可重试清理。已有完成记录而盘缺失/损坏时失败，遇到未知内容时不覆盖。

缓存位于独立用户缓存路径，按 Host OS/architecture 与 bundle 内容身份管理，不承担业务数据。日志与安装根一起可定位，私有运行控制材料放在当前用户受保护的运行目录。Windows 安全边界使用 ACL 与规范文件身份，不能把 chmod 视为等价保护。

对外只承诺首发新安装及该首发安装的再次启动，不增加专门的旧 9P 识别/迁移协议。格式不匹配按普通未知数据保护处理即可。备份在停止后复制磁盘和安装元数据；缓存可省略。不提供运行中 Host 挂载 ext4 或热复制一致性承诺。

### 4. microvm/MMIO 固定，两个加速器分别验证参数

共同使用 `-M microvm,pcie=off,acpi=off,auto-kernel-cmdline=on`、外置 kernel/initramfs、只读 RootFS、独立 qcow2 盘、virtio-blk/net/serial/rng 的 MMIO 设备，默认 2 vCPU、4096 MiB。移除全部 `-fsdev` 和 `virtio-9p-device`。

Linux 使用 KVM，保留该后端的 CPU、中断和 block 参数并重新验证。Windows 实测收敛为 WHPX `kernel-irqchip=on` 和 `qemu64`：split 不受支持，off 在双核 Guest 中出现 IPI 等待，max 组合未正常启动。通过 Windows WHPX API 查询实际处理器时钟，向共同内核传递 `tsc_early_khz`、`tsc=reliable` 和 `clocksource=tsc`，解决 microvm 无参考计时器时的校准与时钟漂移。不复制 Linux 的 `-cpu host` 或 `file.locking=on`，不更换机型或启用 TCG。

Windows block 参数选择支持 Guest flush 的常规 writeback 模式，禁止 unsafe，验证 ext4/SQLite 写入到 Host `FlushFileBuffers` 路径；Linux 可使用其已验证的直接 I/O 配置。缓存策略属于平台参数，不改变共同的持久性要求。

第一阶段必须在 Windows 本机启动真实 WHPX microvm，确认 kernel、块设备、DHCP、私有控制和有序停止。qboot 是先行验证固件；任何兼容修正均保留 microvm/MMIO 与硬件加速约束。失败时调查具体 CPU/IRQ/时钟/固件原因，不以换 q35、启用 PCI 或 TCG 来打勾。兼容目标从 Windows 11 Home 21H2 起；本轮只记录当前 Home/WHPX 实测环境，不再要求多版本验收矩阵。

### 5. Host 平台适配同时覆盖锁、进程和私有控制

保留公共参数、阶段状态、HTTP 探针、日志过滤、bundle 格式和 Guest 操作逻辑；将路径/权限、虚拟化探测、锁、进程启动/退出、控制 transport、浏览器打开拆为平台文件。避免把 Unix socket、SIGTERM 或 Linux fd 行为隐藏在通用代码中。

**独占：** 安装初始化先持有安装根锁，盘存在后再基于实际磁盘文件身份取得写者保护，防止别名绕过。Linux 可使用 flock 与 QEMU 继承 fd 保持锁。Windows 使用拒绝共享打开的锁句柄，并将其作为原生继承句柄交给 QEMU；键包含卷标识和磁盘 File ID，不能只 hash 未规范化路径。共享打开限制由句柄生命周期维持，不能仅依赖父进程拥有的 mutex 或会随父进程释放的字节锁。

Windows QEMU 的文件后端不支持 `locking=on`，因此显式去掉该参数，不能把它当作独占保障。QEMU 进程结合 Job Object 管理，正常退出先有序关机，异常父进程退出时可联动收尾；无论子进程存活还是正在退出，继承的磁盘身份锁都须阻止第二个写者。先做原生进程/句柄小规模验证，检查 QEMU 是否确实持有保护直到退出；不能用仅测试 launcher 的锁来替代。

**控制：** Linux 保留私有 Unix sockets；Windows 使用安装专属 named pipes 承载 QMP 与 QGA，不开管理 TCP 端口。QEMU 的 pipe 后端会创建 named pipe 并等待连接，因此 launcher 必须在进程启动期间及时连接，按 transport 维护持久连接、请求 ID 和事件处理，不能照搬每次请求新连 Unix socket 的行为。

named pipe 从创建起就须有当前用户的访问边界。实测 Win32 为 NULL security attributes 创建的管道忽略受限 token 默认 DACL，包含 Everyone/Anonymous 读权限；固定 QEMU Windows 补丁在创建时显式应用 token 默认 DACL，launcher 验证最终 ACL。另一个小补丁处理前端暂停读取时的管道轮询，避免饿死 QMP 调度。随机名称只用于避免冲突。QMP/QGA 必须并行建立初始连接，失败即收尾，不启用管理 TCP。两项均为 QEMU 平台修正，Piwork 源码不变。

**Windows 生命周期：** 正常 Ctrl+C 使用私有 Guest 关机流程；窗口关闭/系统结束会话可能受 OS 的短期限限制。此类未确认关闭必须保留未清洁标志，下一次提示恢复检查；不为追求“正常退出”记录而把 kill 当同步完成。普通终端正常停止是首版可靠关机入口，不增加后台常驻 daemon 或新 UI。

### 6. 分平台封装 QEMU，用户只分发一个文件

保留 Go launcher 加压缩资源、manifest 和尾部索引的单文件形式，分别输出 ELF 与 PE；首次提取不是运行时构建。公共 Guest 内容相同，QEMU/runtime 部分按平台生成清单。

- Linux：从固定源码构建 headless KVM/microvm/SLIRP QEMU，去掉 9P/attr/Host UID 定制，打包 loader、必要库和固件。
- Windows：以固定 QEMU 源码、两项管道补丁和锁定 MinGW/依赖工具链构建 headless x86-64/WHPX/SLIRP 版本，打包 EXE、非系统 DLL 和固件。工具链使用固定 Fedora 基础镜像、184 个有 URL/sha256 的固定 RPM，验证全部安装包身份。编译设置 `FD_SETSIZE=1024`，因为 Windows 默认 64 个 socket 的集合会在 65 个转发 socket 后遗漏 DNS UDP 轮询；已实测修复前 DNS 超时、修复后 DNS/HTTPS 成功。不把预装 MSYS2、开发目录或 Host QEMU 当依赖。
- 构建入口允许 Linux/容器或 WSL 工具链完成交叉编译，最终 PE 的提取、加载 DLL、访问磁盘和控制 VM 必须完全原生。开发环境可用不构成运行依赖证明。
- 归档和 manifest 携带平台、架构、资源 hash、完整输入身份和许可证。提取检查 Linux 路径及 Windows 绝对盘符、反斜线、重解析/链接边界，按包身份原子发布，损坏缓存安全重建。

优先维护一套可复现构建入口，不依赖用户下载不同安装器。若 WHPX 兼容确需调整 QEMU/kernel 版本，锁定新版本及来源后重新验证两平台；不能修改 Piwork 业务来补偿 Host 行为。

### 7. NAT、首次授权和上传下载复用原有语义

共同使用 QEMU user NAT/DHCP/DNS，只对 `127.0.0.1` 转发两个端口：`--port`（默认 17891）到 Guest UI 17891，`--core-port`（默认 17871）到 Guest Core 17871。两者接受 1–65535 且必须不同。Guest 对这两项使用 `0.0.0.0` 监听以允许 NAT 到达，外部暴露由 Host 回环转发限定。UI 公共 origin、浏览器与 UI 探针跟随 `--port`，完整就绪探针同时检查转发后的 Core；80 使用规范 origin。Work Service 使用原版 UI `/services/...` 路径及动态前缀，不配置旧 Service 端口池，不转发 7172、Docker API 或控制通道。独立安装使用不同的两个 Host 端口和各自数据盘可同时运行；同盘独占不变。

Guest 从非秘密 kernel 参数获得 Host 主端口。按照用户明确的“最新源码、不改 Piwork”约束，跟随锁定 0.0.9 已由上游简化的首次引导：浏览器直接打开当前回环 URL、创建首位管理员、正常登录并进入 QuickStart。删除规划中已过时的私有链接/operator 刷新假设，不增加包装层业务授权。空安装以原版引导可用为启动成功状态，随后观察完整 ready；已配置安装检查实际 delivery readiness。QMP/QGA 的 Host 控制权限仍独立使用私有通道。

Files 流程为浏览器上传、原版 file-helper 写入 workspace named volume、Guest/获准 Service 读取、浏览器下载。测试文本、二进制和中文路径的字节/哈希、替换与删除，再跨正常重启验证。无需额外共享进程或产品 UI。

### 8. 有序关闭和备份以真实写者退出为边界

正常停止经 QGA 请求 Guest 按 init 依赖停止 Piwork/Work、Docker/containerd、同步并卸载 state。microvm 的无 ACPI 配置继续先验证 `reboot=t`、`-no-reboot` 的 Guest 有序重启退出路径；WHPX 对 triple fault 的实际行为必须实测。若该路径不兼容，仍可在 Guest 已完成数据盘卸载并报告后由 QMP 结束进程，不改变原版 Piwork。

总关闭预算初始 120 秒，并按最新上游 drain 时间核对。只有 Guest 收尾和真实 QEMU 退出均确认后才写 clean 状态并释放保护；超时或外部强杀保留异常标志、磁盘与诊断。备份说明要求正常停止后复制磁盘和安装元数据，不操作正在运行的 ext4。

### 9. 按关口实施，以最终产物逐平台验收

1. 解析最新上游并锁定干净输入；完成最小 Windows QEMU/WHPX/microvm 真实启动、控制、锁与停止验证。该关口允许先用外置开发资源，但不能据此声明最终单文件交付。
2. 生成无共享公共 Guest，原版 Piwork/生产镜像身份匹配，完成 Linux 真实 KVM 业务回归。
3. 完成 Windows 原生 launcher、打包闭包及真实 Work/Files/Service；再生成两个最终单文件。
4. 对最终产物执行全流程、异常路径、重启与清缓存恢复，记录当前实际环境、hash、实际参数、进程/模块来源及脱敏结果。

2026-10-21 用户确认本轮只使用现有 Linux/KVM 和原生 Windows 11 Home build 26200/WHPX。取消 Windows 多版本覆盖、关闭宿主虚拟化功能的额外环境准备和第二台干净电脑测试，不再将它们列为未完成交付项。保留运行时能力检查和自包含分发要求。使用独立全新 `--data-dir` 验证空安装；宿主依赖与资源缓存不会因更换数据目录自动清空，证据按实际情况描述。

收尾只推进以下两组验收，使用当前最终 ELF/PE，记录产物 SHA256；如修复产品代码导致重建，则对新产物重新关联证据：

1. 两平台分别真实执行 Guest 提前退出、QGA 不可用导致关机超时、launcher 强杀三种场景。每次故障前建立已确认写入的基线，之后用原盘恢复，核对账号/配置、Work/卷身份、文件哈希、Service 数据和数据库完整性。超时必须真实经过关闭预算，不能用缩短预算的测试产物替代。launcher 强杀后，如果 QEMU 仍存活，第二个写者必须持续被拒绝；如果平台 Job 终止 QEMU，则确认退出后才恢复。不将尚未提交的请求写入或强杀期间的活动事务承诺为已持久化。
2. 两平台分别从独立空安装完成 QuickStart、配置实际可用模型、创建 Work，发起真实模型请求并执行可核对的文件工具操作，验证 Files/Service。正常停止后以原目录启动，确认原账号、模型、Work、文件和 Service 数据保持，工具会话历史 HTTP 200，随后在原会话继续一次真实模型请求。只读查看现有成功会话是补充证据，不能代替本轮新安装和重启流程。测试使用专属安装和测试 Work，实际凭证只经受限输入/私有文件传递，不进入普通日志、截图或验收附件。

原合成 Responses 夹具的特定 toolCallId 历史 503 保留为独立异常记录。真实模型验收按具体供应商/协议和会话实测判断，不用该夹具失败代表全部工具调用失败，也不删除原失败证据。若真实模型同样失败，则对应平台任务仍未完成；不修改 Piwork 业务源码来绕过。

## Risks / Trade-offs

- [WHPX 与 microvm 的 IRQ/时钟/固件组合尚未验证] → 最先执行真实 Windows 启动关口，保留机器与加速约束，记录具体失败和修正，不静默换后端。
- [Windows 不支持 QEMU `locking=on`，父进程退出会释放普通父锁] → 使用持续到 QEMU 退出的原生继承保护与磁盘文件身份，并测试父进程强杀、路径别名和重复启动。
- [named pipe 默认 ACL、阻塞连接和断线行为与 Unix socket 不同] → 从创建阶段收紧访问，按 Windows transport 实测持久连接、取消和重连，不增加管理 TCP 口。
- [源码或构建目录残留补丁造成“原版”误报] → 最新 commit 的独立干净输入、补丁列表为空、UI/镜像一致 provenance，构建前核对，不复用不明 dirty tree。
- [Windows API/DLL 依赖不明确] → 固定依赖、检查导入和当前 Home 上实际模块来源；本轮不建立多版本覆盖矩阵或第二台主机验证门槛。
- [Ctrl+C 之外的关闭事件受 OS 时限约束] → 区分正常与异常状态，保留数据、下次恢复检查，绝不宣称强杀已完成 clean shutdown。
- [单盘易备份但 Host 不能直接浏览文件] → 首版明确使用 Files 上传下载，目录共享后置，不把 qcow2 文件称为直接目录映射。
- [真实模型存在协议差异和外部请求失败] → 记录实际模型/协议、Run、工具结果及恢复证据；合成夹具与真实请求分开记录，任何失败不伪造通过。

## Migration Plan

本次按首发新安装实施，不提供旧版本/9P 安装识别或迁移步骤。源码中的旧实现直接清理，既有实验文件和未声明用户目录不自动删除。测试使用专属新安装根，不影响现有 Host 服务。

发布准备只生成本地两个产物及构建/验收材料，不推送或发布。替换测试产物前先正常关闭 VM；保留磁盘和安装元数据，缓存可重新提取。任何无法确认的数据格式或不明非空目录按数据保护规则报错，不通过格式化实现“回退”。
