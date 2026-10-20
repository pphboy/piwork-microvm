# Proposal

## Why

首发需要在 Linux 和 Windows 11 Home 上分别运行一个程序，就能启动真正的 Piwork MicroVM，并保留账号、Work、文件与 Service 数据。采用 Guest ext4 持久盘和 Piwork 现有上传下载，可以先完成这一目标，把宿主目录共享留到后续版本，减少平台、驱动及文件系统兼容工作。

## What Changes

- 提供 Linux x86-64 ELF `dist/piwork-microvm` 和原生 Windows x86-64 PE `dist/piwork-microvm.exe`。分别使用 KVM、WHPX，均启动一个 QEMU `-M microvm` VM，使用 VirtIO-MMIO，不以其他机型、TCG 或宿主 Piwork 静默替代。
- Windows 兼容目标从 Windows 11 Home 21H2 起，不依赖 Pro 专属管理功能、WSL、Docker Desktop 或 Windows 11 24H2 新增的 SMB 功能。当前已启用的 Windows Hypervisor Platform 作为系统前提，launcher 检查实际能力。
- 从官方远程最新默认分支获取 Piwork。实施首次构建时重新解析 `main` 并锁定完整 commit；本次只读确认的 HEAD 为 `a6c36da16ebcc0e96f0e34ef820d857f2bea4877`。Server、WebUI、生产 Agent/Helper 均从同一干净源码身份构建，不应用 Piwork 补丁，不在用户启动时拉源码或构建。
- 两平台共用 Linux Guest 配方和磁盘布局。所有持久业务数据、Docker/containerd 内容和 named volumes 写入 Host `disks/state.qcow2` 内的 ext4；只读 RootFS 与可重建缓存不承担用户持久数据。
- **BREAKING（当前开发实现）**：删除 9P 设备、Guest 共享挂载、共享目录探测、专用 Piwork/QEMU 补丁和共享相关构建依赖。首版不提供 SMB、FUSE、映射盘或文件同步；通过原有 Piwork Files 上传和下载。
- **BREAKING（当前开发实现）**：`--data-dir DIR` 统一定义为完整安装的数据根目录，包含安装身份、持久盘和日志，不再表示直接共享文件目录。按首次发布定义新安装行为，不设计已发布版本兼容、9P 安装识别或自动迁移；一般的数据保护仍禁止覆盖未知内容或重建已有坏盘。
- 保留 `--port`（UI 默认 17891），新增 `--core-port`（Core API 默认 17871），以及 `--cpus`、`--memory`、`--no-open`、`--help`。自动准备资源、检查独占锁与端口、等待真实启动状态、打开原版首次引导入口并正常关闭；默认只转发回环地址上的 UI 与 Core 两个入口，Work Service 通过 UI 同源 `/services/...` 路径访问，不预占旧端口池。跟随锁定的原版 0.0.9，直接在浏览器创建首位管理员并正常登录，不增加私有设置链接协议。
- 分别验收两个最终单文件产物，覆盖 QuickStart、真实模型及工具调用、Work/Service、Files 上传下载、DNS/出站、HTTP/WebSocket/流式连接、正常退出、重启及清缓存恢复。使用当前 Linux/KVM 与 Windows Home/WHPX 和独立全新 `--data-dir`，补齐 Guest 提前退出、关机超时、launcher 强杀后的原盘恢复。不推送远程、不发布 Release。
- 本轮取消 Windows 多版本测试矩阵、关闭主机虚拟化功能的额外环境准备及第二台干净电脑验证要求。全新 `--data-dir` 验证空安装，不能称为清空了宿主依赖；仍要求产物自包含并记录实际运行依赖。真实模型验收以实际请求、工具结果和重启后历史读取为准；合成夹具失败单独记录，不泛化为所有模型或会话不可用。

## Capabilities

### New Capabilities

- `microvm-guest-runtime`：最新原版 Piwork 的一致构建、无共享 Guest、容器能力和启动顺序。
- `microvm-launcher-lifecycle`：Linux/KVM 与 Windows/WHPX 原生启动、统一命令行、私有控制、独占及退出行为。
- `microvm-network-access`：NAT、回环端口、现有授权入口、Files 和真实 Service 的完整网络访问。
- `microvm-persistent-storage`：仅使用 qcow2/ext4 的数据目录、完整持久化、恢复和备份边界。
- `microvm-single-binary-delivery`：两平台自包含分发、可信资源提取、可复现输入和真实验收证据。

### Modified Capabilities

本变更制定时主规格为空，以上路径定义首发契约，现已同步过主规格。本轮继续修订本变更的验收范围；此前的实验变更不作为需兼容的产品版本，也不作为本次验收结果。

## Impact

- 改动归属本包装仓库的 `cmd/piwork-microvm/`、`cmd/piwork-guest/`、`internal/{launcher,bundle,qemu,network}/`、`guest/`、`scripts/`、`Makefile`、`build.lock.json` 和双语 README；上游 Piwork 仓库及业务源码不改动。
- 现有 launcher/bundle 带 Linux 构建限制，Unix sockets、flock、继承描述符和 Linux loader 不能直接用于 Windows，需要平台实现及 Windows QEMU/DLL/固件构建闭包。
- 复用最新上游的 `cmd/piwork-serve/`、WebUI、Docker local volumes 和现有构建/发行身份工具；不改变 Work/Service 生命周期、权限、卷语义、API 或 UI。
- 构建阶段可以使用容器、Go、Node、交叉编译工具和网络。运行阶段只要求受支持 Host、可用硬件加速及足够资源，不安装额外文件系统/网络驱动或新 Infra Daemon。
- 原生 Windows `microvm + WHPX`、中断/时钟及正常关机已在当前 Home 主机验证；本轮收尾要求最终产物的真实模型与异常退出恢复证据，Windows 结果必须来自原生 WHPX，不以 WSL/KVM 或旧产物记录代替。
