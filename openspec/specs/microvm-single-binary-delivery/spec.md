# microvm-single-binary-delivery Specification

## Purpose

定义 Linux ELF 与原生 Windows PE 两种自包含分发产物，确保一个程序包含启动 Piwork 所需的完整运行资源。通过可信缓存、可复现输入及分平台真实验收，区分设计目标、实际通过项和未验证条件。

## Requirements

### Requirement: 分平台交付自包含可执行文件

最终 SHALL 交付 `dist/piwork-microvm` Linux x86-64 ELF 和 `dist/piwork-microvm.exe` Windows x86-64 PE。每个文件 SHALL 内含对应平台的 QEMU、所需非系统运行库/固件，以及 Guest kernel、RootFS、持久盘模板、Piwork 和生产镜像。Host SHALL 无需预装 QEMU、Docker、Go、Node、Python、源码或附加挂载驱动。

#### Scenario: 仅复制一个产物启动
- **WHEN** 用户将匹配平台的产物复制到满足 KVM/WHPX 前提、端口和资源可用的 Host 并执行
- **THEN** 自动准备内含资源并启动完整 Piwork，不要求执行构建、安装 QEMU 或运行 Docker 命令；首次业务设置仍由用户在原 QuickStart 完成

### Requirement: 原子提取和复用可信缓存

资源 SHALL 按平台、包身份和完整性校验提取到当前用户受管缓存，并原子发布。Windows SHALL 使用适当 ACL，Linux SHALL 使用适当权限。归档路径、链接或重解析行为 MUST NOT 导致写出缓存边界；损坏/中断提取 SHALL 可恢复，但不能覆盖用户数据盘。

#### Scenario: 首次和后续启动
- **WHEN** 首次缓存为空，随后重复启动相同产物
- **THEN** 首次提取，后续复用有效缓存，不重新构建 Guest，也不重新初始化数据盘

#### Scenario: 损坏缓存和恶意归档路径
- **WHEN** 缓存损坏、并发提取、提取中断或资源路径试图越出边界
- **THEN** 只重建可重建资源或安全失败，不执行未验证程序，不改写边界外文件或持久数据

### Requirement: 提供可复现输入和真实来源身份

构建 SHALL 锁定实际 Piwork commit、工具链、Guest 依赖、QEMU 和运行库/固件来源及校验，记录原版源码状态、UI 输入 hash、生产镜像身份、产物 hash 和必要许可证。构建流程 SHALL 不推送镜像、远程仓库或发布 Release。

#### Scenario: 审核并重建两个产物
- **WHEN** 开发者按仓库构建入口和锁定清单重建
- **THEN** 可以取得同一依赖组合，验证源码没有 Piwork 补丁、Server/镜像身份一致，并分别核对 ELF 与 PE 的资源清单

### Requirement: Windows 运行链路独立于 WSL

Windows 最终产物 SHALL 从 Windows 本地文件系统使用原生 QEMU/DLL、WHPX、控制通道和数据路径。构建工具可以运行于 Linux/WSL，但运行 MUST NOT 调用 `wsl.exe`、Linux ELF 或依赖发行版路径、WSL 网络转发和 WSL 内的 Docker/QEMU。

#### Scenario: 核实原生依赖
- **WHEN** 从 Windows 本地终端启动最终 EXE 并检查进程、加载模块、资源和磁盘路径
- **THEN** 观察到独立的 Windows 运行链路及 WHPX，源仓库、开发工具和 WSL 发行版不是启动依赖

### Requirement: 真实验证两平台 Happy Path

验收 SHALL 使用当前最终产物和独立全新 `--data-dir`，在真实 Linux/KVM 和当前原生 Windows 11 Home/WHPX 上分别验证 microvm、Guest Docker、QuickStart、真实模型请求及工具调用、Work、Files 上传下载、Service HTTP/WebSocket/流式连接、Guest/Work 联网、正常停止、二次启动和清缓存恢复。代码审查、mock、交叉编译成功、TCG 或旧实验记录 MUST NOT 代替实际运行证据。

#### Scenario: 完成并记录平台验收
- **WHEN** 对某一平台声明 Happy Path 通过
- **THEN** 可关联最终产物 hash、源码 commit、QEMU 及加速器、Guest、Work/Service、文件哈希和重启结果，且实际无目录共享设备或服务

#### Scenario: 真实模型和工具历史跨重启
- **WHEN** 在两平台独立新安装中配置真实模型，在 Work 发起请求并通过工具产生可核对的文件及结果，正常停止后以原盘重新启动
- **THEN** 原账号/模型/Work、Files 和 Service 数据保持，工具会话历史读取 HTTP 200，并能在原会话继续一次真实模型请求；证据记录模型/协议、Run、工具结果和产物身份且不泄漏凭证

### Requirement: 如实报告版本覆盖和外部限制

验收 SHALL 记录当前 Linux/KVM 与 Windows Home/WHPX 的实际环境和结果。本轮 SHALL 使用独立全新 `--data-dir` 验证新安装，不要求 Windows 多版本矩阵、额外禁用主机虚拟化环境或第二台干净电脑，不将这些已取消的验证列为交付阻塞项。空数据目录 MUST NOT 被描述为宿主系统依赖或资源缓存已清空；自包含和原生运行要求继续生效。合成模型测试 SHALL 与真实供应商请求分开记录，单一夹具失败不得泛化为所有模型或会话不可用。

#### Scenario: 使用现有主机完成验收
- **WHEN** 两个平台在当前主机使用各自新数据目录执行真实模型、正常重启和异常退出恢复验收
- **THEN** 记录实际平台、最终产物与原盘恢复证据，按各项真实结果标记通过或失败，不等待额外电脑或 Windows 版本环境，不伪造真实模型成功

#### Scenario: 部分验收环境不可得
- **WHEN** 没有其他 Windows 版本或第二台干净主机
- **THEN** 按已确认范围使用现有两平台及独立空安装完成本轮验收，不将已取消的环境要求列为阻塞项或伪造为实测通过；真实模型请求失败或缺少可用凭证仍如实记录
