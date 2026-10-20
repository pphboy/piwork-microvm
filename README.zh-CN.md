# Piwork MicroVM

[English](README.md)

在一个 QEMU `microvm` Linux Guest 中运行原版 Piwork，使用 VirtIO-MMIO。
目标平台：Linux x86-64/KVM 与原生 Windows 11 Home x86-64/WHPX（从 21H2 起）。
Windows 运行不依赖 WSL、Docker Desktop 或 Hyper-V Manager。
[实现进度](openspec/changes/support-windows-and-disk-only-storage/tasks.md)中的
未勾选验收项尚未通过，不能视为已完成支持。

在 Linux 上构建，依赖 Docker Engine、Go 1.25.5、Git、Python 3、Make、Bash、
curl、qemu-img 和网络。容器提供内核/QEMU/MinGW 工具、Node 24 和 Guest Docker
28.5.2；输入由 `build.lock.json` 固定。

```sh
make source-refresh         # 显式解析官方默认分支最新 HEAD 并锁定
make source-check           # 检查独立、干净的固定源码副本
make piwork-microvm-all      # 两个平台产物
# 或分别执行 make piwork-microvm / make piwork-microvm-windows
```

普通构建使用 `dist/source/<commit>/piwork` 中固定的完整 commit，不应用 Piwork
补丁，拒绝修改过的输入。Server、WebUI、生产 Agent/Helper 使用同一上游发行身份，
package-helper 沿用上游 Agent 引用。`make source PIWORK_SOURCE=/path/to/piwork`
可以从本地 clone 获取已提交对象，不重置该工作区、不复制未提交文件。构建不推送、
不发布。文件系统 UUID/时间可能变化，不承诺整个产物逐字节重现。

只将匹配平台的完整产物复制到 Host：

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

Linux 当前用户须能读写 `/dev/kvm`。Windows 须启用固件虚拟化和 **Windows
Hypervisor Platform（Windows 虚拟机监控程序平台）**，并按系统要求重启。
无需新驱动、Host QEMU、Docker 或语言工具链。缺少硬件加速会报错，不回退机型或
TCG。至少预留 8 GiB 用于资源与初始数据，后续按 Work 增长增加空间。默认
2 vCPU/4096 MiB，可通过 `--cpus`、`--memory` 调整。

启动器输出 UI、Core API 地址、持久盘和过滤后的日志路径，日志包含实际 QEMU 参数。
只转发以下两个端口，所有 Host 监听仅用 `127.0.0.1`：

| 参数 | Host 默认端口 | Guest 端口 | 用途 |
| --- | --- | --- | --- |
| `--port` | 17891 | 17891 | UI、登录、管理、QuickStart 和 Service Proxy |
| `--core-port` | 17871 | 17871 | CLI/backend 的 Core API |

两个 Host 端口接受 1–65535 且必须不同。Service 通过 UI 同源
`/services/<workId>/<serviceId>/<port>/` 路径访问，不再预占或转发旧的 64 个端口。
浏览器 origin 跟随 `--port`，HTTP 80 的 origin 不带 `:80`。冲突明确报错，不结束
其他程序。正常停止后换端口保留原安装，请重新登录并打开 Service。
同时运行 Windows 与 Linux 版时，各自使用独立数据目录和不同的 UI/Core 端口；
同一数据盘始终只允许一个 VM 写入。

启动器自动打开访问地址。原版 Piwork 0.0.9 直接在浏览器创建首位管理员，随后正常
登录并完成 QuickStart。`--no-open` 禁止自动打开浏览器。API Key、密码、Token
不应出现在普通日志中。

`--data-dir` 是**完整安装根目录**。Linux 默认
`${XDG_DATA_HOME:-~/.local/share}/piwork-microvm`，Windows 默认
`%LOCALAPPDATA%\PiworkMicroVM`：

| 安装内路径 | 内容 |
| --- | --- |
| `installation.json` | 安装身份和初始化状态 |
| `disks/state.qcow2` | Guest ext4，保存全部业务与容器持久数据 |
| `logs/` | 过滤后的启动/Guest 诊断 |

qcow2 逻辑容量 64 GiB，随实际分配增长，没有外部 backing 文件。
`/mnt/state/core` 绑定到 `/var/lib/piwork/core`；Docker 使用 `/mnt/state/docker`，
含其管理的 containerd 和 local named volumes，`/var/lib/containerd` 也绑定到盘。
账号、模型配置、Work private/workspace/历史/Memory 和 Service 声明的持久数据
均在这里。RootFS 只读，使用临时 overlay；其他容器临时路径保持上游语义。

使用现有 **Piwork Files 上传/下载**。文件保存在盘内的普通 Work workspace 卷。
首版不提供 Host 目录共享、映射盘或文件同步。

保持启动器前台运行，按 **Ctrl+C** 并等待确认 Guest 正常停止，再一起备份
`installation.json` 与 `disks/state.qcow2`。不要运行时挂载磁盘，不把运行中的复制
称为一致备份。关闭窗口、系统关闭期限或强杀可能无法确认正常停止，此时保留异常
标记供下次启动提示。缺盘/坏盘不会被空盘替代，不覆盖不明非空安装目录。

系统资源单独存于用户缓存 `piwork-microvm/bundles/<hash>/`。正常停止后可删缓存，
下次从程序重新提取，保留原安装。启动时不构建或下载 Guest。组件构建入口为
`make guest`、`make qemu`、`make qemu-windows`；`make boot-dev` 是显式选用
外部 QEMU 的开发入口。

验收使用当前最终产物、独立全新 `--data-dir`，以及现有 Linux/KVM 和原生 Windows
Home/WHPX。更换数据目录验证空安装，不代表清空宿主依赖或资源缓存。本版按用户
确认移除 Windows 多版本矩阵和第二台干净电脑验证门槛。

当前构建使用原版 Piwork **0.0.9**，commit 为 `a6c36da16ebc`。真实模型调用、重启历史
和最终产物异常恢复结果见
[收尾验收](openspec/changes/support-windows-and-disk-only-storage/evidence/completion-acceptance.md)。
[双入口验收](openspec/changes/support-windows-and-disk-only-storage/evidence/two-port-acceptance.md)与
[此前 0.0.8 验收](openspec/changes/support-windows-and-disk-only-storage/evidence/acceptance.md)
保留各自原始测试范围和结果。

另有合成 OpenAI Responses 夹具在工具 ID 为 `call-1|fc-1` 等形式时复现历史 HTTP 503。
该样本的 Run 和原始历史/Memory 已持久化，但历史读取失败。此项保留为特定样本的
已知异常，不能泛化为所有工具会话失败；真实供应商结果单独记录实际模型和协议。
Piwork 业务源码保持未修改。Windows 实测环境为原生 Windows 11 Home build 26200，
不据此声称所有 Windows 版本均已验证。

Linux 验收入口为 `make acceptance-microvm`，需要真实 KVM、用于外围隔离的 Docker、
以及测试用 Playwright/Chromium。空运行根中只有最终文件和其解压资源；测试工具在根
外执行。`make acceptance-ports` 在独立网络命名空间测试端口，不停止原 Host 7171 服务。

Windows 验收使用原生 Edge、原生 Node 作为测试工具。用 `GOOS=windows GOARCH=amd64
 go build` 编译 `cmd/acceptance-windows` 和 `cmd/acceptance-guest-windows`，将它们、
测试脚本/fixtures、`dist/piwork/images.json`、Node 和 Playwright 复制到 Windows 本地
测试目录。运行 `scripts/acceptance-windows.ps1 -Root <目录> -Port 8080 -Phase first`
验证已启动的正式 PE；Core 使用自定义端口时增加 `-CorePort <端口>`。
`-Phase recovery` 验证已有基线，`-Phase failures` 要求停止
测试安装。额外 Guest 检查程序持独占锁准备合成模型夹具和检查挂载，单独记录，
不代替正式 PE 启动验收，不打包进产品文件。用户启动产品无需这些测试工具。
