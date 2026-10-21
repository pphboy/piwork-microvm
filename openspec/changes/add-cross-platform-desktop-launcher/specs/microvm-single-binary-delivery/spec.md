# MicroVM Single Binary Delivery Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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

修复和双语修改后 SHALL 分别记录两平台真实 GUI 的默认英文、语言切换/恢复、完整日志及故障后 Launcher 诊断包保存结果；回归通过 MUST NOT 代替缺失的实机步骤。当前变更 SHALL 保持既有锁定上游输入，验收不得被宣称为后续上游升级后的最终整合结果。

#### Scenario: 在具备条件的平台真实验收
- **WHEN** 当前环境具备桌面与 KVM/WHPX
- **THEN** 实际运行最终 GUI 完成主路径、停止和再次启动，保存真实未启动/启动中/运行/错误窗口及原生操作结果，并记录实际平台、依赖和测试使用的文件身份

#### Scenario: 只有构建或自动化结果
- **WHEN** 某个平台未实际打开 GUI 或未从 GUI 启动 VM
- **THEN** 分别记录构建/自动化结果及未验证的桌面/VM 项，不能声称该平台端到端完成；没有窗口打开证明或存在主路径阻断时不声称整项 GUI 交付完成

#### Scenario: 修复后重新验收语言和故障导出
- **WHEN** 交付包含 C1/W1–W5 修复、双语及自身诊断能力的新 GUI
- **THEN** 保留旧记录原身份，并按新文件在两平台实际验证语言、取消、错误和取日志链路，打开导出包核对内容，未执行项仍标未验证

### Requirement: 双语用户说明的事实与验证边界一致

英文与简中 README、GUI 使用帮助、构建、排障和交付说明 SHALL 具有一致的功能事实、命令、构建/运行前提、端口、数据及日志位置、权限和已测/未测边界。说明 SHALL 明确首次固定英文、语言菜单及保存行为、原生日志保留技术原文、普通保存目录与完整导出、窗口不可用时自身诊断文件/系统错误获取方式，以及用户本地导出包后自行发给维护者；MUST NOT 描述不存在的上传服务。GUI 自有说明和操作名 SHALL 匹配所选语言，操作系统控制的原生文案边界 SHALL 明确说明。两种文档 SHALL 区分当前锁定输入的 GUI 阶段与后续独立上游升级，不将 `piwork-serve` 到 `piwork-core` 的适配冒充本变更已实现。

#### Scenario: 中英文用户执行同一流程
- **WHEN** 用户分别按英文或简中说明运行、切换语言、构建、排障或导出诊断
- **THEN** 得到相同的功能及边界，操作名称与相应 GUI 语言一致，均可找到实际日志来源和交付身份，不被引向上传地址或不存在的功能

#### Scenario: 说明已测环境与后续上游升级
- **WHEN** 说明列出 Windows/Linux 验收状态或上游入口
- **THEN** 两种语言均保留真实测试范围、当前 pin 和未测限制，当前 GUI 验收不会被写成后续独立升级的整合验收
