# Design

## Context

动机见 [proposal.md](proposal.md)。本目录是独立的 MicroVM 项目；初始上游调研通过相邻 `/home/p/Projects/piwork` 只读检查，origin 对应 `pphboy/piwork`，固定提交为 `efce08c228c12f10d18a968b69c3398bb0e783e1`。上游有未跟踪的 `promo/`，不能复制其整个工作区作为构建输入。基线与本次端口增量的实现/验收身份分别记录在 [acceptance.md](acceptance.md)。

已核对的实现事实：

| 上游位置 | 对本设计的约束 |
| --- | --- |
| `AGENTS.md`、`cmd/piwork-serve/main.go`、`internal/app/run.go` | 复用统一 Go 应用；默认包含 Core、ServeUI、管理和首次引导。正常关闭预算为 45 秒，会停止本安装 Work 容器并保留持久意图 |
| `Makefile`、`scripts/build-go.sh` | Go 1.25.5、CGO disabled；先构建 harness/WebUI，再嵌入资源；Node 24 是构建/镜像依赖，不是 Host 运行依赖 |
| `Dockerfile.agentd`、`scripts/build-native-agent-images.sh` | 生产/验收 Agent 分开；Agent 内含真实 TS harness、Pi SDK、Go Service MCP/package-helper；package-helper 复用 Agent 镜像 |
| `Dockerfile.file-helper.native`、`Dockerfile.snapshot-helper.native` | 两个独立 Go helper 镜像，不能只准备 Agent |
| `internal/distribution/`、`scripts/native-server-defaults.mjs`、`scripts/build-docker-release.mjs` | Agent 引用绑定发行身份；普通开发构建的历史默认引用不能代替新构建镜像；用户不能通过 `--agent-image` 覆盖 |
| `internal/corestore/store.go`、`internal/safefs/` | `core.sqlite` 使用 WAL、FULL sync 和文件锁；Core 私有目录有所有者/权限及 no-symlink 检查 |
| `internal/workruntime/runtime.go`、`internal/dockerengine/resources.go` | 每 Work 有两个 Docker local named volumes：private 挂 `/var/data`，workspace 挂 `/var/data/workspace`；当前没有 Host workspace backing 配置 |
| `internal/coreapp/service_runtime.go`、上游 `work-storage` 主规格 | Service 只能按既有 workspace grant 访问受管卷，使用 UID/GID 10001；不能改成任意 Host bind 或给 Service private 卷 |
| `internal/webapp/`、`internal/cli/hosted_services.go` | Service 使用独立端口和来源，Host/Origin 校验严格；公开地址必须显式设置为 Host 浏览器地址 |
| `internal/coreapp/http.go`、`web-onboarding` 主规格 | `/healthz` 可在未配置时成功；完整探针为 `/readyz?profile=docker-delivery`；首次设置需要限时一次性证明，不能取消授权 |

2026-10-20 只读环境检查：Linux x86-64；当前用户属于 kvm/docker 组；`/dev/kvm` 可读写且 `KVM_GET_API_VERSION=12`；QEMU 为 Debian 10.0.8，列出 microvm、VirtIO-MMIO 块/网络/9P/串口和 user 网络；Host Docker 为 26.1.5、Go 为 1.25.5、当前 Node 为 25.6.0。Host Docker 只用于构建；Guest 必须独立提供 Docker 28+，构建使用固定 Node 24。上述检查没有创建 VM，不是运行验收。

## Goals / Non-Goals

**Goals:**

- 从当前源码构建后依次完成 Guest、KVM 启动、网络、数据、单文件、真实验收；每一阶段保留可运行命令，不以设计或宿主 QEMU 阶段作为最终完成。
- 用常规 Linux、Docker、QEMU 和现有 Piwork 的行为完成 Demo，故障能定位到明确阶段。
- 数据库默认使用 ext4；Host 直接共享的普通文件能进入同一 Work workspace，并保持两卷与 Service 授权边界。

**Non-Goals:**

- 多 VM、其他平台/加速器、TAP/Host bridge、新 Infra Daemon、UI 改版、Core 重构、业务协议/数据库格式改版、自动在线升级和公开发行。
- 不承诺任意用户在共享文件子目录自行运行数据库的可靠性，不把 9P 当 Docker overlay backing，不承诺缓存或 rootfs 就是用户备份。

## Decisions

### 1. 独立包装项目，锁定并复用上游构建

本仓库保存 launcher、Guest 配方、必要小补丁、依赖锁定清单和验收驱动。源码获取支持固定 revision 的 Git fetch，以及从指定本地 Git clone 导出该 revision；只导出声明输入，保留提交身份。构建副本放在忽略的 `dist/source/`，不修改相邻工作区、不推送远程。任何补丁作为本仓库 `guest/patches/` 的可审阅文件，并记录补丁 hash 与应用后的实际源码状态。

拟定实现分工：

| 本项目路径 | 职责 |
| --- | --- |
| `cmd/piwork-microvm/`、`internal/{launcher,bundle,qemu,state}/` | Host 参数、检查、打包/提取、QEMU 参数、探针、锁及生命周期 |
| `guest/kernel/`、`guest/rootfs/`、`guest/initramfs/` | kernel 配置、固定基础系统配方、挂载/init 和服务依赖 |
| `guest/patches/` | 仅有必要的、默认关闭的 Guest workspace 共享适配 |
| `scripts/`、`Makefile`、依赖锁定清单 | 获取输入、构建 Piwork/镜像、Guest、QEMU 闭包、单文件及验收 |
| `dist/` | 构建产物、工作源码副本、临时日志、截图和原始验收输出，默认忽略 |

调用上游现有 harness/WebUI/Go 和镜像构建入口。生成本地 candidate 身份，把实际生产 Agent/file/snapshot-helper 的固定引用写入统一服务端的嵌入发行依赖；package-helper 指向同一生产 Agent。检查 UI 输入 hash、平台/协议标签和实际 image ID。不能只 `make build` 后保留旧的 `internal/distribution/images.json` 引用，也不修改或冒用旧发行标签。现有 release 构建入口仅用于本地身份/产物复用，不执行 push/release。

**取舍：** 直接复用上游发布镜像更快，但不满足“基于当前源码”；复制整个上游仓库会引入无关改动且失去输入身份，因此选择固定源码构建加独立包装。

### 2. 固定 Linux Guest 与常规 init

采用 Debian slim 基础 RootFS、systemd、systemd-networkd、CA、iproute2、iptables/nftables、e2fsprogs 和 qemu-guest-agent。基础 OCI digest/软件包 snapshot、Docker 28+ 的具体版本/校验及依赖全部进入锁定清单。Linux 从固定 LTS 源码构建，初始选择 6.6 LTS 系列，具体 patch 版本和 SHA256 在构建配方中固定。

kernel 配置至少检查：`KVM_GUEST`、`VIRTIO`、`VIRTIO_MMIO`、`VIRTIO_MMIO_CMDLINE_DEVICES`、`VIRTIO_BLK`、`VIRTIO_NET`、`NET_9P`/`NET_9P_VIRTIO`/`9P_FS`、`VIRTIO_CONSOLE`、`DEVTMPFS`、ext4、tmpfs、overlayfs、各 namespace、cgroup v2/CPU/memory/pids、veth/bridge、netfilter/conntrack/NAT 及选用的 iptables/nftables 模块。启动所需驱动 built-in，其他必要模块随 RootFS 交付并实际加载，不以仅检查配置代替 Docker 测试。

Guest 资源分离：kernel/initramfs、只读 ext4 RootFS、每安装可写 ext4 state 盘。initramfs 把只读 RootFS 作为 lower、tmpfs 作为 upper，完成根挂载后进入常规 init；可变业务路径明确绑定 state 盘，root upper 不承载持久数据。state 盘由预格式化 ext4 的稀疏 qcow2 模板创建（避免首次解包扫描 64 GiB 零块），初始逻辑容量 64 GiB，Host 不需要 `mkfs`/`qemu-img`。只有新安装原子创建模板；已有盘绝不自动格式化。

服务依赖固定为：state/9P mounts → DHCP/DNS → Docker/containerd → 必要镜像校验/按缺失加载 → Piwork。Docker 的 data-root 为 `/mnt/state/docker`；实查 Docker 生成的 containerd.toml，其实际持久 root 为 `/mnt/state/docker/containerd/daemon`，临时 state 为 `/var/run/docker/containerd/daemon`。另将 `/var/lib/containerd` 绑定到 `/mnt/state/containerd`，避免后续组件在该标准路径写入易失根。本固定静态 Engine 管理自己的 containerd 子进程，没有独立 containerd unit。启动 mount 检查作为强依赖，禁止写入 tmpfs 替代挂载。服务状态写到 `/run/piwork/boot.json`，仅含阶段、成功状态和安全错误。

必要镜像的离线 archive 随 RootFS 交付，首次用 Guest Docker 加载；后续按实际 image ID 检查，不因旧 marker 存在就跳过，也不每次重复加载。Piwork 在 Guest 的默认 Engine Unix socket 上直接运行，不再包一层 Core Docker 容器。

**取舍：** 精简自编 init 可以减少镜像体积，但可靠停止服务和挂载的成本高；首个可用 Demo 使用现成 init，之后再考虑体积优化。

### 3. QEMU 参数与 Guest 控制

先用当前 Host QEMU 完成可运行开发阶段，再将固定版本 QEMU 打入最终包。默认 2 vCPU、4096 MiB。QEMU 10 的 microvm 可能具有 PCIe/ACPI 扩展，显式关闭 PCIe 与 ACPI；所有 virtio 设备使用 `*-device` MMIO 型号。

以下模板的 microvm/KVM 和端口传递均已真实启动验证；其中 `<PORT>` 默认值为 7171，本次最终 ELF 已依次验证 8080、8081、默认 7171 和 80。完整展开参数随对应版本验收附件交付；实际 argv、kernel 参数和 QEMU/KVM 查询结果见 `evidence/ports/proof-<PORT>.json`：

```text
<qemu-system-x86_64>
  -M microvm,pcie=off,acpi=off,auto-kernel-cmdline=on
  -accel kvm,kernel-irqchip=on -cpu host -smp 2 -m 4096
  -nodefaults -no-user-config -display none -monitor none
  -L <bundle/qemu-data> -bios <bundle/qemu-data/qboot.rom>
  -kernel <bundle/kernel> -initrd <bundle/initramfs>
  -append "console=ttyS0 panic=1 reboot=t root=/dev/vda ro piwork.host_port=<PORT>"
  -drive if=none,id=root,file=<bundle/rootfs.ext4>,format=raw,readonly=on
  -device virtio-blk-device,drive=root
  -drive if=none,id=state,file=<installation/disks/state.qcow2>,format=qcow2,cache=none
  -device virtio-blk-device,drive=state
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:<PORT>-:7171,<64条Service hostfwd>
  -device virtio-net-device,netdev=net0
  -fsdev local,id=files,path=<host-data>,security_model=mapped-xattr
  -device virtio-9p-device,fsdev=files,mount_tag=piwork-data
  -chardev socket,id=qga,path=<run/qga.sock>,server=on,wait=off
  -device virtio-serial-device
  -device virtserialport,chardev=qga,name=org.qemu.guest_agent.0
  -qmp unix:<run/qmp.sock>,server=on,wait=off
  -serial <filtered-serial-transport>
```

machine/kernel 的 MMIO cmdline discovery 和根设备名必须实际验证；不依赖 PCI/磁盘自动选择。构建时把所需 microvm BIOS 的真实文件名/内容登记到 bundle manifest。所有路径经 argv 传递且正确编码 QEMU keyval 中的逗号等字符，不拼 shell 命令。串口由 launcher 接收并过滤后落盘，不能让 QEMU 直接把未处理的 Core stdout 写入日志。

使用现成 qemu-guest-agent，经私有 Unix socket/virtio-serial 获取启动状态并执行关机；QMP 用于查询 KVM 状态、设备树和进程收尾。二者仅在本安装私有运行目录，没有管理 TCP 端口。这是标准 Guest 管理组件，不设计新的 Host Infra Daemon。固件使用固定 QEMU 源码包中的 qboot.rom；SeaBIOS 在本环境的第二个 MMIO 块设备中断上无法可靠启动。不依赖 ACPI `system_powerdown` 在关闭 ACPI 的机型上完成关机。

### 4. NAT 双层网络与现有 Service 网关

QEMU user 网络为 Guest DHCP 提供地址、DNS 和路由；Guest 中 Docker 继续建立 Work bridge/veth/NAT，验证两层 NAT 的 DNS、HTTPS、MTU 与持续连接。不创建 Host bridge/TAP，不访问 Host Docker socket，不转发 Guest 7172。

`--port PORT` 只选择 Host WebUI/Core 的入口，默认 7171，固定监听 `127.0.0.1`。launcher 在 KVM 检查、资源提取或用户数据写入之前校验它是 1–65535 的整数，并排除固定 Service 范围 17891–17954；0、负数、越界、非数字或缺值明确失败。合法端口若被占用或当前用户无权绑定，也明确失败，不提升权限、不自动选择替代值。Host 端口可以与 Guest listener 不同，Guest Core 和 Agent 内部端口始终保持原值。

launcher 使用同一个已校验的端口值生成 QEMU 主入口 hostfwd、公开 origin、Host `/healthz` 与 `/readyz?profile=docker-delivery` 探针、私有首次设置链接的 origin 校验和访问地址输出，不再检查或探测未选用的 Host 7171。端口经非秘密 kernel cmdline 项 `piwork.host_port=<PORT>` 传给 Guest helper；helper 从 `/proc/cmdline` 读取并校验，参数缺省时使用 7171 以保留原开发启动方式，显式非法值则报告启动失败，不静默回退。端口只属于本次运行配置，不写入安装关联键、不改变数据盘身份或锁。

公开 origin 使用浏览器规范形式：HTTP 端口 80 的 origin 为 `http://127.0.0.1`，省略默认端口，避免浏览器自动规范化后被既有严格 Host/Origin 校验拒绝；hostfwd 和 kernel 参数仍显式使用 80。其余端口保留 `:<PORT>`。该规则同时用于 Guest 公开 origin、Host 探针、首次设置链接及输出，并增加真实浏览器的 80 端口回归。

Guest 启动统一入口的基本参数为：

```text
piwork-serve serve
  --listen 0.0.0.0:7171
  --public-origin http://127.0.0.1:<PORT>
  --data-dir /var/lib/piwork/core
  --service-ports 17891-17954
  --no-open
```

`<PORT>` 来自上述 kernel 参数，默认 7171。Guest 自己的 `127.0.0.1:7171` 对应同一 Core；托管工作台和管理界面的内部客户端通过现有进程内 `HandlerTransport` 调用 Core handler，不通过公开 origin 的 Host 端口建立 Guest TCP 连接，因此无需修改 Piwork Core 或新增 Guest listener。Service listener 在 Guest `0.0.0.0` 接收 SLIRP 入站，生成的浏览器链接仍使用 Host 回环地址和原 Service 端口，主入口来源校验及返回工作台的链接使用新的公开 origin。Agent 的 `piwork-core:host-gateway`/7172 仍由 Guest Docker/内部 mTLS 处理，不使用 Host 的回环地址当 Agent 上游。

启动前对所选主入口和全部 64 个 Service TCP 端口逐个试绑定，并检查任何包含回环的 wildcard 冲突；检查后与 QEMU bind 之间的竞争由 QEMU 错误确认，清理半启动进程。不能静默省略一个 Service 端口；仅改变主入口无法避开 Service 范围的占用，也不提供多 VM 并行运行能力。e2e 必须从实际浏览器取得受授权入口后验证 HTTP、WebSocket 和 SSE，并验证未授权/撤权行为；不对 Service 容器添加 Docker published ports。

正常停止后更换 `--port` 仍使用原 data-dir 关联的持久盘、安装、账号及 Work/Service 数据。浏览器 origin 随端口改变，原有基于 origin 的 Cookie/会话边界继续生效；用户在新入口重新登录并重新取得 Service 授权，不重复 QuickStart、不复制旧会话授权。更换主入口不绕过现有目录/磁盘锁。

### 5. ext4 为完整状态，9P 为明确的普通文件子范围

默认布局：

```text
~/.local/share/piwork-microvm/
  data/works/<installation-id>/<work-id>/    # 直接共享的普通文件
  disks/state.qcow2                          # 完整持久状态的 ext4 盘
  logs/<run-id>.log                         # 已脱敏日志
  installation.json                         # 安装与磁盘关联，非秘密
```

运行时 socket/首次设置入口放当前用户的私有 runtime 目录；只读包缓存使用 XDG cache 下的内容 hash 路径。`--data-dir DIR` 只选择直接共享根；其确定性关联状态放默认 state 根的 `installations/<canonical-directory-hash>/` 下，内含 `disks/`、`logs/`、关联元数据和锁。启动时打印这两个位置。相同参数始终复用原盘，数据目录 inode 锁与 QEMU 块设备锁共同防止路径别名导致多写者；不把自定义 data-dir 的兄弟目录无条件征用为 disks/logs。目录重定位需要保存原磁盘及安装关联，不由路径猜测自动迁移。

| 数据 | Guest/Work 位置 | backing | Host 能否直接编辑 |
| --- | --- | --- | --- |
| Core DB、账号、模型配置/secret、安装身份、context/package/snapshot 状态 | `/var/lib/piwork/core` | state ext4 | 否；停止后与整盘备份 |
| Docker images/layers/元数据、named volumes、containerd 持久内容 | `/mnt/state/docker`、`/mnt/state/containerd` | state ext4 | 否 |
| Work private：历史/Memory/联合事务状态 | `/var/data` 的既有 private 卷 | state ext4 | 否；不暴露给 Service |
| 普通 workspace 和 Service 的声明持久数据/业务 SQLite | `/var/data/workspace`，共享子目录除外 | 既有 workspace 卷，state ext4 | 否；经 Files/应用访问 |
| 普通共享文件 | Host data 对应目录 → Guest `/var/lib/piwork/host-data` → 当前 Work `workspace/shared/` | 9P，`cache=none`，`9p2000.L` | 是 |

选定**ext4 workspace + 嵌套普通文件共享子目录**，不把整个 workspace 放到 9P；这样 Service 默认业务数据库仍落 ext4。所有“用户数据直接映射”说明必须限定到 `shared/`，其余明确为镜像内数据。9P 的 SQLite/WAL/锁测试是能力与限制证据，测试通过也不把生产数据库迁到 9P，失败不影响保守布局选择。实际 9P WAL 返回 SQLITE_IOERR_SHMMAP，ext4 WAL/中断恢复通过。9P 不支持 rename flags；普通文件用原子 link/unlink 保持不覆盖发布，要求不覆盖的目录移动安全失败。9P statfs 返回 Host backing 类型，实际挂载校验使用 statx mount ID + mountinfo。

上游当前没有此共享能力，需要一处默认关闭的 Guest 存储适配，随本地构建补丁交付：

- 增加仅安装者设置的 workspace shared root 选项，传入固定 Guest 路径；普通上游运行默认关闭。路径不来自 Service/API 请求，不开放任意 bind 权限。
- 保持现有 local named workspace 卷、名字、标签和 private 卷。卷创建/恢复时，在任何 Agent、file-helper、snapshot-helper 或 Service 使用前，把该 Work 唯一的 9P 子树 bind 到 workspace backing 的 `shared/`；按实际 volume Mountpoint 与安装/Work 标签校验，不能从用户字符串拼任意路径。无需第三卷或常驻同步/监听 daemon。
- Guest 初始挂载和 Core 卷准备均在适当 mount namespace 中执行，确保 Docker/containerd 的挂载能看到子挂载；用真实容器检查递归挂载传播。保留只读 grant 对子挂载的只读效果，不能因递归 bind 让只读 Service 获得写权限。
- 处理首次卷 image copy-up、UID/GID 10001、Guest/Host 新建文件的权限及 mapped-xattr；包内 QEMU 的专用补丁仅将没有 virtfs 属性、属于启动用户的 Host 文件呈现为 UID/GID 10001，已有虚拟属主保持不变；不能只让 Guest root 通过测试。Host 文件系统不支持所需 xattr 时明确失败，不自动切到不可靠安全模式或递归 chown 用户目录。
- 已有 `shared/` 非空内容不能直接被新挂载遮住。对导入/恢复的普通文件以有归属的暂存/提交记录接入共享树；不支持或无法确认时明确失败并保留原字节。迁移暂存原目录保留在同一 volume mount 内，避免跨 Core bind mount rename 的 EXDEV；只有共享副本持久提交并完成挂载后才删除该暂存。冷快照仍捕获两卷完整用户树，导入后新 Work 取得独立共享目录，不能复用来源 Work 的 Host 路径。
- 普通 Stop/Service 删除保留共享数据；只有既有授权 purge 确认后才删除准确归属的 Host 子树。删除卷前确认无消费者并卸载子挂载，卷删除失败不得错误清除 Host 文件。

这处适配是实现必做工作，不能用空的 9P 探测目录或手工镜像内复制替代。如果真实运行揭示适配违反既有权限/快照约束，应修复后继续验收，不把共享项记为通过。

**取舍：** 整个 Core/所有 Docker volumes 都放 9P 会把 WAL/Memory/Service DB 和 overlayfs 置于未经证明的文件系统；只挂一个无人使用的 exchange 目录不满足 Work 用户文件共享；Host 同时挂载运行中的 ext4 镜像有损坏风险。选择小范围共享接入，承担少量卷准备/清理适配和真实兼容测试成本。

### 6. 启动就绪与首次设置证明交付

Host 状态机为 `preflight → assets → booting → storage → network → docker → images → web-available → setup-required/runtime-preparing → runtime-ready`。探针并行检查 QEMU 退出、Guest 阶段、Host `/healthz` 和引导静态资源。启动阶段设有界 deadline；未配置时允许 `setup-required` 并保持 foreground 进程运行，不循环等待永远不能自行成功的完整 ready。已有配置则继续读取完整交付 readiness 并报告具体准备状态，超时明确报告而不隐藏到固定 sleep。

Core 在空安装 stdout 输出 `First-time setup: <带证明链接>`，不能直接进 journal/串口日志。Guest 使用服务包装器接收 stdout/stderr，将该行只写到 `/run/piwork/setup.url`（0600），其他允许的安全记录才进入日志。Host 通过私有 Guest agent 通道读入内存，生成私有 runtime 目录内 0600 的一次性跳转 HTML；终端只输出普通 URL 与本机文件路径，不输出证明。可选浏览器打开器打开该本地入口；无打开器时用户可手动打开该文件进入现有 `/setup#setup=...`。HTML 禁止缓存/引用外传，不创建新产品设置页面；过期可经私有通道调用现有 operator `setup link` 刷新，不在日志中记录其结果。关闭/初始化完成后清理临时授权文件，持久数据中不保存票据。

launcher 记录阶段、时长、QEMU 安全 argv、退出状态和路径，不记录环境全集、HTTP Authorization/Cookie、原始 QGA 秘密响应或模型请求体。模拟秘密的回归检查覆盖串口、Guest 日志、Host 日志和所属验收附件。

### 7. 独占与正常关闭

获得安装/共享根的非阻塞排他锁后才准备可写状态；锁采用真实目录/文件身份，不仅检查 PID 文件。QEMU 使用启用写锁的 qcow2 state block backend；同时验证锁 FD 的生命周期。父 launcher 被 SIGKILL 而 QEMU 留存时，后续进程也必须被仍存活的磁盘写锁阻止，不能删除所谓“旧锁”后启动同盘 VM。启动竞争、QEMU 提前退出和资源提取失败均保留用户盘，清理本次临时资源。

正常关机使用 QGA `guest-shutdown` 的 `reboot` 模式；按 QEMU microvm 官方关闭约定，kernel `reboot=t` 与 QEMU `-no-reboot` 在有序收尾后以 triple fault 退出 VM。随后，Guest service ordering 先终止 Piwork，`TimeoutStopSec` 不低于 60 秒，覆盖 Core 的 45 秒 drain；再停 Docker/containerd，卸载 workspace 子挂载、9P 和 ext4，sync 后正常 reboot/triple fault。launcher 总关闭预算初始 120 秒，等待 Guest/QMP 事件与 QEMU 退出；磁盘和 QEMU 真正关闭后释放锁。QGA 无响应或服务不能 drain 时先记录具体失败，再采用有界 QMP quit/进程终止策略，以非零返回和“异常关机”报告，不宣称 clean shutdown。microvm 的 ACPI 关闭命令不是关机后备成功依据。

真实暂停测试发现，未完成的阶段探针可能在收到信号后额外消耗 socket/read-close 超时。
QGA Client 因此在 context 取消时立即关闭当前 socket，文件关闭和 HTTP 探针也服从
同一 context；进入协调关机前再次检查取消。回归覆盖阻塞 read 与关闭请求，不把
控制 I/O 的额外等待排除在实际信号到退出的计时之外。

### 8. 单 ELF 资源包和 QEMU 依赖闭包

Host launcher 使用 Go、CGO disabled。最终 ELF 采用 Go 程序加内附压缩资源包、索引/长度/manifest hash 尾部的单文件格式；Linux 仍直接执行其 ELF 前部。这样避免巨大 Guest/镜像经 `go:embed` 编译进 rodata 带来的链接与体积限制，同时保留一个分发文件。压缩包按内容清单固定排序、权限/时间和 hash；记录源输入身份，不在尚未重复验证时承诺整盘构建逐字节一致。

资源提取按包内容 hash 使用 staging 目录、独占锁、路径边界检查和逐文件 hash，全部验证后 rename 发布。缓存只保存不可变 kernel/rootfs/QEMU/库/固件；可写磁盘永不位于 cache。清除缓存只会重新提取，不会重建安装。`--help` 在解析 payload/创建目录前返回。

最终 QEMU 来自固定构建容器内的 headless x86-64 构建/固定软件包，包含 KVM、microvm、9P、SLIRP、MMIO 及控制接口。若是动态 ELF，把 loader、全部 DT_NEEDED 依赖、运行时 dlopen 模块和必要数据/BIOS 一起冻结，通过包内 loader 与显式 library path/data path 启动，不仅复制 `/usr/bin/qemu-system-x86_64`。构建清单包含源码/许可证；验证实际文件访问，防止偷偷依赖原 Host 的库或固件。包内程序通过 `/proc/self/exe` 定位自身资源，不要求从源码目录启动。

**取舍：** 静态 QEMU 可以减少共享库寻址问题，但不能以卡住静态链接为由跳过可运行 Guest；先做已验证的动态依赖闭包，再以干净 KVM Host 验证，静态链接不是本 Demo 的独立目标。

### 9. 真实验收及可重跑驱动

已提供 `make guest`、`make boot-dev`、`make piwork-microvm`、`make acceptance-microvm` 实现入口。构建及验收命令为：

```sh
make guest
make boot-dev                 # 开发阶段：明确使用 Host QEMU
make piwork-microvm           # 构建 dist/piwork-microvm，包含 QEMU
./dist/piwork-microvm
./dist/piwork-microvm --data-dir /absolute/path/to/data
make acceptance-microvm
```

本次端口增量已实现并重建单文件，以下命令可直接使用；对应版本的真实验收见 [acceptance.md](acceptance.md)，原默认端口基线记录保留其原版本身份：

```sh
./dist/piwork-microvm --port 8080
./dist/piwork-microvm --data-dir /absolute/path/to/data --port 8080
```

端口增量验收同时覆盖默认 7171 和自定义 8080。用受控测试监听器占用 Host 7171，在 Service 范围可用时以 8080 启动最终 ELF，核实真实 hostfwd 和 kernel 参数、公开 origin、探针、私有首次设置链接以及浏览器 QuickStart、管理界面、真实 Work/Files 和受保护 Service HTTP/WebSocket/SSE；原占用进程保持运行。正常停止后对相同 data-dir 改用另一个合法端口（例如 8081），核对原管理员、配置、Work/Service 身份、文件及数据库计数，重新登录并取得授权后继续访问，不重新创建安装。针对所选主入口与任意 Service 端口分别验证冲突错误，并验证非法参数在准备资源/数据前失败。默认与自定义配置均须保留真实 KVM 证据，不能只做参数单元测试。

验收使用独立 Host data/disks 与合成账号，所有容器位于 Guest 的独立 Engine，不清理 Host 其他安装。先在真实 KVM Guest 完成完整现有 QuickStart，再创建真实 Work，经现有受认证接口/Service MCP 部署一个可返回 HTTP、WebSocket/SSE 和持久计数/SQLite 数据的确定性 Service；不需要模型生成代码才能测试网络。Files 检查普通 ext4 workspace 与 9P shared 两个范围，Agent/Service 真实读取 Files 写入内容。

缺真实 AI Key 时，在明确标识的模型夹具下验证现有 SDK/Agent/Service 链路，但生产产物继续携带 production Agent；真实供应商调用单列未验证。若有用户提供的有效 Key，仅用于显式测试，不读出或公开已有安装秘密。真实 AI Happy Path 至少验证一条 SDK Run 与文件/Service 能力，不能让夹具结果冒充供应商成功。

在 Work 运行时发 Ctrl+C，验证正常停止；二次启动检查原管理员/模型引用、Work ID/配置、Session/Memory、Files 字节、Service 定义和业务计数/SQLite。再以正常停机后的原盘重建临时 RootFS/缓存验证复用。记录实际恢复的运行意图，既有契约不要求自动运行的状态通过原 Start 恢复，不能擅自改变语义。

必要失败场景覆盖缺 KVM/无权限、所选主入口/任一 Service 端口冲突、非法或与 Service 范围重叠的主入口参数、损坏 payload/cache、缺失/错误持久盘、9P/xattr/权限故障、重复启动、launcher 异常退出后磁盘锁、Guest 提前退出、关机超时。单元测试只用于参数、锁、提取边界和状态机等有实际故障价值的逻辑，不能替代 KVM 集成。

原始日志/截图落忽略的 `dist/acceptance/`；脱敏验收结论和必要可审阅证据归本 change 附件。最终报告包括 ELF hash、固定输入、实际 QEMU argv、网络/存储表、逐项结果和未验证原因。若没有第二个干净 KVM Host，当前 Host 上可做受控依赖隔离检查，但该项仍记录未验证；普通容器不冒充干净 Host KVM 验收。

## Risks / Trade-offs

- [9P 缓存、mmap、锁、fsync 或 xattr 不可靠] → 默认所有数据库/运行时在 ext4；普通共享文件用保守缓存策略和真实双向用例验证，明确支持的 Host 文件系统，不凭探测文件宣布共享完成。
- [共享子挂载对 UID、只读权限、快照或 purge 有影响] → 适配默认关闭，仅在 Guest 构建启用；覆盖恢复、Host 新建文件、两卷导入导出、引用检查及递归只读，拒绝隐藏既有数据。
- [QEMU 10 microvm 设备发现/固件行为与示例不同] → 显式 pcie/acpi 设置，kernel cmdline 与设备树/启动日志实际确认，在当前 KVM 上先验证，再冻结参数与包内固件。
- [上游脚本历史默认镜像或 Node/Engine 版本不匹配] → 固定构建 Node 24/Go 1.25.5、Guest Engine 28+；嵌入本地 candidate 依赖并检查真实 image ID；Host Engine 26 不当 Guest 验收依据。
- [单文件体积和首次解包磁盘压力] → 压缩资源、稀疏数据盘和内容缓存；启动前检查空间，使用内附 payload 避免 Go 巨型 rodata，后续启动不重复构建/导入。
- [launcher 死亡留下写盘 QEMU 或强制终止损坏数据] → 使用 Guest 协调关闭和 QEMU 块设备锁，异常关闭如实报告，下一启动检查文件系统/数据库；不自动重置或格式化。
- [自包含包依赖开发机的动态库/固件] → 记录完整依赖闭包与实际运行文件访问，使用独立 KVM Host 复验；未做则保留未验证状态。

## Migration Plan

本 Demo 从独立空安装开始，不迁移用户现有 Piwork 安装，不访问原 Docker volumes 或凭证。先完成可运行 Guest 和外部 QEMU 开发阶段，再加入网络/共享适配与持久恢复，最后打包并用最终 ELF 重跑验收。

同版 RootFS/cache 可替换，原 ext4 盘和 data 树保持关联。任何变更涉及 Core/Work 格式时遵守上游兼容检查，不自动升级或回滚现有数据；回退前正常停止并备份整盘、共享树和关联元数据，不能在已变更的盘上盲目使用旧程序。最初只交付本机构建/启动命令，不上传、不发布 Release。

实现补充：真实 SDK 夹具暴露上游会话历史契约拒绝 Responses SDK 组合 toolCallId（例如 call_id|fc_id）。仅放宽 SessionContentBlock 的 opaque toolCallId 字符范围以保留该分隔符，资源 ID/路径规则和 Work/Service 语义不变；Go 契约回归覆盖接受组合 ID、拒绝控制字符及保持资源 ID 规则。

9P 冷快照实测发现上游 snapshottree 对描述符包装的临时名称调用 ReadDir；DT_UNKNOWN 下 Go 会相对该名称 lstat 并跳过条目。改为 Readdirnames，后续 inode 类型/身份仍由原来的 fstatat 检查。该修复保留完整共享树，不更改快照格式。

严格冷恢复还发现 Linux 6.6 的 9P superblock 沿用一秒时间精度，导致协议本身支持的纳秒 mtime 在 setattr 前被截断。Guest kernel 补丁仅为 9P2000.L 设置 `s_time_gran=1`；实际验证纳秒 round-trip 后重新执行完整导入，保持原有元数据一致性校验。授权 purge 在卸载前关闭自己的探测目录描述符，避免自身打开的 FD 造成 EBUSY；被引用卷仍按既有检查拒绝清除。
