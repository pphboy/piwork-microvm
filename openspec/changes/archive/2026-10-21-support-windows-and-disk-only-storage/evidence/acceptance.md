# 本地验收记录

日期：2026-10-20。变更：`support-windows-and-disk-only-storage`。

已产出并真实运行两个自包含文件；完整验收仍保留上游工具调用历史失败，以及没有环境执行的 Windows 能力负例。没有发布 Release、推送仓库或镜像。Piwork 业务源码、契约、UI 均未修改。

## 产物和构建输入

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `dist/piwork-microvm` | 392268368 | `0f347071f87c045ed387868fcae4d5285d613a0d50f324a5e1fd3ad0edb43a66` |
| `dist/piwork-microvm.exe` | 409080329 | `9007b45e34af52fd8a4f98dcf93348bb121c753907f57bb79158acecccea1fd8` |

完整身份、镜像 ID、资源数见 [artifacts.json](artifacts.json)。Piwork 原版 commit 为 `9a40d4443fee559335485744d0aabbf186e24b38`，上游版本 0.0.8，release ID 为 `0.0.8-9a40d4443fee-8093dd5fbc88`。实施开始解析官方默认 HEAD 后锁定，后续远程复核仍是相同 commit。独立源码 `sourceModified=false`、`patches=[]`。Docker 构建配方的副本仅将基础镜像替换为构建锁中的 digest，不改业务源文件。

Linux kernel 6.6.159、Docker 28.5.2、QEMU 10.0.8；Guest 共用同一 kernel/initramfs/RootFS/盘模板。完整重建入口 `make piwork-microvm-all`，分项 `make guest`、`make qemu`、`make qemu-windows`；依赖、源码刷新/检查见双语 README。常规 Windows QEMU 构建使用固定 Fedora 基础镜像、184 个带 SHA256 的 RPM 和 326 个完整安装包身份。两处 QEMU Windows 管道修复随包提供；没有 Piwork 补丁。

## 环境与执行方式

| 项目 | 实际环境/结果 |
|---|---|
| Linux | 提供的 WSL Linux x86-64，真实 `/dev/kvm`，API 12；QMP `query-kvm` 的 present/enabled 均 true |
| Linux 依赖隔离 | 外围 Docker 网络命名空间与空 chroot；运行根只有最终 ELF、设备、proc、resolv 和自己解压的资源，PATH 无构建工具；测试工具在根外执行 |
| Windows | 原生 Windows 11 家庭中文版 25H2，10.0.26200，AMD Ryzen 9 7945HX；WHPX 已启用，测试进程**未提权** |
| Windows 路径 | `C:\Users\p\AppData\Local\PiworkMicroVM-final-20261020\piwork-microvm.exe`，安装根 `安装 数据`，含 Unicode 和空格 |
| Windows 浏览器 | 原生 Edge，经原生 Node/Playwright 驱动；Windows 进程、DLL、Guest 文件与数据盘均为本地路径 |
| Windows 运行依赖 | 正式 PE 的一次恢复启动限制 PATH 为 System32；仍从包内加载 QEMU/DLL/Guest，无 Host QEMU/Docker/语言运行时调用 |

Linux 的测试隔离不等于第二台干净物理 Host；Windows 的构建使用 Linux/WSL，正式 PE 运行不调用 WSL。检查 Guest 数据库及合成模型夹具使用的 `acceptance-guest-windows.exe` 是**独立验收工具**，不打包进产品，不替代正式 PE 的 QuickStart、Work/Files/Service 和恢复测试。

## 实际运行和网络

Linux 的完整实际参数见 [linux/proof-8080.json](linux/proof-8080.json) 的 `qemuArgv`；Windows 见 [windows/windows-process-proof.json](windows/windows-process-proof.json) 的原生进程命令行、模块及监听。临时开发关口的跟踪参数另见 [windows-gate.md](windows-gate.md)，不作为最终产物参数。

两平台均为 `-M microvm,pcie=off,acpi=off,auto-kernel-cmdline=on`，2 vCPU/4096 MiB，VirtIO-MMIO 的 blk/net/serial/rng，没有 PCI 或共享设备。Linux 用 `-accel kvm,kernel-irqchip=on -cpu host`；Windows 用 `-accel whpx,kernel-irqchip=on -cpu qemu64`。Windows 由 WHPX API 获取稳定 TSC 频率传给 kernel，QEMU 编译 FD_SETSIZE=1024，避免 65 条转发使 DNS UDP socket 被遗漏。

SLIRP DHCP `10.0.2.15/24`，网关 `10.0.2.2`，DNS `10.0.2.3`。每次只有 65 个 IPv4 `127.0.0.1` TCP 转发：所选主端口到 Guest 7171，以及 17891–17954 到同号 Guest 端口。控制通道为 Linux 私有 Unix socket / Windows 创建时当前用户专用 DACL 的 named pipes，没有管理 TCP。

| 验收项 | Linux 最终 ELF | Windows 最终 PE |
|---|---|---|
| 原版首位管理员、正常登录、QuickStart、真实 runtime ready | 通过 | 通过 |
| 新建真实生产 Agent Work | 通过 | 通过 |
| Files 中文文本/二进制上传下载、SHA256、修改/删除 | 通过 | 通过 |
| 主机访问真实授权 Service | 通过 | 通过 |
| WebSocket 往返 / SSE 流 | 通过 | 通过 |
| 匿名 Service 请求拒绝 | 通过 | 通过 |
| 只读卷不可写、未授予卷不可见 | 通过 | 通过 |
| 停止/禁用后旧授权入口拒绝 | 通过 | 通过 |
| Guest、Work DNS / HTTPS / 无 Key AI API 连通性 | 初始通过；末轮一次失败后结构化重测 DNS=true、HTTPS=200、AI API=401（08:05 UTC），首次失败未保留 stderr | 初始通过；末轮一次失败后结构化重测 DNS=true、HTTPS=200、AI API=401（08:01 UTC） |
| 默认 7171 | 真实浏览器通过 | 当前 Host 已占用，明确报错；未停止占用程序 |
| 8080 / 80、规范 origin、更换端口后重登 | 通过；7171 受控占用时也通过 8080 | 通过；8081 首次流程、8080/80 恢复 |

最小 chroot 的 C locale Chromium 对中文下载曾建议通用名称 `download`；下载内容 SHA256 相同、Files 中名称保留。普通 Linux 浏览器环境和原生 Edge 使用中文建议文件名。此差异原样记在 `browser-result.json`。

## 存储、恢复和关机

`--data-dir` 是完整安装根：`installation.json`、`disks/state.qcow2`、`logs/`。qcow2 为无外部 backing 的 64 GiB 逻辑盘，Guest `/dev/vdb` 直接挂载 ext4 到 `/mnt/state`。Core 在 `/mnt/state/core`，Docker 为 `/mnt/state/docker`，实际 containerd root 为 `/mnt/state/docker/containerd/daemon`，另有 `/var/lib/containerd` 的 ext4 bind。

真实 Core、Work、Memory、Service SQLite 数据库均检查为 ext4，`PRAGMA integrity_check=ok`。两个原版 Docker local named volumes 的身份在恢复后不变，private、workspace、Session JSONL/Run、Memory 和声明的 Service 持久数据留在盘内。普通 Host 目录不直接展示文件；通过原版 Files 访问。

两平台已验证管理员/模型身份、Work/Service revision、Session/Run 记录、中文/二进制文件 hash、Service SQLite 计数和完整性恢复；清空/损坏缓存只重建资源。Linux 做了真实 SQLite WAL/DELETE 并发锁、事务和同步测试。Windows 在窗口关闭及父进程强杀后恢复了同一盘；后续额外检查的四个数据库仍为 integrity ok，卷名与故障前一致。

正常 Ctrl+C：停止 Piwork、Docker，确认 unit Result，sync 并卸载 Core/containerd bind 与 state ext4，最后结束 QEMU。Windows 在确认卸载后 QMP quit，避免依赖 WHPX triple-fault reboot 的异常退出表现。正常结果才移除 unclean 标记。Windows 关闭控制台会中断关机；该次准确报未确认，保留标记。父进程强杀的 Job 保护终止 QEMU，之后启动提示恢复检查，没有创建空盘替代原盘。

## 实际故障测试

| 场景 | 结果 |
|---|---|
| Linux 无 KVM、KVM 无权限 | 最终 ELF 明确拒绝，未启动 VM |
| Windows 缺少 WHPX / 最低 Win11 版本 | 没有该环境，未实际执行；未关闭本机 Hypervisor |
| 必要主端口、Service 端口冲突 | 两平台最终文件明确拒绝，不停止占用程序 |
| 无效端口/只读 help | 原生测试和最终文件通过，未创建指定数据目录 |
| 未知非空根、已有盘缺失/损坏 | 拒绝覆盖；原盘恢复后 SHA256 精确相同 |
| 第二启动、磁盘身份/别名、继承保护 | Linux 不同网络命名空间/主端口仍被锁拒绝；launcher 强杀后 QEMU 保持安装/实际盘/硬链接锁直到退出；Windows 原生文件身份/大小写/junction/硬链接及真实 Job 强杀检查通过 |
| Windows 管道 ACL/取消/断开 | 当前用户专用；真实 OS 管道测试拒绝宽 ACL，持久请求、迟到响应、取消和断线有界；真实 QEMU 连续 QMP/QGA 操作通过 |
| 持久盘未挂载、错误标记 | 独立 Guest mount namespace 的未挂盘初始化失败；错误标记阻止 Docker/Piwork，恢复标记后 launcher 按失败阶段收尾 |
| 生产镜像缺失/身份不符 | 内置归档补回缺失镜像；错误预期 ID 明确报 `production image identity mismatch` 并停止 |
| 缓存损坏/删除 | 两平台最终文件重建并恢复同一 Guest 资源，原安装/文件/Service 数据保留 |
| Guest 提前退出 | Linux 最终 ELF 明确失败并留盘和 unclean 标记 |
| Guest QGA 不可用、关机超时 | 实际用尽 120 秒预算后强制退出、保留异常标记，之后原盘恢复通过 |
| Windows 窗口关闭、launcher 强杀 | 均没有假报 clean，异常提示和数据保留；强杀后 Job 中 QEMU 不残留 |

## AI 和未完成验收

生产 Agent SDK 已通过明确标注的**合成 Responses 协议夹具**完成 Memory status/stage/commit 和文本 Run。不是外部模型调用。普通文本 Session 的历史读取在恢复后返回 200，Run 内容一致。真实外部供应商调用没有 Key，未验证。

**已确认失败：原版 0.0.8 的 Responses 工具调用 Session 历史读取返回 503。** SDK 产生如 `call-1|fc-1` 的 toolCallId，而 `packages/contracts/src/harness.ts` 的 IdentifierSchema 禁止 `|`；Core `internal/agentclient/client.go` 的 SessionContentBlockSchema 校验拒绝，映射为 RUNTIME_UNAVAILABLE。工具 Run 本身已成功，原始 JSONL、Run 和 Memory 数据保留。两平台均复现；没有通过更改 Piwork 或改写历史绕过。此项使“完整 AI/工具历史 Happy Path”不能声明全通过，8.1/8.2 保留未完成。

| 覆盖矩阵 | 状态/原因 |
|---|---|
| Linux 当前 KVM Host、空运行根 | 已执行；包含最终产物与真实容器/浏览器 |
| Windows 11 Home 25H2 / build 26200 | 已执行；普通用户、原生 PE/Edge/WHPX |
| Windows 11 Home 21H2 / 22H2 / 23H2 / 24H2 | 未验证：没有这些系统；产品最低目标仍为 21H2，没有增加 24H2 或 Pro 门槛 |
| 第二台无预装工具的干净 Host | 未验证：只有提供的机器；依赖隔离与 PATH 限制分别记录 |
| WHPX 被禁用、BIOS 虚拟化关闭 | 未验证：当前已启用，未擅自更改主机能力 |
| 真实模型 Key | 未验证：未提供，不声明模型调用成功 |
| Responses 工具调用历史 | **失败**：上述未修改上游问题；普通文本历史已单独通过 |

复验入口：Linux `make acceptance-microvm` / `make acceptance-ports`；Windows 本地的正式 PE、`scripts/acceptance-windows.ps1` 和两个仅验收用 Go 控制程序。具备其他 Win11 版本/关闭的 WHPX 或真实 Key 时，在对应环境单独执行并更新矩阵。

完整本机日志保存在 `dist/runs/final-linux/evidence/`、`dist/final-linux-acceptance*.log`、`dist/windows-native-tests-final.log` 及 Windows 本地测试根。收集器 `scripts/acceptance-record.py` 仅复制允许的脱敏文件，排除凭证与 baseline 中的私密材料。未完成项在 tasks.md 保持未勾选。

补充：末轮两次外网重测的初始失败未保留具体 stderr，不能归因为已证实的网络原因；增加结构化诊断后，Windows 08:01 UTC、Linux 08:05 UTC 重测均通过。失败经历保留，不代替为从未失败的记录。

验收跟踪保留 5.1、8.1、8.2、8.4 未完成：Windows 最低版本/缺失 WHPX 的对应负例环境缺少，以及原版工具调用 Session 历史的已确认失败。8.5 的覆盖矩阵与 8.6 的本地产物核对完成，不代表上述环境或失败项通过。
