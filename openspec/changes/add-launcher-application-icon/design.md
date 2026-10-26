# Design

## Context

动机见 `proposal.md`。当前 GUI 使用 Wails v2.17.0，`main_desktop.go` 设置 `Frameless: true`，Header 已引用内嵌的 `frontend/assets/piwork-logo.png`。图源为 1254×1254 RGBA PNG，来源与许可记录在 `ui-sources.json`，不需要生成新的品牌图片。

`scripts/gui-build.py` 与 `scripts/gui-build-windows.ps1` 都直接调用 `go build`，没有执行 Wails CLI 的图标打包。锁定 Wails 的 Windows 窗口从 PE 的图标组资源 ID 3 加载图标；Linux 支持通过 `linux.Options.Icon` 接收 PNG 字节。现有 bundle 在 GUI 主体编译后追加 payload、manifest 与 Trailer。

`scripts/bundle.py` 的 `source_fingerprint` 和 PowerShell 的等价计算目前仅覆盖 Go 文件与模块文件，未包含内嵌前端、Logo 以及构建配方。仅替换 Logo 时，旧 Windows 主体仍可能被错误接受。

## Goals / Non-Goals

**Goals:**

- 用一个受版本控制的品牌图源供应 Header、Linux 窗口和 Windows PE 图标；无需运行时外部图片。
- 两个 Windows 构建入口共用图标生成规则，并能验证最终单文件中的资源和 Trailer。
- 修正 GUI 主体输入覆盖范围，保持 Python 与 PowerShell 的指纹算法一致。

**Non-Goals:**

- 不引入托盘、安装器、桌面注册、额外系统标题栏或上游 Piwork WebUI 图标修改。
- 不修改 Guest、CLI 行为和发行流程；无需重跑真实模型、Work/Files/Service 或全部 VM 故障矩阵。

## Decisions

### 1. 单一 PNG 来源，派生文件不作为第二份品牌源维护

保留现有 PNG 和来源许可记录。Windows 从该 PNG 生成 16、32、48、64、128、256 像素图层，保持完整方形画布、宽高比和透明度；不裁剪或重新绘制现有图形。生成的 ICO/COFF 资源放入受忽略的构建目录，加入编译所需的临时 `.syso` 在失败或成功后都清理，不提交二进制中间资源。

选择已有锁定模块 `github.com/leaanthony/winicon v1.0.0` 与 `github.com/tc-hib/winres v0.3.1` 实现一个共享 Go 构建工具，两个 Windows 构建脚本均调用它。若成为直接导入依赖，按实际用途调整 go.mod 声明但保持版本锁定。相较手工保存 ICO 或在两种脚本各写转换逻辑，共享工具能避免图源漂移，且不需要新增 Python 图像包或独立系统工具。

### 2. Windows 在编译主体前嵌入图标资源

共享工具生成 Windows amd64 COFF `.syso`，将图标组标识设为锁定 Wails 实际加载的 ID 3，同时携带各尺寸图层。两个构建入口在 `go build` 前放置受管理的临时资源，成功后先记录主体，再按现有流程追加 bundle；不可在最终单文件上补图标。

临时文件名仅属于 Windows amd64，避免 Linux 编译误取；存在非本次生成的同名文件时明确失败，不覆盖用户资源。构建结束和异常退出都清理自有中间文件，不遗留影响后续构建的资源。图源解码或资源生成失败直接停止，不回退到旧资源。

相比迁移整个项目到 `wails build`，此方案保留现有版本注入、入口隔离和 bundle 处理。相比程序启动后调用 Win32 临时设置图标，PE 资源还能服务资源管理器图标与 Wails 原有加载路径。

### 3. Linux 读取同一内嵌 PNG，并保持现有窗口设置

从已有 `embedded` 文件系统读取同一 Logo，配置 `options.Linux.Icon`；设置稳定的 `ProgramName` 便于桌面环境识别。显式保留当前有效 GPU 策略 `WebviewGpuPolicyNever`：当前 Linux 选项为 nil 时 Wails 默认禁用 GPU，新增非 nil 选项不可意外切换为零值 `OnDemand`。尺寸、透明度、关闭流程和 Frameless 保持现状。

Header 继续使用原有相对资源路径，不添加第二枚标识或系统标题栏。读取内嵌图源异常时报告初始化错误，不悄悄省略图标。

Linux GTK 设置窗口图标不等于给裸 ELF 设置文件图标；Wayland 或特定桌面可能优先依赖 `.desktop` 注册。README 双语说明明确该限制并记录实测桌面会话，不新增安装/导出图标命令来扩大范围。

### 4. GUI 输入指纹覆盖品牌资源与构建配方

为 GUI 主体定义明确的额外输入集：`cmd/piwork-launcher/frontend/` 的内嵌文件、`ui-sources.json`、共享图标工具源码及 `gui-build.py` / `gui-build-windows.ps1` 等实际资源生成配方。在现有 Go/模块输入的基础上按相对 POSIX 路径排序，以统一的路径、NUL、内容 SHA256、换行格式计算；Python 与 PowerShell 完全一致。

指纹排除生成的 `.syso`、ICO、dist、OpenSpec 和运行状态，避免清理中间文件后主体记录自行失效。CLI 不纳入 GUI 专有资源输入。缺失必要图源或配方直接失败；旧 GUI 记录因输入集改变失效并要求重建，不静默信任。用具体修改 Logo/前端/配方后拒绝旧主体的测试证明行为，避免只对脚本文本做匹配。

### 5. 聚焦验证资源、交付格式和真实系统入口

自动验证 PNG 可解码、派生 ICO 图层尺寸、PE 图标组 ID 及其图层可提取；验证图源缺失/损坏的失败路径，主体指纹变化和 Python/PowerShell 一致性。现有 `scripts/bundle_test.py` 承载主体记录与 Trailer 回归，共享工具配有直接验证资源输出的测试。保留 `go test ./...` 的无桌面构建条件。

最终两平台 GUI 产物检查版本和 Trailer；原生 Windows 检查资源管理器、任务栏、Alt+Tab、自绘 Header，Linux 记录桌面/显示协议并检查可用的窗口图标入口与 Header。图标验证可在未启动 VM 时完成，关闭空闲窗口即可；不因本次纯图标变更启动完整业务验收。实机不可得的项目如实标记未验证，静态资源检查不能代替实机通过。

## Risks / Trade-offs

- [原 PNG 留白在 16 像素时降低辨识度] → 先保留原图与比例并核对实际小尺寸效果；本次不擅自重新设计或裁剪品牌。
- [Windows Shell 缓存旧图标] → 用新路径的当前产物进行观察，并对 PE 内资源提取比对，区分缓存与构建缺陷。
- [Linux 桌面忽略窗口内嵌图标] → 记录桌面与 X11/Wayland 会话，明确 `.desktop` 依赖边界；不宣称所有桌面都已覆盖。
- [临时 `.syso` 残留或双入口算法漂移] → 统一资源工具、严格所有权及清理、跨入口指纹比较与编译失败后的清理验证。
- [GUI 输入范围改变使旧主体记录过期] → 要求重建受影响 GUI 主体，无需重新构建未变化的 Guest、Kernel 或 QEMU。

## Migration Plan

按任务顺序接入资源工具、窗口配置、两个构建入口与主体复用校验，重建两平台 GUI 主体后封装本地最终产物，再完成聚焦验证及双语说明。无需数据迁移、重新安装 Guest 或发布 Release。回退时恢复旧构建/窗口配置并重建主体和 bundle，保留用户数据与原有独立 CLI 产物。
