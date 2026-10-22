# microvm-guest-runtime Specification

## Purpose

定义 Linux 与原生 Windows 共用的 Piwork Guest 首发契约：从最新干净上游源码构建完整服务和容器镜像，以本地 ext4 数据盘运行真实 Work，并通过现有浏览器界面操作文件和 Service。

## Requirements

### Requirement: 从最新干净上游源码锁定构建输入

构建准备 SHALL 明确选择源码构建或官方发行制品导入，并锁定实际源码完整 commit 与解析时间；正常重建 MUST NOT 自动跟随 main、标签或下载内容的变化。源码模式 SHALL 使用锁定提交的干净副本，不应用本项目的 Piwork 补丁、不继承脏输入、不修改相邻工作区。官方制品模式 SHALL 同时锁定官方仓库、发行标签、实际构建提交、发布提交、资产地址/大小/SHA256、来源元数据校验和及生产镜像身份，导入原版 Linux amd64 Core/CLI；输入失败 MUST NOT 静默回退到源码编译或旧版本。用户运行最终产物时 MUST NOT 拉源码、刷新分支、编译或下载内置运行依赖。

本次输入 SHALL 为 Piwork `v0.0.12` Preview，实际构建提交 `4f127751fc4805e504a1af0d7b48c02739f72489`，发布提交 `c4ce9bbd8fea9d990979332e57b61876cda20da2`。两个提交 SHALL 分别记录，程序版本与构建提交 SHALL 保留上游真实值，不将发布提交写成二进制构建身份。 native-v2 元数据 SHALL 从 `nativePrograms` 获取程序身份与摘要、从发行清单获取完整镜像身份，独立解析官方 Git 标签确定未在原始资产中声明的发布提交，并记录其来源；MUST NOT 改写下载的元数据或程序字节。准备结果的只读检查 SHALL 比较完整资产、程序/UI、镜像引用/digest/image ID/协议与锁定来源身份，不仅检查资产摘要和 image ID。

#### Scenario: 最新源码与可复现重建
- **WHEN** 实施准备批准的上游输入，随后另一构建按锁定记录重建
- **THEN** 使用相同输入模式和实际源码身份；源码模式使用干净锁定副本，官方模式使用相同 SHA256 的发行资产，不因 main 或远端标签前进而改变

#### Scenario: 构建目录残留修改
- **WHEN** 原有源码副本含本地补丁、未声明改动或与实际构建提交不符
- **THEN** 构建拒绝该输入或创建独立干净副本，不将它标为原版，也不重置其他工作区

#### Scenario: 官方构建提交与发布提交不同
- **WHEN** 0.0.12 官方标签指向 `c4ce9bbd8fea9d990979332e57b61876cda20da2`，而归档及程序报告 `4f127751fc4805e504a1af0d7b48c02739f72489`
- **THEN** 两者按锁定来源分别验证和呈现，包装层上游版本输出关联实际构建提交，不重写原版程序身份

#### Scenario: 官方资产或身份校验失败
- **WHEN** 下载不完整、大小/SHA256 不符、程序平台/版本/提交/原版状态或嵌入 UI 身份与锁不符
- **THEN** 导入失败，未验证内容不成为有效构建输入，不覆盖上一份有效输入，不生成冒充 0.0.12 的 Guest 或发行文件

#### Scenario: 锁定身份变化而准备文件未变化
- **WHEN** 镜像 digest/引用/协议、程序/UI 身份或资产记录等锁定字段变化，但准备输出字节未改变
- **THEN** 只读检查拒绝旧准备记录，不能复用或通过发布输入门槛，且不写入或下载文件

#### Scenario: 官方归档含不安全路径
- **WHEN** 官方制品输入的归档存在路径越界、重复目标、链接、特殊文件或超出导入边界的内容
- **THEN** 导入拒绝该归档，不能写出暂存目录或执行其中的非预期程序；只有通过完整性和结构校验的目标程序可进行版本检查

### Requirement: 交付完整且身份一致的 Piwork 运行资源

Guest SHALL 包含既有 Linux kernel、RootFS/init、Docker Engine/containerd/runc、证书、原版 `piwork-core` / `piwork-cli`、嵌入 WebUI、生产 Agent、package-helper、file-helper、snapshot-helper 和必要资源。Core SHALL 继续作为 Guest 原生二进制启动，使用 `--ui-port`、`--core-port`、`--data-dir`，保留持久数据位置和停止语义，不传递旧入口参数，也不为导入二进制而改为 Core 容器运行。

Core 与生产依赖 SHALL 来自同一锁定实际构建身份，校验版本、完整 commit、原版状态、资源及协议身份。官方模式 SHALL 按锁定 registry digest 取得配套镜像，核对 image ID、Linux amd64、身份/协议标签及其中程序的版本，再将所需镜像和原版 Core 引用一起内嵌。必要镜像 SHALL 能从内置资源准备，不依赖 Host Docker 或运行时在线拉取；不强改版本、不把旧镜像重标记为新版本，也不依赖标签的可变解析结果。

#### Scenario: 离线准备内置依赖
- **WHEN** 新安装启动，Guest Docker 中尚无 Piwork 镜像
- **THEN** Guest 从内置资源加载匹配的生产镜像并验证身份，不要求用户运行 Docker 命令或下载 Guest

#### Scenario: 镜像身份不符
- **WHEN** Core 引用与 Agent/Helper 的 digest、image ID、实际构建身份或协议不匹配
- **THEN** 构建或运行准备明确失败，不静默采用历史标签或验收专用 Agent

#### Scenario: 新 Core 入口启动
- **WHEN** 使用锁定 0.0.12 官方制品构建的 Guest 启动 Piwork
- **THEN** 原版 Core、Desktop、Guest Docker 和内置生产依赖可用，日志及版本关联实际构建提交，既有 Host UI/Core 入口与安全停止继续生效

#### Scenario: 官方标签被重新指向其他镜像
- **WHEN** 同名官方镜像标签对应了与锁定 digest 或 image ID 不同的内容
- **THEN** 只允许使用已核验的锁定镜像；不能接受新标签内容、跳过校验或用本地旧镜像冒充新输入

#### Scenario: Core 原生运行与生产容器分工
- **WHEN** 检查最终 Guest 的进程与镜像准备结果
- **THEN** Core 由既有 Guest 服务启动为原生进程，Agent/Helper 与 Service 使用 Guest Docker；最终产物不因导入官方包而要求 Host Docker 或额外暴露端口

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

### Requirement: 从原版 Desktop 管理员入口取得故障日志包

GUI SHALL 继续通过系统浏览器打开 Guest 中原版 Desktop。有效管理员 SHALL 能从其账户菜单唯一的 `Export logs` 入口创建、观察并下载原版 ZIP 到 Host，无需终端或宿主目录共享；应用 MUST NOT 新增另一业务日志入口、上传服务或改变上游授权。下载请求 SHALL 沿现有 WebUI 同源路径通过两个既有 Host 入口完成，不额外发布端口。

ZIP SHALL 保留上游 Core 与管理员所属 Work/Service 的日志范围、脱敏及缺口表达。浏览器开始下载 MUST NOT 被描述为本地保存完成；实测 SHALL 打开已保存 ZIP 核对来源、受控故障标记、敏感值过滤和可观察的缺口，不将 Launcher 的运行日志当作业务故障包。

#### Scenario: 可控故障的实际浏览器导出
- **WHEN** 专属 Guest 内真实 Work/Service 产生已知故障，管理员在 Desktop 账户菜单导出日志
- **THEN** Host 获得可打开的 ZIP，包含相关 Core/应用诊断及正确来源标识，已知测试凭据不泄漏，导出不额外停止或重新创建 Work

#### Scenario: 可控来源缺口
- **WHEN** 专属测试安装中一个日志来源按上游支持的故障条件变为不完整
- **THEN** Desktop 与已下载包的清单如实显示缺口及部分结果，不用空日志或 HTTP 成功冒充完整收集，也不要求真实模型调用
