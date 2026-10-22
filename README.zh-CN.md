# Piwork MicroVM

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) ![Platforms](https://img.shields.io/badge/platforms-Linux%20x86--64%20%7C%20Windows%2011%20x86--64-blue) [![Upstream Piwork](https://img.shields.io/badge/upstream%20Piwork-0.0.11-informational)](build.lock.json)

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
- [桌面入口（GUI）](#桌面入口gui)
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
时才会打开。原版 Piwork 0.0.10 直接在浏览器创建首位管理员，随后正常登录并完成 QuickStart。

## 桌面入口（GUI）

可选的桌面入口是独立的 Wails v2.17.0 应用，本地构建为单独的单文件；它不替换、不改名，也不给 CLI
产物增加桌面依赖。

### 运行要求

- **Windows 11**：Microsoft Edge WebView2 Runtime（当前 Windows 11 默认存在）和 WHPX，固件虚拟化
  前提与 CLI 相同。
- **Linux**：GTK 3 与 WebKitGTK 4.1 运行库（例如 `libgtk-3-0`、`libwebkit2gtk-4.1-0`），以及可用的
  系统浏览器启动器：`xdg-open`、`gio open`、`gnome-open`、`kde-open` 或 `sensible-browser`。若均
  不存在，启动器会明确报错，而不是静默无反应。
- KVM/WHPX、磁盘空间、端口与数据锁规则与 CLI 相同。运行和构建静态前端都不需要宿主 QEMU、Docker、
  Node、NPM 或 Vite。
- 这些桌面库与运行库**只**适用于 GUI；CLI 仍是 `CGO_ENABLED=0` 且不依赖桌面组件的二进制。

### 运行

双击 `piwork-microvm-gui`（Windows 为 `piwork-microvm-gui.exe`）。首次界面固定英文，
不随系统语言自动变中文，使用平台默认数据根，可通过原生「Change」选择目录。更多菜单选择
「简体中文」后，以下操作名按中文显示。点击一次「启动 Piwork」，界面显示真实阶段；只有本次 VM 的 `/healthz`
返回 HTTP 200 后，「打开 Piwork」才可用。管理员创建、模型/API Key 与 Runtime 配置仍由原版 Piwork
页面负责。

- 数据根是完整安装根（元数据、`disks/state.qcow2`、日志）。Windows 默认
  `%LOCALAPPDATA%\PiworkMicroVM`，Linux 默认 `$XDG_DATA_HOME/piwork-microvm`（或
  `~/.local/share/piwork-microvm`）。
- **语言：** 更多 → English / 简体中文立即切换并保存，不增加设置页或首启必选步骤。旧偏好
  没有语言字段时也默认英文；切换不重启 VM、不改数据根，引导文档按语言打开对应 README。
- 偏好单独保存在 Windows `%APPDATA%\piwork-microvm\launcher.json`、Linux
  `$XDG_CONFIG_HOME/piwork-microvm/launcher.json`（或 `~/.config/...`）。WebView 数据留在各自的
  用户目录，绝不进入安装根。
- 成功标记只在真实健康检查成功且安装身份匹配后写入。仅复制磁盘模板或一次失败启动都不算完成。
- 点击停止或关闭运行中的窗口会弹出原生确认，然后执行与 CLI 相同的有序 Guest 停止和磁盘同步；重复
  操作复用同一次停止。未确认的关机保留为错误，不会被自动关窗掩盖。
- 底部日志面板显示本次会话；重开时若本次尚无日志，会显示最近的历史日志。「导出本次日志」通过原生
  保存对话框写出脱敏 `.log`，「导出全部日志」只归档所选安装的脱敏 `.zip`。技术日志保留原文；
  应用文案及原生对话框自有标题使用所选语言，系统按钮和文件列表使用系统语言。

## 命令行参考

| 参数 | 默认值 | 有效值 | 用途 |
| --- | --- | --- | --- |
| `--data-dir DIR` | 平台默认根目录 | 任意路径 | 完整安装根目录（元数据、磁盘、日志） |
| `--port PORT` | `17891` | 1-65535，排除 7172 | Host 浏览器 UI/ControlPlane 端口 |
| `--core-port PORT` | `17871` | 1-65535，排除 7172 | 供 CLI/backend 使用的 Host Core API 端口 |
| `--cpus N` | `2` | 1-64 | 虚拟 CPU 数 |
| `--memory MiB` | `4096` | 1024-262144 | Guest 内存（MiB） |
| `--no-open` | 关闭 | - | 不自动打开访问地址 |
| `--startup-timeout D` | `15m` | > 0 | 等待 Guest 就绪的最长时间 |
| `--help`、`-h` | - | - | 显示帮助，不触碰虚拟化与数据 |

- `--port` 与 `--core-port` 必须不同，且都须在 1-65535 范围内，排除内部 Agent RPC 保留端口 7172。
  保留端口会在访问虚拟化和数据前明确报错。
- 不接受位置参数。
- 成功和 `--help` 的退出码为 `0`；任何失败都以退出码 `1` 结束，并向 stderr 打印
  `piwork-microvm: <error>`。
- 仅开发使用：`--assets DIR` 与 `--qemu PATH` 必须成对给出，用于显式选用外部 QEMU。这不属于普通
  用户流程。

## 网络与访问

只转发两个 Host 端口，且所有 Host 监听都绑定到 `127.0.0.1`：

| 参数 | Host 默认端口 | Guest 端口 | 用途 |
| --- | --- | --- | --- |
| `--port` | 17891 | 所选 `--port` | UI、登录、管理、QuickStart 和 Service Proxy |
| `--core-port` | 17871 | 所选 `--core-port` | 供 CLI/backend 使用的 Core API |

Guest 监听、QEMU 目标和内部 Core 客户端随所选 UI/Core 端口联动；
不增加反向代理，不放宽 Host/Origin/CSRF。浏览器 origin 跟随 `--port`，HTTP 80 端口的 origin 不带 `:80`。端口冲突会明确报错并指明被占用的
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

升级验收先确认专属旧测试安装已安全停止，再将 `installation.json` 与 `disks/state.qcow2`
成组复制到另一安装根；只启动副本，核对原身份与数据后安全停止并重开同一副本。
不要使用用户原盘；兼容检查失败时不初始化替代磁盘。回退使用未升级的停机备份，
不承诺旧 Core 能读取已经升级的副本。

## 日志与诊断

每次运行写入 `<data-dir>/logs/<UTC 时间戳>.log`，权限 0600。只有包含 `qemu-system-x86_64` 的行会
回显到控制台；完整 QEMU argv JSON 只写入日志文件。

“过滤”是已强制执行的机制，而非期望。启动器会把匹配 `#setup=`、`authorization:`、`bearer `、
`api_key`、`apikey`、`password`、`token` 或 `credential` 的行替换为 `sensitive diagnostic omitted`，
在 QEMU 与 Guest Piwork 两条输出路径上都生效。因此 API Key、密码和 Token 不会出现在普通日志中。

Guest 正常运行时，打开 Piwork 并以管理员登录，从 Desktop 账户菜单唯一的 `Export logs`
入口收集并打包日志，再把浏览器下载的 ZIP 保存到 Host。打开 `manifest.json` 核对 Core、自己的
Work/Service 来源和缺口；部分结果不代表保留了全部历史，开始下载也不代表已经保存。
这类业务故障包与 Launcher 运行日志不同。

GUI 启动失败时，选择「查看日志」→「导出本次日志」。存在真实 VM 会话文件时，导出开始时已写入的
完整脱敏内容（包括界面有界缓冲未显示的部分）；会话文件尚未创建时，同一操作可保存已经显示的
真实启动错误。「导出全部日志」只包含所选安装的真实日志文件。没有相应真实内容时禁用对应项。

保存到普通可写的下载/桌面目录即可，不会修改目录权限。取消不写入；写入、同步或替换失败会明确
报错，未完成的输出不替换原文件。当前上限为单个源文件 64 MiB、全部源日志合计 256 MiB，超限明确
失败，不静默截断。保存后自行将文件发送给维护者，应用没有上传服务。

窗口没有打开时，按系统错误检查 Windows 的 WebView2，或 Linux 的 GTK/WebKitGTK 和桌面会话。
Linux 可从终端执行 `./piwork-microvm-gui` 查看加载器/Wails 错误；Windows 查看系统错误弹窗并检查
WebView2 Runtime。OS 加载/Wails 初始化前失败不承诺生成应用诊断文件，也没有独立早期诊断目录或包。

## 资源缓存

内置资源在启动时懒解压到 `<UserCacheDir>/piwork-microvm/bundles/<manifest 的 sha256>/`，有效的缓存
会被复用而不再解压。并发解压会被串行化，解压需要 payload 大小外加 1 GiB 预留空间可用。

正常停止后删除缓存是安全的：可执行文件会重新解压，安装目录不受影响。

## 从源码构建

### 主机前置

Docker Engine、**恰好 Go 1.25.5**（其他 `go env GOVERSION` 会直接导致构建失败）、Git、Python 3、
Make、Bash、curl、qemu-img 和网络访问。Node **不是**主机前置，由容器提供。只有 Go 有强制版本校验。

默认的 `official-release` 输入导入 Piwork 已发布的 Linux 二进制，并按摘要拉取配套生产镜像；
不执行上游 npm、Go 或镜像源码构建。首次准备仍需要 Go 1.25.5（读取模块身份与模块许可文本）、
Docker 和网络。显式选择的 `source` 输入仍按原方式编译锁定提交。

### 桌面 GUI 构建前置

GUI 构建与 CLI 分离，并使用固定的 Wails CLI：

- Go 1.25.5，以及本模块固定的 Wails CLI（`go tool wails version` 必须输出 `v2.17.0`）。
- **Linux**：GCC、pkg-config、`libgtk-3-dev` 与 `libwebkit2gtk-4.1-dev`；Linux GUI 必须在 Linux 上
  构建。
- **Windows**：原生 Windows 11、Go 1.25.5、`PATH` 中的 MinGW-w64 GCC 和 WebView2 运行库。Windows
  GUI 必须在原生 Windows 上构建；WSL、交叉编译或 Linux GUI 结果不能作为 Windows 证明。
- 不需要 Node/NPM：前端是静态资源，通过 `go:embed` 内置。

### 容器提供组件

| 组件 | 版本 |
| --- | --- |
| Linux 内核 | 6.6.159 |
| QEMU | 10.0.8，含两个 Windows 补丁 |
| Windows QEMU 工具链 | Fedora 43 上的 MinGW |
| Node | 24 |
| Guest Docker | 28.5.2 |

官方输入构建按 registry 摘要拉取固定的 Agent、file-helper 与 snapshot-helper 镜像，并内嵌到
Guest 归档。最终产物离线加载这些镜像，用户无需 Host Docker 或网络。

### 构建目标

| 目标 | 作用 | 依赖 |
| --- | --- | --- |
| `source` | 克隆并固定锁定的上游源码 | 网络、git |
| `source-refresh` | 仅源码模式：重新解析官方默认分支 HEAD 并重写 `build.lock.json` | 网络、git |
| `source-check` | 检查既有的干净固定副本，不拉取 | - |
| `piwork` | 准备锁定输入（默认导入官方发行制品） | Docker、Go 1.25.5、网络 |
| `piwork-lock` | 显式替换官方发行输入；需 `TAG`，例如 `TAG=v0.0.11` | 网络、git |
| `piwork-check` | 只读校验已准备输入及其输出摘要，不写入、不拉取 | Python 3 |
| `piwork-source` | 显式编译锁定提交，而不是导入官方发行制品 | Docker、Go 1.25.5 |
| `kernel` | 构建 Guest 内核 | Docker |
| `guest` | 组装 Guest rootfs、initramfs 和状态盘 | `piwork`、`kernel` |
| `qemu` | 构建并打包 Linux QEMU | Docker |
| `qemu-windows` | 构建并打包 Windows QEMU | Docker |
| `piwork-microvm` | 产出 Linux 产物 | `guest`、`qemu` |
| `piwork-microvm-windows` | 产出 Windows 产物 | `guest`、`qemu-windows` |
| `piwork-microvm-all` | 产出两个平台产物 | 上述两者 |
| `piwork-microvm-gui` | 产出 Linux GUI 产物 | `guest`、`qemu`、GUI 构建前置 |
| `piwork-microvm-gui-windows` | 产出 Windows GUI 产物 | `guest`、`qemu-windows`、原生 Windows GUI 前置 |
| `piwork-microvm-gui-all` | 产出两个 GUI 产物 | 上述两个 GUI 目标 |
| `test` | Go 测试与 Python 脚本测试 | Go 1.25.5、Python 3 |
| `boot-dev` | 仅开发使用：对宿主 QEMU 运行 | 宿主 `/usr/bin/qemu-system-x86_64`、已构建的 `dist/guest` |

Kernel、QEMU 与 Guest 组装在 `dist/build-current/` 写入组件记录：仅覆盖该组件自身输入，
并记录全部输出的大小与 SHA256。只有记录与当前输入一致且所有输出校验通过时才跳过构建；
输出缺失/损坏、输入变化或没有记录都会重建。需要完整重建时使用 `FORCE_REBUILD=1`。
每次检查输出 `component <kind>: HIT|MISS` 与耗时。同一份已核验 Guest 只组装一次，
供四个 CLI/GUI 入口复用，原 payload/Trailer 格式不变。

```sh
make piwork                                    # 导入锁定官方发行制品
make piwork-check                              # 只读校验该导入
make piwork-lock TAG=v0.0.11                   # 显式更新发行输入（联网）
make piwork-source                             # 显式编译锁定提交
make guest PIWORK_SOURCE=/home/p/Projects/piwork  # 统一组装 Guest 一次
make source-check                              # 检查独立干净锁定副本（源码模式）
# 下方两个 GUI 构建复用同一 Guest，不刷新冻结锁。
```

当锁选择 `official-release` 时，`source-refresh` 会被拒绝：发行更新必须同时替换资产、程序身份
和镜像摘要，因此请使用 `make piwork-lock`。缺少 `piwork.inputMode` 的旧锁仍按源码锁处理，
可继续使用 `source-refresh`。

锁定的 Guest/QEMU 资源已构建时，可只重建 GUI 主体并追加现有资源，不刷新上游：

```sh
python3 scripts/gui-build.py --platform linux
# 在原生 Windows，用同一源码、锁与 dist/piwork/metadata.json：
# powershell -File scripts/gui-build-windows.ps1 -Source C:\src\piwork-microvm -Output C:\src\piwork-microvm\dist\launcher-gui-windows.exe -Version <wrapper-version> -Commit <git-commit>
# 随后在资源构建主机封装：
PIWORK_RELEASE_VERSION=<version> python3 scripts/bundle.py --entry gui --platform windows --body /path/to/launcher-gui-windows.exe
```

Linux GUI 使用 `CGO_ENABLED=1` 和 `desktop production webkit2_41` tag；原生 Windows GUI 使用
`CGO_ENABLED=1`、`desktop production` 和 `-H windowsgui`；CLI 保持禁用 CGO。当公共资源构建主机是
Linux 时，原生主体脚本负责 Windows 部分，最终 EXE 仍内含全部 Guest/QEMU 资源。只有可选前端回归
`node --test scripts/frontend_test.mjs` 需要 Node，构建和运行 GUI 不需要。构建不打 tag、不推送、不发布。

### 构建产物

- `dist/piwork-microvm` 与 `dist/piwork-microvm.exe`，各带 `.sha256` 校验文件。
- `dist/piwork-microvm-gui` 与 `dist/piwork-microvm-gui.exe`，各带 `.sha256` 校验文件。
- GUI 中间产物使用独立名称：`dist/launcher-gui-<platform>[.exe]`、
  `dist/payload-gui-<platform>.tar.gz` 与 `dist/bundle-manifest-gui-<platform>.json`，不会覆盖
  CLI 中间产物或 CLI 产物。
- 中间产物：`dist/source/<commit>/piwork`、`dist/piwork/images.json`、
  `dist/piwork/metadata.json`、`dist/piwork/import.json`、`dist/piwork/upstream-release/`、
  `dist/guest/`、`dist/qemu/`、`dist/qemu-windows/`。导入的二进制与镜像归档原子发布：
  任一步校验失败都会保留上一份有效输入。

### 上游固定

[`build.lock.json`](build.lock.json) 是唯一事实来源。`piwork.inputMode` 选择
`official-release`（当前）或 `source`；缺少该字段的锁按源码锁处理。当前锁固定
`https://github.com/pphboy/piwork.git`、发行标签 `v0.0.11`、实际构建提交
`a19c6f595fa6b2515d19146f3510dfc9f1ba4b8c` 和独立的发布提交
`2142491f5103b58731de4872d153bd1b876860de`，并记录四个资产的大小/SHA256、程序与 UI 身份、
以及三个生产镜像摘要。`piwork.commit` 始终是实际构建提交，绝不是发布提交。

普通构建只消费锁，不跟随 `main`、可变标签或 `latest`。源码模式使用
`dist/source/<commit>/piwork` 中固定的完整提交，修改过的输入会被拒绝。内置上游版本为
`0.0.11`（上游 Preview），与包装层版本相互独立。

### 本地源码与可重现性

`make source PIWORK_SOURCE=/path/to/piwork` 仅在首次检出时把本地 clone 作为来源。它不会重置该
clone，不会复制未提交文件，且校验对修改过的输入硬失败。不应用任何 Piwork 补丁。

payload tarball 是确定性构建的（条目排序、`mtime` 为 0、固定权限、gzip `mtime` 为 0），但 Guest
ext4 rootfs 使用新生成的 UUID，因此不承诺整个产物逐字节重现。构建不推送、不发布。源码模式使用
本地 registry 命名空间 `docker.io/piwork-microvm-local`；官方模式按摘要拉取镜像，且从不向任何
registry 推送。

导入二进制、其 Go 模块及生产镜像的可读许可文本写入
`dist/piwork/upstream-release/licenses/`，并内嵌到每个产物的
`provenance/piwork-upstream/licenses/` 下。Guest 包文本仍在 `provenance/guest-licenses/` 与
`guest-licenses.tar.gz` 中。各 `INDEX.json` 会记录无法提取文本的组件而不是丢弃它们，且这些文件
都无需启动 VM 即可读取。

## 发布

发布在 GitHub 上进行，且只从打过 tag 的提交切出。Piwork MicroVM 有自己的版本号，独立于它
打包的上游 Piwork 版本；annotated git tag 是事实来源，`--version` 同时报出两者。本次目标为
包装层 v0.2.1，内置 Piwork 0.0.11 —— 这是上游 **Preview**，不是稳定发行版。

| 资产 | 内容 |
| --- | --- |
| `piwork-microvm-v<version>-<platform>-amd64[.exe]` | Linux x86-64（ELF）或原生 Windows x86-64（PE）CLI |
| `piwork-microvm-gui-v<version>-<platform>-amd64[.exe]` | 同两平台 GUI，使用独立主体与 payload |
| `*.sha256` | 对应二进制的校验和 |
| `release-manifest.json` | 锁定输入、四个产物 hash 与分范围验收状态 |
| `qemu-patches.tar.gz` | 被修改的 GPL 组件的对应源码 |
| `guest-licenses.tar.gz` | Guest 镜像内每个包的可读许可证文本 |
| `piwork-licenses.tar.gz` | 导入二进制、其 Go 模块及生产镜像的可读许可证文本 |

GUI 主体必须在原生 Windows 上用 `scripts/gui-build-windows.ps1` 构建，再在资源构建主机执行
`scripts/bundle.py --entry gui --platform windows --body ...`。Wails 不做交叉编译；Linux GUI
不能替代 Windows GUI。Windows 主体会写入构建记录，封装会拒绝版本、平台、入口或锁定输入
不匹配的主体。

`make release VERSION=0.2.1` 执行门槛、测试、Linux 构建、四产物检查、清单与说明，随后在
`dist/release-plans/v0.2.1/` 冻结版本计划并停止。它绝不打 tag、不推送、不发布，也不向任何
registry 推送容器镜像。`make release-publish VERSION=0.2.1` 是独立的远端步骤：校验冻结计划
与本地字节，创建或复用 annotated tag，建立草稿，上传缺失资产，核对每个远端文件的大小与
SHA256，全部完成后才公开。

上传中断后重新执行同一命令即可。冻结计划与说明会被复用；已匹配的远端资产跳过，可确认属于
同一草稿计划且尚未完成的占位资产会先受控清理再重传。tag 指向其他提交、已完成资产内容不同、
或已公开版本内容不同时，均明确拒绝而不是覆盖。上传按文件重试；GitHub 不提供文件内断点续传。
四个完整产物仍占主要传输时间。

`make release-publish-dry-run VERSION=0.2.1` 只打印冻结的 tag 与资产列表，不创建 tag、不写远端。

验收记录以**锁定输入**为基准，而不是下载到的字节：Guest ext4 rootfs 每次构建都重新生成
UUID，因此同一组输入构建两次，产物仍然不同。清单携带完整输入指纹，并分别列出 `build`、
`integration`、`real-model` 与 `upstream` 范围；只有指纹相同的记录才能把某一范围标为
verified，上游记录永远不会提升 MicroVM 范围。请用所属发布中的校验和验证下载。

### 升级已有的 0.2.0 安装

先正常停止旧启动器，再把 `installation.json` 与状态盘一起复制到独立目录。用新的 0.2.1
产物启动该副本，核对既有账号、Work、Files 与 Service 数据以及正常停止/重开。保留未触碰的
停机原件及其备份。本次只报告实际测试副本的结果，不承诺通用降级兼容。需要回退时，使用未触碰的
停机安装与旧发行文件，绝不能拿旧 Core 去打开已升级副本。

发布说明逐个列出 GPL/LGPL 组件（包括 BusyBox、qboot、libfdt 与 Guest 包）的对应源码、锁定
校验和、书面提供承诺，以及当前分发的已知限制。可读许可文本同时内嵌在每个产物的
`provenance/` 与 `guest-licenses.tar.gz`/`piwork-licenses.tar.gz` 中，无需启动 VM。

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
| [冻结 Core 日志导出验收](openspec/changes/archive/2026-10-22-update-guest-piwork-log-export/acceptance.md) | 2026-10-22 | Piwork 0.0.10、`29e3471`；两平台原生 GUI、Desktop 故障/缺口 ZIP 实际下载、停机副本持久化及一对自定义 UI/Core 端口；未调用真实模型 |
| [GUI 验收](openspec/changes/archive/2026-10-22-add-cross-platform-desktop-launcher/acceptance.md) | 2026-10-22 | Linux/KVM 与原生 Windows/WebView2/WHPX CoreLoop、目录/日志对话框、Work/Files/Services、数据库持久化与异常恢复；未验证真实模型调用 |

### GUI 验收

已归档的 GUI 记录基于其原 Piwork 输入，覆盖 C1/W1–W5、默认英文、英/简中切换保存、Launcher
正常/错误导出与安全停止。[本轮冻结 Core 整合](openspec/changes/archive/2026-10-22-update-guest-piwork-log-export/acceptance.md)
在 Linux/KVM 与原生 Windows/WebView2/WHPX 上使用新构建的 0.0.10 Guest，覆盖保存到 Host 的 Desktop
故障/缺口 ZIP、旧安装停机副本、语言保存、安全关机及自定义 19190/19191 路径。两份记录均不声称新增
真实模型调用或未测试的 Windows 版本已通过。GUI 构建不打 tag、不推送、不发布。

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

历史 0.0.9 的合成 OpenAI Responses 夹具在工具 ID 形如 `call-1|fc-1` 时复现历史 HTTP 503。该样本的
Run 与原始历史/Memory 已持久化，但历史读取失败。本轮冻结 0.0.10 输入未重跑这个夹具；此处保留历史
证据，不作为当前工具会话仍会失败的结论。真实供应商记录单独注明实际模型与协议。Piwork 业务源码未修改。

## 范围与限制

- 不提供 Host 目录共享、映射盘、SMB、FUSE 或文件同步。
- 不回退 TCG 或替代机型；硬件加速是必需的。
- Windows 实测使用原生 Windows 11 Home build 26200，不据此声称所有 Windows 版本均已验证。多版本
  矩阵和第二台干净电脑在本版约定的验收范围之外。
- 同一数据盘始终只允许一个 VM 写入，且构建只在 Linux 上运行、不推送不发布。
- GUI 增加了上述系统 WebView/GTK 运行前提，这些前提不适用于 CLI。GUI 不内嵌 Piwork WebUI，不增加
  账户/模型/Runtime 表单，不驻留托盘，也不管理第二个安装。

## 许可证

Piwork MicroVM 的原创代码使用 [Apache-2.0](LICENSE) 许可，另见 [NOTICE](NOTICE)。Piwork、Linux、
QEMU 等第三方组件及上游组件补丁保留各自的许可证和声明。内置第三方组件的许可证文件随运行资源一起
解压。

## 相关文档

- [AGENTS.md](AGENTS.md) - 仓库提交与文档约定
- [build.lock.json](build.lock.json) - 固定的上游 commit 与构建输入
- [openspec/specs/](openspec/specs/) - 同步后的主规格
- [LICENSE](LICENSE) 与 [NOTICE](NOTICE) - 许可
