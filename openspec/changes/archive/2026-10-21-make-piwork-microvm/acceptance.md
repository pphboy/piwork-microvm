# Piwork MicroVM 实际交付与验收

验收日期：2026-10-20（Asia/Shanghai）。当前最终产物为仓库根目录的
`dist/piwork-microvm`，392,429,214 字节（约 374 MiB），Linux x86-64 ELF。
SHA256：`fbfb7ba3bfb231d94dee91a00e1b23041a669481c74565358b7b06961bef2ca1`。
它内含 QEMU、动态 loader/运行库、qboot、kernel/initramfs、RootFS、Docker、
现有统一 Piwork Server/WebUI 和生产 Agent/Helper 镜像。默认启动没有 Host QEMU
或 Host Docker 依赖；构建和自动验收需要下述开发工具。

## 本次端口增量验收

当前 ELF 支持 `--port PORT`，默认 7171。选择其他主入口时不检查或占用 Host 7171；
Guest Core 始终监听 7171，Guest 公开 origin、Host 探针、私有首次设置链接及输出地址
使用所选端口。参数仅接受 1–65535 的整数，排除 Service 范围 17891–17954；不自动
换端口或提升权限。正常停止后更换端口仍复用原安装，浏览器需在新 origin 重新登录。

最终 ELF 的真实 KVM 验收运行在
`dist/acceptance-runs/ports-20261020T002114-4031035/`。
四次启动使用相同的上述 SHA256、一个 VM 和同一组持久数据，按下列顺序执行。
8080、8081 和 80 测试中，Host 7171 由受控独立 HTTP 监听器占用；其响应始终保持，
Launcher 未将其当作 Piwork 探针。用户原 Host namespace 的 Piwork 保持运行。

| Host 端口 | 浏览器公开 origin | Work/Service SQLite 计数 | 结果 |
| --- | --- | --- | --- |
| 8080 | `http://127.0.0.1:8080` | 0 → 1 | 私有首次授权、管理员、QuickStart、真实 Work/Files/Service 通过 |
| 8081 | `http://127.0.0.1:8081` | 1 → 2 | 原账号、模型配置、Work/Service、Session、ext4/9P 文件恢复后通过 |
| 默认 7171（未传 `--port`） | `http://127.0.0.1:7171` | 2 → 3 | 默认行为及同一安装恢复通过 |
| 80 | `http://127.0.0.1` | 3 → 4 | 浏览器默认端口规范化及同一安装恢复通过 |

每次均实际通过浏览器登录、现有管理/工作台、真实生产 Agent Work、Files 编辑、
Service HTTP、匿名拒绝、双向 WebSocket、SSE 和 Work DNS/HTTPS。每次 QMP 均确认
microvm/KVM、无 PCI；QEMU 拥有精确的 65 个 IPv4 回环监听，其运行库全部来自包内
缓存。Guest 实际进程参数确认 `--listen 0.0.0.0:7171` 和对应的 `--public-origin`，
公开 URL/健康及完整就绪探针均成功。四次停止均退出 0 并记录 `Guest stopped cleanly`。

Core/Work/Service 的实际数据库均在 ext4 且完整性检查为 ok，原两个 named volumes
身份保持，Service 无 Docker published ports。首次还验证 Host 与 Work Files 对
9P 共享文件和嵌套目录的双向创建、修改、读取和删除。另一网络 namespace 的第二个
Launcher 即使改用 8082，也被同一安装锁拒绝，未启动第二个可写 VM。

最终 ELF 还通过 8 组非法端口输入在无 KVM 环境中的提前失败检查，未创建数据或缓存；
8080 冲突、Service 17954 冲突和低端口绑定权限不足均明确失败，不影响原占用程序。
HTTP 80 的成功测试在允许普通用户绑定该端口的隔离 namespace 中执行；权限失败测试
另以 `ip_unprivileged_port_start=1024`、普通用户和无 capabilities 验证。

脱敏证据见 [端口验收日志](evidence/ports/acceptance.log)、
[交付身份](evidence/ports/delivery.json)、
[8080 实际 QEMU/Guest/存储证据](evidence/ports/proof-8080.json)、
[8081](evidence/ports/proof-8081.json)、[默认入口](evidence/ports/proof-7171.json)、
[80](evidence/ports/proof-80.json) 和 [失败路径](evidence/ports/port-preflight.json)。
密码、模型 Key 和首次设置 proof 未进入这些记录及检查过的 Host/Guest 日志；私有测试
凭证只留在忽略的运行目录。四次 VM 均已停止，原数据保留。

本次实际增量构建与复跑命令：

```sh
go test ./...
python3 scripts/rootfs.py       # 复用锁定版本的既有 Piwork、镜像、kernel 和 QEMU
python3 scripts/bundle.py
make acceptance-ports
./dist/piwork-microvm --port 8080
```

完整重建入口仍为 `make piwork-microvm`。本次未修改 Piwork Core、UI 或生产镜像，
真实供应商模型推理和第二台独立干净 KVM Host 仍未验证。下文基线的冷快照、权限隔离、
坏盘/缓存和故障注入记录属于原 aa5f 版本，不冒充新版本重复执行的结果。

## 构建、启动与交付位置

在本仓库根目录执行：

```sh
make piwork-microvm
# 本次实际使用的本地固定 revision 输入；不读取该 clone 的未提交文件：
make piwork-microvm PIWORK_SOURCE=/home/p/Projects/piwork
make guest PIWORK_SOURCE=/home/p/Projects/piwork
make qemu
./dist/piwork-microvm --help
./dist/piwork-microvm
./dist/piwork-microvm --data-dir /absolute/path/to/data --cpus 2 --memory 4096
./dist/piwork-microvm --port 8080
```

构建依赖 Docker、Go 1.25.5、Git、Python 3、Make、Bash、curl、qemu-img 和网络。
`build.lock.json` 锁定 Piwork `efce08c228c12f10d18a968b69c3398bb0e783e1`、
Node 24.21、Docker 28.5.2、Linux 6.6.159、QEMU 10.0.8、基础 OCI digest、
Debian snapshot 和下载 SHA256。`scripts/source.py` 获取并检查固定 revision，
`guest/patches/` 的完整补丁只应用于 `dist/source/piwork`，相邻工作区保持原样。
`scripts/kernel.sh`、`scripts/rootfs.py`、`scripts/qemu.sh` 和
`scripts/bundle.py` 给出可重建配方。文件系统 UUID/创建时间可变，不承诺 ELF
字节级重现。构建无镜像推送、Release 发布或远程 Git 写入。

| 位置 | 交付内容 |
| --- | --- |
| `dist/piwork-microvm`、`.sha256` | 可分发单 ELF 及校验和 |
| `dist/guest/` | kernel/config、initramfs、rootfs.ext4、state.qcow2 模板、qboot、生产镜像包 |
| `dist/bundle-manifest.json` | 包内每个资源的路径、大小、权限、SHA256 |
| `dist/qemu/licenses/`、包内 `provenance/` | 许可证、依赖版本、固定源码身份及本地补丁 |
| 本仓库 `cmd/`、`internal/`、`guest/`、`scripts/`、`fixtures/` | Launcher、Guest 配方、完整源码补丁和真实验收驱动 |

开发阶段还实际运行过显式 Host QEMU 模式：
`make boot-dev`；该阶段依赖 `/usr/bin/qemu-system-x86_64`，不能作为自包含分发。
开发阶段日志保存在 `dist/isolated-state/piwork-microvm/logs/`，例如
`20261019T180352.064879591.log`。最终验收使用上面的内含资源 ELF。

源码改动集中在以下范围，没有产品 UI 重设计或新的网络管理 daemon：

- `cmd/piwork-microvm`、`internal/launcher`、`internal/qemu`、`internal/bundle`：前台 Launcher、KVM/QEMU、就绪/关机、锁和单文件提取。
- `cmd/piwork-guest`、`guest/rootfs`：systemd 初始化、持久挂载、镜像身份校验与现有统一 Piwork 入口的日志包装。
- `guest/patches/piwork-workspace-sharing.patch`：默认关闭的共享根选项与原两卷接入/导入/清理；9P 普通文件原子创建兼容；snapshot 描述符目录枚举；SDK Responses 复合 toolCallId 历史契约兼容。Work/Service 资源身份和授权语义保留。
- `guest/kernel/dotl-nanoseconds.patch`、`guest/qemu/host-owner.patch`：9P2000.L 纳秒 metadata 与 Host 创建文件的 UID/GID 兼容。
- `scripts/acceptance*`、`fixtures/`：真实 KVM、浏览器、存储、SDK 协议夹具和故障注入；夹具不作为生产 Agent 镜像替身。

## 本次真实环境与范围

Host 是 Linux x86-64 / WSL kernel 6.18.54.1，真实 `/dev/kvm` API 12，
成功创建 KVM VM。Guest 是自行构建的 Linux 6.6.159、systemd、Docker 28.5.2、
overlay2/cgroup v2。默认 2 vCPU、4096 MiB；一次只运行一个 VM。

Host 原网络 namespace 的 7171 已被用户现有 Piwork 占用，未停止它。
因此验收在同一 Host 的独立网络 namespace 中执行；真实 Host Chromium 也进入
该 namespace 访问 `127.0.0.1`。Docker 仅创建这个测试隔离环境及空 chroot，
通过真实 `/dev/kvm` 启动 QEMU；Guest 内的 Docker、Agent 和 Service 都在 KVM VM
里，未用 Host 容器替代 Guest。

空 chroot 只复制最终 ELF，提供 `/proc`、必要 `/dev`、DNS 文件和空数据目录，
以普通 UID 1000、`PATH=/nonexistent` 启动；其中没有预装 QEMU、Docker、libc、Go
或 Node。QEMU `/proc/<pid>/maps` 中实际加载的 `.so` 全部来自包内缓存。
浏览器和探测工具在 chroot 外执行。此项是当前 Host 的运行依赖隔离验证，
**没有取得第二台独立干净 KVM Host，跨 Host 分发复验仍未验证**。

## 实际网络与 QEMU 参数

QEMU 10.0.8 使用 `-M microvm,pcie=off,acpi=off,auto-kernel-cmdline=on`、
`-accel kvm,kernel-irqchip=on`、`-cpu host`，全部磁盘、网卡、9P 和串口均为
virtio-mmio 设备。QMP 核对 `query-kvm` 的 enabled/present、machine 类型和
空 `query-pci`。实际完整 argv 从 Launcher 及运行中进程提取；原默认端口基线保存在
`evidence/qemu-argv.json`，本次端口增量分别保存在 `evidence/ports/proof-<PORT>.json`
的 `qemuArgv`，包含全部 65 条 hostfwd，而非参数示意。

| Host loopback | Guest | 验证用途 |
| --- | --- | --- |
| `127.0.0.1:<PORT>`（默认 7171） | `7171` | 统一 WebUI、登录、QuickStart、Core/Files |
| `127.0.0.1:17891–17954` | 相同端口 | 受既有授权保护的 Service HTTP/WS/SSE |

网络使用 QEMU SLIRP user NAT，Guest systemd-networkd DHCP/DNS；Work 使用
Guest Docker bridge/NAT。Launcher/QEMU 不创建 Host TAP/bridge；验收隔离容器
借用当前 Host 已有 Docker 网络，此依赖仅属于测试工具。Guest 7172 Agent 控制入口不转发；
Service 不使用 Docker published ports。仅监听 Host 回环地址。完整 origin 为
`http://127.0.0.1:<PORT>`，由 `--port` 选择；HTTP 80 的规范 origin 为
`http://127.0.0.1`。Service 使用原 17891–17954 独立端口及现有 Cookie/授权机制。
QEMU `-append` 的 `piwork.host_port=<PORT>` 传给 Guest helper，Guest Core 继续
监听 `0.0.0.0:7171`，仅 `--public-origin` 随 Host 入口变化。

microvm 使用包内 `qboot.rom`；SeaBIOS 曾导致第二个 MMIO 磁盘中断未正确启用，
实测后采用 qboot。正常关闭先停 Piwork、Docker 及其托管 containerd，sync 后
由 QGA 请求 Guest reboot；kernel `reboot=t` 配合 QEMU `-no-reboot` 在有序卸载后
退出。无 ACPI poweroff 的机器不能把仅 halt 当作 QEMU 已退出。

## 实际存储与备份

| 数据 | 实际 backing | Host 能否直接读取/编辑 |
| --- | --- | --- |
| Core 配置、管理员、模型配置/凭证、安装身份和快照状态 | `state.qcow2` 内 ext4，Guest `/var/lib/piwork/core` | 否，随整盘保存 |
| Docker/containerd、原有两只 local named volumes | 同一 ext4 盘 | 否 |
| Work private、Session/Memory/SDK 历史 | private named volume / ext4 | 否 |
| Work 普通 workspace、Service SQLite/计数 | workspace named volume / ext4 | 否 |
| 每 Work 的 `workspace/shared/` 普通文件 | Host `data/works/<installation>/<work>/`，9P bind 到既有 workspace | 是，双向可见 |

默认 state 根为 `~/.local/share/piwork-microvm/`（尊重 XDG_DATA_HOME），
包含 `data/`、`disks/`、`logs/`、`installation.json`。自定义 `--data-dir`
只选择共享文件根，关联磁盘在默认 state 根的
`installations/<canonical-directory-hash>/disks/state.qcow2`。启动时打印两者。
盘是 64 GiB 虚拟容量的稀疏 qcow2，使用 ext4，Docker data-root 不在 9P。
实查 Docker 生成的 containerd.toml，托管 containerd 的持久 root 是
`/mnt/state/docker/containerd/daemon`，临时运行 state 是
`/var/run/docker/containerd/daemon`。另外持久绑定 `/var/lib/containerd`，没有把
运行时 PID/socket 的易失状态误当成数据库持久化。

Guest 在 `/var/lib/piwork/host-data` 自动挂载 `virtio-9p-device`，
`mapped-xattr`、`9p2000.L`、`cache=none`、nodev/nosuid。每个 Work 分配独立共享
子树；普通删除保留数据，既有受授权的内部 purge 才清除已不被引用的所属树。
没有第三只 named volume、文件同步进程或新 Infra Daemon。

实测 9P 的跨进程文件锁、fsync/rename 和 SQLite DELETE 模式事务恢复通过，
但 **WAL 返回 SQLITE_IOERR_SHMMAP（5386）**。因此所有生产数据库保留 ext4，
不降低 SQLite 同步/完整性检查。9P 的文件原子防覆盖使用 link/unlink 适配；
要求防覆盖的目录 rename 会安全失败。QEMU 小补丁将 Host 启动用户创建且没有
virtfs 属主属性的文件呈现为 Work UID/GID 10001，Host 实际属主不变。

冷导入保留严格纳秒 metadata 检查：Guest kernel 小补丁启用 9P2000.L 的纳秒
时间戳精度，snapshot-helper 兼容 DT_UNKNOWN 目录枚举。非空无归属 Host 目录
会拒绝接入并保留原文件；导入 Work 使用独立 Host 目录。

先 Ctrl+C 并等待 `Guest stopped cleanly`，再同时备份：

```sh
# STATE 和 DATA 使用 Launcher 实际打印的路径；以下为默认安装示例。
state="$HOME/.local/share/piwork-microvm"
mkdir -p /path/to/backup
cp --sparse=always "$state/disks/state.qcow2" /path/to/backup/
cp "$state/installation.json" /path/to/backup/
tar --xattrs -cpf /path/to/backup/shared.tar -C "$state/data" .
```

自定义 data-dir 时同时记录原 DATA 路径及关联安装位置。已按该流程在正常停止后
保存 `dist/acceptance/backup/`。没有 Host 并发挂载运行中的 ext4。只备份 data
目录不能恢复全部 Piwork；只保留镜像也不等于用户目录直接共享。

## 原默认端口版本的完整基线测试记录

原默认端口版本（SHA256 `aa5f2d7acd062a0f428db20338d9ad0da7234fc149061fc0a8eb7e06fbd80829`）的全新安装验收运行在
`dist/acceptance-runs/20261019T193437-3908348/`；原始日志、私有测试凭证、
截图和 Work 冷导出包留在忽略的 `dist/`。可审阅的脱敏结果归入本 change 的
`evidence/` 根目录，含该版本的 `delivery.json`、`final-verification.json` 和故障结果。
这些是基线记录，不作为新端口增量已经通过的证据；新版本记录位于 `evidence/ports/`。
测试过程中发现并修复的问题保留在设计说明中；失败的早期结果不冒充通过证据。

| 项目 | 基线版本结果/证据 |
| --- | --- |
| microvm + 真 KVM、Guest Linux/Docker、无 PCI | 已通过，QMP/Guest 运行证据 |
| 真实浏览器首管理员、登录、现有 QuickStart | 已通过，浏览器日志/截图 |
| 生产 Agent Work、Files 实际读写 | 已通过，真实 Work/container 身份 |
| Guest/Work DNS、HTTPS、AI API 连通 | 已通过；无认证 OpenAI API 返回 401 |
| Service HTTP、双向 WS、SSE、SQLite | 已通过；匿名拒绝、独立来源与停 Work 后路由撤销另有断言 |
| Host ↔ Work/Files/Service 共享读写、删除、UID 10001 | 已通过；递归只读和无 grant 隔离 |
| 真实 SDK Run/Memory tools | 已通过明确标注的合成 Responses 协议夹具；未替换生产 Agent |
| SQLite backing/事务中断/完整性 | ext4 通过；9P WAL 不支持并已规避 |
| 完整冷导出/导入、不同 Work 隔离、普通删除与授权 purge | 已通过，含 Host 冲突保护、导入隔离、普通删除留存和授权 purge |
| 基线 ELF 正常停止/重启、缓存损坏/清除恢复 | 五次启动及清缓存/损坏缓存/孤儿退出后的原安装恢复均通过 |
| 同盘锁、孤儿 QEMU、权限/坏盘/端口失败 | 本轮全部通过，含移除 PID 记录/路径别名和坏盘后原盘 hash 不变 |
| Guest 提前退出、共享设备失联、关机 120 秒超时 | 全部通过，见 `evidence/fault-results.json` 和对应日志 |
| 真实供应商模型推理 | **未验证：用户没有提供有效 AI Key** |
| 第二台干净 KVM Host | **未验证：当前没有该环境** |

合成夹具只验证生产 SDK Session/Run、Memory 工具、历史契约及持久化。它不会
证明真实模型推理、真实 Key 或供应商计费链路成功，也不用于分发默认模型。

## 复跑与诊断

```sh
make test
make acceptance-microvm
# 完整运行正常停止后，再对其副本执行真实失败注入：
python3 scripts/acceptance-faults.py \
  --from-host dist/acceptance-runs/<run>/host \
  --out dist/acceptance-runs/<unique-fault-run>
openspec validate make-piwork-microvm --strict
```

自动浏览器验收需要 Host Node/Playwright + Chromium，可通过
`PIWORK_NODE_PATH`、`PIWORK_PLAYWRIGHT_MODULE` 指定。测试使用私有合成账号，
不读取用户现有配置或 API Key。每一轮使用独立数据目录，一次只启动一个 VM。
故障脚本只复制已正常停止的验收盘，不注入用户安装。

启动失败先查看 Launcher 输出的 log：包含真实 argv、串口及阶段；首次授权
proof 只写私有临时文件，不输出日志。阶段失败明确返回 storage/images 等原因。
端口冲突不会停止已有程序；当前 Host 默认 7171 已被占用，可使用 `--port 8080`
选择其他可用主入口，全部 64 个 Service 端口仍须可用。KVM 缺失/权限、磁盘丢失/
错误等检查拒绝启动，不自动初始化空替代安装。
关机失联超过总预算以非零和 unclean shutdown 报告，保留磁盘供下一次检查。

故障副本运行位置：`dist/acceptance-runs/aa5f-faults/`。Guest 提前退出、
离线镜像加载失败、断开真实 VirtIO-9P 驱动均返回阶段诊断和非零。QMP 暂停 Guest
后发 SIGTERM，实测 **120.3 秒**后以明确的 unclean shutdown 强制终止，退出 1；
重新启动后原 ext4 sentinel、Work 和 Service 均在，SIGINT 正常退出 0。主验收安装
未被故障注入修改，两组测试 VM 均已停止，全部磁盘和用户文件保留。

前一版从信号到退出曾用 132.33 秒，未达到目标，记录在
`evidence/previous-shutdown-timing.json`。已修复阶段探针的 context 取消，增加阻塞
控制 I/O 回归，并用上述 aa5f 基线 ELF 完整重跑五次启动与全部故障测试；该旧计时
不作为通过证据。故障注入和冷快照等基线全套未因本次端口增量重复执行，相关结果保留其原版本身份。

源码相关 Go 测试（app/coreapp/dockerengine/filehelper/snapshottree/contracts）全部通过，
Launcher/bundle/QMP 测试通过；`evidence/upstream-tests.log` 保存结果。核对固定输入、
三个补丁与包内 provenance 的 SHA256 一致，运行中的 QEMU 库闭包和 65 个回环监听均已核实。
相邻 Piwork 工作区仍仅有原来的未跟踪 `promo/`，没有修改或推送它。
