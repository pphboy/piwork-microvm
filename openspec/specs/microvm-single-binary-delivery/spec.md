# microvm-single-binary-delivery Specification

## Purpose

定义 Linux ELF 与原生 Windows PE 两种自包含分发产物，确保一个程序包含启动 Piwork 所需的完整运行资源。通过可信缓存、可复现输入及分平台真实验收，区分设计目标、实际通过项和未验证条件。

## Requirements

### Requirement: 分平台交付自包含可执行文件

最终 SHALL 保留 `dist/piwork-microvm` Linux x86-64 ELF 和 `dist/piwork-microvm.exe` Windows x86-64 PE，并增加桌面入口 `dist/piwork-microvm-gui` 与 `dist/piwork-microvm-gui.exe`。每个文件 SHALL 内含对应平台的 QEMU、所需非系统运行库/固件，以及 Guest kernel、RootFS、持久盘模板、Piwork 和生产镜像；GUI 另内含其全部前端及英文/简体中文资源，不依赖远程翻译或运行时语言下载。Host SHALL 无需预装 QEMU、Docker、Go、Node、Python、源码或附加挂载驱动。GUI 允许并 SHALL 明确声明系统桌面 WebView 前提：Windows WebView2、Linux GTK/WebKitGTK；这些前提不新增给 CLI，普通用户无需手工管理内部多个程序。

#### Scenario: 仅复制一个产物启动
- **WHEN** 用户将匹配平台和入口的产物复制到满足其桌面运行前提（GUI）、KVM/WHPX、端口和资源条件的 Host 并执行
- **THEN** 自动准备内含资源并启动完整 Piwork，不要求执行构建、安装 QEMU 或运行 Docker 命令；首次业务设置仍由用户在原 QuickStart 完成

#### Scenario: GUI 和 CLI 并存
- **WHEN** 分别构建或分发 CLI 与 GUI
- **THEN** 文件名、校验和和构建记录可区分两个入口，GUI 构建不会替换 CLI 文件或使 CLI 增加桌面系统依赖

#### Scenario: 离线首次打开和切换语言
- **WHEN** Host 无法访问语言/静态资源服务，用户首次打开 GUI 或切换英文/简中
- **THEN** 使用内置词条，无语言偏好时保持英文，界面和语言操作不依赖外网

### Requirement: 原子提取和复用可信缓存

资源 SHALL 按平台、包身份和完整性校验提取到当前用户受管缓存，并原子发布。Windows SHALL 使用适当 ACL，Linux SHALL 使用适当权限。归档路径、链接或重解析行为 MUST NOT 导致写出缓存边界；损坏/中断提取 SHALL 可恢复，但不能覆盖用户数据盘。

#### Scenario: 首次和后续启动
- **WHEN** 首次缓存为空，随后重复启动相同产物
- **THEN** 首次提取，后续复用有效缓存，不重新构建 Guest，也不重新初始化数据盘

#### Scenario: 损坏缓存和恶意归档路径
- **WHEN** 缓存损坏、并发提取、提取中断或资源路径试图越出边界
- **THEN** 只重建可重建资源或安全失败，不执行未验证程序，不改写边界外文件或持久数据

### Requirement: 提供可复现输入和真实来源身份

构建 SHALL 锁定实际 Piwork commit、工具链、Guest 依赖、QEMU 和运行库/固件来源及校验，记录原版源码状态、UI 输入 hash、生产镜像身份、产物 hash 和必要许可证。构建流程 SHALL 不推送容器镜像、远程仓库，也不自行发布 Release；容器镜像 MUST NOT 被推送到任何远程 registry。公开 Release SHALL 由独立于构建流程的发布步骤执行，其资产与对应源码义务由该步骤负责。

#### Scenario: 审核并重建两个产物
- **WHEN** 开发者按仓库构建入口和锁定清单重建
- **THEN** 可以取得同一依赖组合，验证源码没有 Piwork 补丁、Server/镜像身份一致，并分别核对 ELF 与 PE 的资源清单

#### Scenario: 区分构建流程与发布步骤
- **WHEN** 只执行构建流程，未执行独立发布步骤
- **THEN** 不产生任何远程推送、容器镜像发布或 GitHub Release，产物仅存在于本地

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

### Requirement: 随产物提供可读的第三方许可证文本

分发产物 SHALL 为 Guest 镜像内分发的每一类第三方组件提供可直接阅读的许可证文本，MUST NOT 要求启动 VM 才能取得。覆盖范围 SHALL 至少包含 Guest rootfs 内的全部已安装分发包、initramfs 中的 BusyBox、内核与 QEMU 及其随产物提供的运行库。许可证文本 SHALL 位于产物解压资源中可预见的路径，并以组件标识或来源包名定位。产物 SHALL 另附一份索引，列出每个组件、其来源包与对应的许可证文件；某个包确实无可提取文本时，索引 SHALL 如实标注该缺口，MUST NOT 静默省略。

#### Scenario: 无需启动 VM 即可阅读许可证
- **WHEN** 用户解压产物资源后查看许可证目录
- **THEN** 能按组件名找到每个已安装包的许可证文本，全程不需要启动 Guest

#### Scenario: 镜像内的分发包变化
- **WHEN** Guest rootfs 的安装包集合发生变化并重新构建产物
- **THEN** 许可证树与索引随之更新，新增包的文本出现在产物中，不再存在的包不再列出

#### Scenario: 某个包缺少可提取文本
- **WHEN** 某个已安装包没有 `/usr/share/doc/<pkg>/copyright`
- **THEN** 索引如实标注该组件缺少随附文本，不静默省略该包

#### Scenario: 提取过程不改动镜像
- **WHEN** 构建过程生成许可证树
- **THEN** 以只读方式读取镜像内容，不挂载、不修改 `rootfs.ext4`，也不需要 root 权限

### Requirement: GUI 构建隔离并保留文件尾资源格式

GUI SHALL 使用独立的桌面构建配置，不更改 CLI 的既有无 CGO 构建语义。桌面可执行主体完成编译及资源处理后 SHALL 附加现有校验资源和最终 Trailer，不能在追加后再执行会改变尾部定位的处理。最终 GUI SHALL 从自身可执行文件读取并校验 bundle，保留 build.lock、上游发行身份、包装层独立版本、资源清单和 SHA256 机制。Windows GUI 及其 QEMU 子进程 SHALL 不弹出多余控制台窗口。

#### Scenario: 最终 ELF 与 PE 读取内置资源
- **WHEN** 在各自平台运行最终 GUI 文件，且程序位于不同工作目录或包含空格/中文的本地路径
- **THEN** 从当前可执行文件正确读取 Trailer、校验并提取内置 Guest/QEMU 资源，不借用其他 CLI 的资源文件或要求用户执行准备命令

#### Scenario: 单独构建 CLI 或 GUI
- **WHEN** 分别执行已有 CLI 目标和新增 GUI 构建目标
- **THEN** 两者均可构建，各自配置、临时文件、资源清单及校验和不相互覆盖，普通 `go test ./...` 无需桌面开发库即可覆盖共享运行逻辑

### Requirement: 桌面依赖和来源可复核

桌面构建 SHALL 固定 Wails v2 稳定版本及依赖，保留所用前端和上游 UI 资源的来源记录与必要许可。说明 SHALL 区分构建开发包和运行系统库，记录实际验证的 Linux GTK/WebKitGTK 和 Windows WebView2 版本。缺少所需桌面运行组件 SHALL 明确失败，不静默转用其他前端、WSL 或外部 QEMU。

#### Scenario: 桌面前提可检查
- **WHEN** 用户按说明构建或运行 GUI
- **THEN** 可得知 GUI 特有的依赖及已测试组合，缺失组件得到对应诊断；不需要为 CLI 安装这些库

### Requirement: GUI 验收与 CLI 和历史证据分别记录

GUI 交付 SHALL 记录本次两平台构建、真实窗口、状态截图、原生操作、GUI 发起的硬件加速启动、健康检查、浏览器访问、安全关机及原盘恢复结果。记录 SHALL 区分锁定输入身份、本次 GUI 产物身份和实际运行证据，不把旧 CLI 结果或相同 Guest 输入自动升级为 GUI 通过。无法进行的真实平台验收 SHALL 保留未验证状态；模拟状态截图或静态 HTML 不能代替真实窗口运行。

修复和双语修改后 SHALL 聚焦 C1/W1–W5 针对性回归与两平台必要真实 GUI 验证，记录默认英文、语言切换/恢复、正常和错误时现有日志导出、一次安全停止及原盘复用；不要求重复无关全故障穷举或完整旧 CLI 发版矩阵。结果 SHALL 追加既有验收记录，历史证据保留原身份，不新建报告或长期清单；回归通过 MUST NOT 代替缺失的实机步骤。已归档桌面变更的证据 SHALL 保留当时锁定输入身份，不得被宣称为后续上游升级后的最终整合结果。

本次上游升级 SHALL 仅按批准范围补齐新输入的聚焦验收：两平台实际 GUI 启动新 Guest、浏览器打开原版 Desktop、唯一管理员入口导出可控 Work/Service 故障 ZIP 并打开核对日志/脱敏/缺口、英文默认与已有语言选择、真实安全停止及旧盘备份副本恢复。不要求真实 AI Key，不重跑不受修改影响的 GUI 全套、全部署或模型矩阵。构建 SHALL 沿现有 MicroVM 链路统一重建上游二进制、生产镜像、Guest 和两平台 GUI 内嵌资源，保留原 Trailer、许可证和输入校验，Kernel/QEMU 及发布体系不变；CLI 兼容只对受影响的入口/端口进行小范围证明。本次结果 SHALL 记录在本变更的验收记录，历史记录保留原身份，不另建通用报告或长期清单。

#### Scenario: 在具备条件的平台真实验收
- **WHEN** 当前环境具备桌面与 KVM/WHPX
- **THEN** 实际运行最终 GUI 完成主路径、停止和再次启动，保存真实未启动/启动中/运行/错误窗口及原生操作结果，并记录实际平台、依赖和测试使用的文件身份

#### Scenario: 只有构建或自动化结果
- **WHEN** 某个平台未实际打开 GUI 或未从 GUI 启动 VM
- **THEN** 分别记录构建/自动化结果及未验证的桌面/VM 项，不能声称该平台端到端完成；没有窗口打开证明或存在主路径阻断时不声称整项 GUI 交付完成

#### Scenario: 修复后重新验收语言和故障导出
- **WHEN** 交付包含 C1/W1–W5 修复、最小双语和现有错误日志导出的新 GUI
- **THEN** 保留旧记录原身份，并按新文件在两平台实际验证语言、必要安全退出和正常/错误取日志链路，打开导出包核对内容，未执行项仍标未验证

#### Scenario: 冻结上游的聚焦整合验收
- **WHEN** 从批准的精确 main 提交重建并验收两个 GUI 产物
- **THEN** 记录真实源码声明版本、完整 commit、dirty 状态、内嵌资源和缓存身份、实际 GUI/浏览器下载及停机副本恢复证据，不能以旧缓存或旧截图冒充升级通过；未测平台或步骤明确标识

### Requirement: 双语用户说明的事实与验证边界一致

英文与简中 README、GUI 使用帮助、构建、排障和交付说明 SHALL 具有一致的功能事实、命令、构建/运行前提、端口、数据及日志位置、权限和已测/未测边界。说明 SHALL 明确首次固定英文、语言菜单及保存行为、原生日志保留技术原文、普通保存目录与完整导出、GUI 已呈现启动错误经现有日志导出、OS 加载/Wails 初始化前失败沿用系统排障说明，以及用户本地导出后自行发给维护者；MUST NOT 描述不存在的独立早期诊断或上传服务。用户说明 SHALL 维护现有 README/帮助/构建与排障内容，不新建报告或长期清单，也不扩展发布流程。GUI 自有说明和操作名 SHALL 匹配所选语言，操作系统控制的原生文案边界 SHALL 明确说明。两种文档 SHALL 区分历史 GUI 阶段与本次冻结输入的上游升级，只有实际适配并验证后才描述 `piwork-core` 及其参数为当前实现；源码声明版本、开发构建身份和官方发行状态不得混淆。

本次现有双语 README、帮助、构建与排障说明 SHALL 同步精确本地输入、统一 MicroVM 构建方式、实际端口行为、旧盘停机备份边界及 Desktop 管理员账户菜单的 `Export logs` 下载流程。说明 SHALL 区分 Desktop 业务故障 ZIP 与 Launcher 本次/全部运行日志：Core 未启动时仍使用 Launcher 既有错误导出；不增加业务导出入口或上传服务，不改官方发行记录。

#### Scenario: 中英文用户执行同一流程
- **WHEN** 用户分别按英文或简中说明运行、切换语言、构建、排障或导出日志
- **THEN** 得到相同的功能及边界，操作名称与相应 GUI 语言一致，均可找到实际日志来源和交付身份，不被引向上传地址或不存在的功能

#### Scenario: 说明已测环境与后续上游升级
- **WHEN** 说明列出 Windows/Linux 验收状态或上游入口
- **THEN** 两种语言均保留真实测试范围、当前 pin 和未测限制，历史 GUI 验收不冒充本次上游升级的整合验收，本次结果只描述实际执行的升级范围

#### Scenario: 用户按新版说明取日志
- **WHEN** 用户在 Guest 已启动或无法启动时按任一语言的说明排障
- **THEN** 分别能找到 Desktop 的原版故障 ZIP 下载，或 Launcher 既有运行错误导出；已保存文件由用户自行发送，文档不承诺未验证的完整性、真实模型或平台覆盖
