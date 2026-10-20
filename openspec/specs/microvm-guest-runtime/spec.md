# microvm-guest-runtime Specification

## Purpose

定义 Linux 与原生 Windows 共用的 Piwork Guest 首发契约：从最新干净上游源码构建完整服务和容器镜像，以本地 ext4 数据盘运行真实 Work，并通过现有浏览器界面操作文件和 Service。

## Requirements

### Requirement: 从最新干净上游源码锁定构建输入

构建准备 SHALL 从官方远程解析实施时默认分支的最新 HEAD，将完整 commit 和解析时间写入构建锁定记录，再以该 commit 构建。正常重建 SHALL 使用锁定输入；用户运行产物时 MUST NOT 拉源码、刷新分支或编译。构建 SHALL 不应用本项目的 Piwork 补丁，不继承脏源码副本，不修改相邻 Piwork 工作区。

#### Scenario: 最新源码与可复现重建
- **WHEN** 实施首次准备源码，随后另一构建按已生成的锁定记录重建
- **THEN** 首次选择当时远程默认分支的最新完整 commit，后续使用相同 commit，均记录真实源码身份且没有应用 Piwork 补丁

#### Scenario: 构建目录残留修改
- **WHEN** 原有源码副本含本地补丁、未声明改动或与锁定 commit 不同的内容
- **THEN** 构建拒绝该输入或创建独立干净副本，不将它标为原版，也不重置其他工作区

### Requirement: 交付完整且身份一致的 Piwork 运行资源

Guest SHALL 包含 Linux kernel、RootFS/init、Docker Engine/containerd/runc、证书、Piwork 统一 Linux 入口及嵌入 WebUI、生产 Agent、package-helper、file-helper、snapshot-helper 和必要资源。Server 与镜像 SHALL 使用同一锁定源码和发行身份，Guest 中必要镜像 SHALL 可以从内置资源准备，不依赖 Host Docker。

#### Scenario: 离线准备内置依赖
- **WHEN** 新安装启动，Guest Docker 中尚无 Piwork 镜像
- **THEN** Guest 从内置资源加载匹配的生产镜像并验证身份，不要求用户运行 Docker 命令或下载 Guest

#### Scenario: 镜像身份不符
- **WHEN** 内置 Server 引用与 Agent/Helper 的镜像身份或协议不匹配
- **THEN** 构建或运行准备明确失败，不静默采用历史标签或验收专用 Agent

### Requirement: 支持真实容器和 VirtIO-MMIO

Guest SHALL 支持本交付使用的 VirtIO-MMIO 块设备、网络、串口控制、ext4，以及 Docker 所需 namespaces、cgroups、overlayfs、veth、bridge、DNS、NAT 和过滤能力。Docker SHALL 在 Guest 内实际管理容器及持久卷，不借用 Host Docker socket。

#### Scenario: Guest Engine 创建真实容器
- **WHEN** Guest Engine 创建一个使用持久卷及独立网络的容器
- **THEN** 容器真实运行、读写卷、解析域名并访问外部 HTTPS，实际存储位于 Guest ext4

### Requirement: Guest 启动不依赖宿主目录共享

Guest 的启动和 Piwork 功能 MUST NOT 依赖 Host 目录挂载、9P、SMB、FUSE、映射盘或文件同步。首版 SHALL 保留上游原有 workspace 布局，通过 Piwork Files 交换文件，不注入专用共享子目录。

#### Scenario: 没有共享设备仍可使用 Piwork
- **WHEN** VM 只连接只读系统资源、持久块设备、网络和私有控制设备
- **THEN** Guest 能启动 Docker 与 Piwork，并创建真实 Work、上传和下载文件、运行 Service，不因缺少共享设备或 Host xattr 能力而失败

### Requirement: 按持久存储和依赖状态启动

Guest SHALL 依次确认 RootFS/init、ext4 持久盘、网络、Docker、生产镜像和 Piwork 启动状态，并提供不含秘密的阶段诊断。持久盘未正确挂载时 MUST NOT 在临时根文件系统建立替代安装。

#### Scenario: 持久盘不可用
- **WHEN** 数据盘缺失、挂载失败或身份校验失败
- **THEN** Guest 报告具体存储阶段错误并停止依赖服务，不启动空白替代 Piwork

### Requirement: 保持原有 Work 和 Service 语义

Guest SHALL 保留上游 Work 身份、private/workspace 卷、历史、文件权限、Service 授权、删除留存和显式清理语义；MUST NOT 修改 Piwork 业务源码、契约或 UI 来适配虚拟机。

#### Scenario: 创建和管理 Work
- **WHEN** 用户完成原有 QuickStart 后创建并启动 Work，使用 Files 和获准 Service
- **THEN** 原版 Agent、文件和 Service 使用上游定义的卷及授权边界，停止后保留上游约定的持久数据
