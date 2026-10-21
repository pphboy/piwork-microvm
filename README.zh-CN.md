# Piwork MicroVM

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) ![Platforms](https://img.shields.io/badge/platforms-Linux%20x86--64%20%7C%20Windows%2011%20x86--64-blue) [![Upstream Piwork](https://img.shields.io/badge/upstream%20Piwork-0.0.9-informational)](build.lock.json)

[English](README.md)

在一个 QEMU `microvm` Linux Guest 中运行原版 Piwork，使用 VirtIO-MMIO。每个平台交付一个自包含
可执行文件：Linux x86-64/KVM 与原生 Windows 11 Home x86-64/WHPX（从 21H2 起）。Windows 运行不依赖
WSL、Docker Desktop 或 Hyper-V Manager。

当前支持状态以已完成变更的
[tasks.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/tasks.md) 为准。该文件而非本
README，是当前支持范围的唯一事实来源。

## 目录

- [这是什么](#这是什么)
- [快速开始](#快速开始)
- [命令行参考](#命令行参考)
- [网络与访问](#网络与访问)
- [安装数据与持久化](#安装数据与持久化)
- [生命周期、停止与磁盘安全](#生命周期停止与磁盘安全)
- [日志与诊断](#日志与诊断)
- [资源缓存](#资源缓存)
- [从源码构建](#从源码构建)
- [发布](#发布)
- [验收与证据](#验收与证据)
- [范围与限制](#范围与限制)
- [许可证](#许可证)
- [相关文档](#相关文档)

## 这是什么

Piwork MicroVM 在单个 QEMU `microvm` Guest 中启动未修改的上游 Piwork，使用 VirtIO-MMIO。每个平台
得到一个自包含可执行文件（Linux ELF 或 Windows PE），其中携带内核、QEMU、Guest rootfs 与容器镜像。
启动时程序把这些内置资源解压到用户缓存并引导 Guest；启动过程不构建、不下载 Guest。不应用任何 Piwork
补丁，Server、WebUI 与生产 Agent/Helper 使用同一上游发行身份。

## 快速开始

### 运行要求

- 复制与你的平台匹配的产物，并同时保留其 `.sha256` 校验文件。
- **Linux**：当前用户须能读写 `/dev/kvm`。
- **Windows**：须启用固件虚拟化和 **Windows Hypervisor Platform（Windows 虚拟机监控程序平台）**，
  包括系统要求的重启。
- 无需新驱动、Host QEMU、Docker 或语言工具链。
- 硬件加速是硬性要求。缺少加速器会直接报错，不回退机型或 TCG。
- 安装根至少需要 **4 GiB 可用空间**，另需 **1 GiB** 用于资源解压预留。为 Work 增长留出更多空间是
  建议，不是要求。
- 默认为 2 vCPU / 4096 MiB，可通过 `--cpus`、`--memory` 调整。

### 运行

```sh
./piwork-microvm
./piwork-microvm --data-dir /absolute/path/to/installation --port 8080
./piwork-microvm --data-dir /another/installation --port 8020 --core-port 8021
./piwork-microvm --help
```

```powershell
.\piwork-microvm.exe
.\piwork-microvm.exe --data-dir 'D:\Piwork Data' --port 8080
.\piwork-microvm.exe --data-dir 'D:\Another Piwork' --port 8030 --core-port 8031
.\piwork-microvm.exe --help
```

### 首次启动

启动器输出安装根、持久盘和日志路径，随后持续报告 Guest 进度直到 Piwork 可访问：

```
Installation: /home/user/.local/share/piwork-microvm
Persistent state: /home/user/.local/share/piwork-microvm/disks/state.qcow2
Log: /home/user/.local/share/piwork-microvm/logs/20261021T074600.123456789.log
Piwork is available: http://127.0.0.1:17891
Core API: http://127.0.0.1:17871
```

除 `--no-open` 外，程序会自动打开访问地址；在 Linux 上仅在设置了 `DISPLAY` 或 `WAYLAND_DISPLAY`
时才会打开。原版 Piwork 0.0.9 直接在浏览器创建首位管理员，随后正常登录并完成 QuickStart。

## 命令行参考

| 参数 | 默认值 | 有效值 | 用途 |
| --- | --- | --- | --- |
| `--data-dir DIR` | 平台默认根目录 | 任意路径 | 完整安装根目录（元数据、磁盘、日志） |
| `--port PORT` | `17891` | 1-65535 | Host 浏览器 UI/ControlPlane 端口 |
| `--core-port PORT` | `17871` | 1-65535 | 供 CLI/backend 使用的 Host Core API 端口 |
| `--cpus N` | `2` | 1-64 | 虚拟 CPU 数 |
| `--memory MiB` | `4096` | 1024-262144 | Guest 内存（MiB） |
| `--no-open` | 关闭 | - | 不自动打开访问地址 |
| `--startup-timeout D` | `15m` | > 0 | 等待 Guest 就绪的最长时间 |
| `--help`、`-h` | - | - | 显示帮助，不触碰虚拟化与数据 |

- `--port` 与 `--core-port` 必须不同，且都须在 1-65535 范围内。
- 不接受位置参数。
- 成功和 `--help` 的退出码为 `0`；任何失败都以退出码 `1` 结束，并向 stderr 打印
  `piwork-microvm: <error>`。
- 仅开发使用：`--assets DIR` 与 `--qemu PATH` 必须成对给出，用于显式选用外部 QEMU。这不属于普通
  用户流程。

## 网络与访问

只转发两个 Host 端口，且所有 Host 监听都绑定到 `127.0.0.1`：

| 参数 | Host 默认端口 | Guest 端口 | 用途 |
| --- | --- | --- | --- |
| `--port` | 17891 | 17891 | UI、登录、管理、QuickStart 和 Service Proxy |
| `--core-port` | 17871 | 17871 | 供 CLI/backend 使用的 Core API |

浏览器 origin 跟随 `--port`，HTTP 80 端口的 origin 不带 `:80`。端口冲突会明确报错并指明被占用的
地址，且不结束其他程序。Service 通过上游 UI 同源 `/services/` 路径访问；启动器本身只转发上表两个
端口。旧的 64 端口池既不预占也不转发。

同时运行 Windows 与 Linux 版时，各自使用独立安装目录和不同的 UI/Core 端口。同一数据盘始终只允许
一个 VM 写入。对同一个已停止的安装换端口后，请重新登录并打开 Service。

## 安装数据与持久化

`--data-dir` 是**完整安装根目录**：

| 操作系统 | 默认根目录 |
| --- | --- |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/piwork-microvm` |
| Windows | `%LOCALAPPDATA%\PiworkMicroVM` |

| 安装内路径 | 内容 |
| --- | --- |
| `.lock` | 安装锁，确保两个进程不会共用同一个根目录 |
| `installation.json` | 安装身份和初始化状态 |
| `disks/state.qcow2` | Guest ext4，保存全部业务与容器持久数据 |
| `logs/` | 过滤后的启动/Guest 诊断 |
| `unclean.json` | 仅在上次停止未被确认时存在 |
| `runtime.json` | 运行中实例的临时运行信息 |

qcow2 逻辑容量 64 GiB，随实际分配增长，没有外部 backing 文件。`/mnt/state/core` 绑定到
`/var/lib/piwork/core`；Docker 使用 `/mnt/state/docker`，含其管理的 containerd 和 local named
volumes，`/var/lib/containerd` 也绑定到盘。账号、模型配置、Work private/workspace/历史/Memory 和
Service 声明的持久数据都在这里。RootFS 只读并使用临时 overlay。

使用现有 **Piwork Files** 上传/下载。文件保存在盘内的普通 Work workspace 卷。不提供 Host 目录共享、
映射盘、SMB、FUSE 或文件同步。

## 生命周期、停止与磁盘安全

保持启动器前台运行。按 **Ctrl+C** 并等待确认 Guest 正常停止，此时会打印
`Guest stopped cleanly. All user data retained.` 关闭过程有 120 秒预算；超时后启动器强制 QEMU 退出
并报告非正常停止。关闭窗口、系统关闭期限或强杀可能无法确认正常停止；此时 `unclean.json` 标记
（内容为 `{"shutdown":"unconfirmed"}`）会留在安装根目录，并在下次启动时重新提示。

备份步骤：

1. 正常停止启动器并等待确认信息。
2. 一起备份 `installation.json` 与 `disks/state.qcow2`。
3. 不要挂载运行中的磁盘，也不要把运行中的副本当作一致备份。

启动器会拒绝破坏数据：

- 已存在的磁盘缺失或不可访问时，不会被空盘替代。
- `installation.json` 非法时拒绝覆盖。
- 不明非空安装根不会被接管：
  `installation root contains unknown data; choose an empty directory (nothing was overwritten)`。

## 日志与诊断

每次运行写入 `<data-dir>/logs/<UTC 时间戳>.log`，权限 0600。只有包含 `qemu-system-x86_64` 的行会
回显到控制台；完整 QEMU argv JSON 只写入日志文件。

“过滤”是已强制执行的机制，而非期望。启动器会把匹配 `#setup=`、`authorization:`、`bearer `、
`api_key`、`apikey`、`password`、`token` 或 `credential` 的行替换为 `sensitive diagnostic omitted`，
在 QEMU 与 Guest Piwork 两条输出路径上都生效。因此 API Key、密码和 Token 不会出现在普通日志中。

## 资源缓存

内置资源在启动时懒解压到 `<UserCacheDir>/piwork-microvm/bundles/<manifest 的 sha256>/`，有效的缓存
会被复用而不再解压。并发解压会被串行化，解压需要 payload 大小外加 1 GiB 预留空间可用。

正常停止后删除缓存是安全的：可执行文件会重新解压，安装目录不受影响。

## 从源码构建

### 主机前置

Docker Engine、**恰好 Go 1.25.5**（其他 `go env GOVERSION` 会直接导致构建失败）、Git、Python 3、
Make、Bash、curl、qemu-img 和网络访问。Node **不是**主机前置，由容器提供。只有 Go 有强制版本校验。

### 容器提供组件

| 组件 | 版本 |
| --- | --- |
| Linux 内核 | 6.6.159 |
| QEMU | 10.0.8，含两个 Windows 补丁 |
| Windows QEMU 工具链 | Fedora 43 上的 MinGW |
| Node | 24 |
| Guest Docker | 28.5.2 |

### 构建目标

| 目标 | 作用 | 依赖 |
| --- | --- | --- |
| `source` | 克隆并固定锁定的上游源码 | 网络、git |
| `source-refresh` | 重新解析官方默认分支最新 HEAD 并重写 `build.lock.json` | 网络、git |
| `source-check` | 检查既有的干净固定副本，不拉取 | - |
| `kernel` | 构建 Guest 内核 | Docker |
| `piwork` | 构建上游 Piwork 及其容器镜像 | Docker、Go 1.25.5 |
| `guest` | 组装 Guest rootfs、initramfs 和状态盘 | `piwork`、`kernel` |
| `qemu` | 构建并打包 Linux QEMU | Docker |
| `qemu-windows` | 构建并打包 Windows QEMU | Docker |
| `piwork-microvm` | 产出 Linux 产物 | `guest`、`qemu` |
| `piwork-microvm-windows` | 产出 Windows 产物 | `guest`、`qemu-windows` |
| `piwork-microvm-all` | 产出两个平台产物 | 上述两者 |
| `test` | `go test ./...` | Go 1.25.5 |
| `boot-dev` | 仅开发使用：对宿主 QEMU 运行 | 宿主 `/usr/bin/qemu-system-x86_64`、已构建的 `dist/guest` |

```sh
make source-refresh         # explicitly resolve latest official default HEAD
make source-check           # verify the independent clean, locked checkout
make piwork-microvm-all     # both platform artifacts
# Or: make piwork-microvm / make piwork-microvm-windows
```

### 构建产物

- `dist/piwork-microvm` 与 `dist/piwork-microvm.exe`，各带 `.sha256` 校验文件。
- 中间产物：`dist/source/<commit>/piwork`、`dist/piwork/images.json`、
  `dist/piwork/metadata.json`、`dist/guest/`、`dist/qemu/`、`dist/qemu-windows/`。

### 上游固定

[`build.lock.json`](build.lock.json) 是唯一事实来源。它固定
`https://github.com/pphboy/piwork.git`、分支 `main`、commit
`a6c36da16ebcc0e96f0e34ef820d857f2bea4877`，解析时间为 2026-10-20。普通构建使用
`dist/source/<commit>/piwork` 中固定的完整 commit，修改过的输入会被拒绝。版本号 `0.0.9` 来自上游
自己的 `package.json`，不来自锁文件。

### 本地源码与可重现性

`make source PIWORK_SOURCE=/path/to/piwork` 仅在首次检出时把本地 clone 作为来源。它不会重置该
clone，不会复制未提交文件，且校验对修改过的输入硬失败。不应用任何 Piwork 补丁。

payload tarball 是确定性构建的（条目排序、`mtime` 为 0、固定权限、gzip `mtime` 为 0），但 Guest
ext4 rootfs 使用新生成的 UUID，因此不承诺整个产物逐字节重现。构建不推送、不发布；容器 registry
命名空间仅本地（`docker.io/piwork-microvm-local`）。

## 发布

发布在 GitHub 上进行，且只从打过 tag 的提交切出。Piwork MicroVM 有自己的版本号，独立于它
打包的上游 Piwork 版本；annotated git tag 是事实来源，`--version` 同时报出两者。

| 资产 | 内容 |
| --- | --- |
| `piwork-microvm-v<version>-linux-amd64` | Linux x86-64 ELF |
| `piwork-microvm-v<version>-windows-amd64.exe` | 原生 Windows x86-64 PE |
| `*.sha256` | 对应二进制的校验和 |
| `release-manifest.json` | 锁定输入、产物 hash 与验收状态 |
| `qemu-patches.tar.gz` | 被修改的 GPL 组件的对应源码 |
| `guest-licenses.tar.gz` | Guest 镜像内每个包的许可证文本 |

Guest 许可证同时内嵌在产物的 `provenance/guest-licenses/` 下，因此无需启动 VM 即可从下载物中阅读；
`index.json` 列出每个包，并标注没有可提取文本的包。

`make release VERSION=<v>` 执行门槛、测试、构建、清单与说明后即停止；
`make release-publish VERSION=<v>` 负责打 tag 并发布。构建流程从不推送或发布，容器镜像
始终只在本地 registry。

验收记录以**锁定输入**为基准，而不是下载到的字节：Guest ext4 rootfs 每次构建都重新生成
UUID，因此同一组输入构建两次，产物仍然不同。请用所属发布中的校验和验证下载，并查看清单的
`verification` 字段确认哪些平台真的跑过 —— 未运行的平台记录为 `not-verified`。发布说明包含
GPL 组件的对应源码、其锁定校验和与书面提供承诺，并列出当前分发的已知限制。

## 验收与证据

已完成变更的 [tasks.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/tasks.md) 当前记录为
**43/43 项完成，0 项未勾选**；请以该文件作为活的事实来源。另见
[proposal.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/proposal.md)、
[design.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/design.md) 以及
[`openspec/specs/`](openspec/specs/) 下同步后的主规格。此前变更归档在
[2026-10-21-make-piwork-microvm](openspec/changes/archive/2026-10-21-make-piwork-microvm/)，
46/46 项完成。

| 证据 | 日期 | 范围 |
| --- | --- | --- |
| [completion-acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/completion-acceptance.md) | 2026-10-21 | 在 Linux/KVM 与原生 Windows 11 Home build 26200/WHPX 上使用真实供应商 `deepseek-flash`、协议 `anthropic-messages`；六项最终产物异常恢复；真实模型工具调用跨重启续接；数据库 `integrity_check=ok` |
| [two-port-acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/two-port-acceptance.md) | 2026-10-21 | 0.0.9 双入口产物；该阶段真实供应商一行为 **NOT VERIFIED**，因为当时没有可用的真实密钥 |
| [acceptance.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/acceptance.md) | 2026-10-20 | 0.0.8 产物，同样两台宿主 |
| [windows-gate.md](openspec/changes/archive/2026-10-21-support-windows-and-disk-only-storage/evidence/windows-gate.md) | 2026-10-20 | 仅开发关口，明确不是最终产物验收 |

### Linux 验收

`make acceptance-microvm` 需要已构建的 `dist/piwork-microvm`、真实 `/dev/kvm`、用于外围隔离的
Docker，以及测试用 Playwright/Chromium。启动器运行在一个只含最终可执行文件的最小干净根目录中；测试
装置本身在该根目录之外。

### 端口验收

`make acceptance-ports` 在隔离的容器网络命名空间中，一次一个 VM，把最终产物启动在备选 Host 端口
（8080、8081、17891 和 80）上，且不触碰既有 Host 安装。它检查 7171 端口上的受控监听者保持不被影响、
只转发所选的两个回环端口，以及非法或已被占用的端口在任何 KVM 或数据操作之前安全失败。

### Windows 验收

Windows 验收使用原生 Edge 和原生 Node 作为**测试工具**。用
`GOOS=windows GOARCH=amd64 go build` 编译 `cmd/acceptance-windows` 和
`cmd/acceptance-guest-windows`，再把它们与测试脚本/fixtures、`dist/piwork/images.json`、原生 Node 和
Playwright 复制到 Windows 本地测试目录。
`scripts/acceptance-windows.ps1 -Root <目录> -Port 8080 -Phase first` 对已启动的正式 PE 执行浏览器
检查；Core 使用自定义端口时增加 `-CorePort <端口>`。`-Phase recovery` 检查已有基线，
`-Phase failures` 要求测试安装已停止。

### 不随产品发布

`cmd/acceptance-windows`、`cmd/acceptance-guest-windows`、`cmd/acceptance-chroot` 和
`cmd/microvm-probe` 只是测试与开发工具。产品命令只有 `cmd/piwork-microvm` 与 `cmd/piwork-guest`。

另有合成 OpenAI Responses 夹具在工具 ID 形如 `call-1|fc-1` 时复现历史 HTTP 503。该样本的 Run 和
原始历史/Memory 已持久化，但历史读取失败。此项保留为特定样本的已知异常，不能作为所有工具会话都会
失败的证据。真实供应商结果单独记录实际测试的模型和协议。Piwork 业务源码保持未修改。

## 范围与限制

- 不提供 Host 目录共享、映射盘、SMB、FUSE 或文件同步。
- 不回退 TCG 或替代机型；硬件加速是必需的。
- Windows 实测使用原生 Windows 11 Home build 26200，不据此声称所有 Windows 版本均已验证。多版本
  矩阵和第二台干净电脑在本版约定的验收范围之外。
- 同一数据盘始终只允许一个 VM 写入，且构建只在 Linux 上运行、不推送不发布。

## 许可证

Piwork MicroVM 的原创代码使用 [Apache-2.0](LICENSE) 许可，另见 [NOTICE](NOTICE)。Piwork、Linux、
QEMU 等第三方组件及上游组件补丁保留各自的许可证和声明。内置第三方组件的许可证文件随运行资源一起
解压。

## 相关文档

- [AGENTS.md](AGENTS.md) - 仓库提交与文档约定
- [build.lock.json](build.lock.json) - 固定的上游 commit 与构建输入
- [openspec/specs/](openspec/specs/) - 同步后的主规格
- [LICENSE](LICENSE) 与 [NOTICE](NOTICE) - 许可
