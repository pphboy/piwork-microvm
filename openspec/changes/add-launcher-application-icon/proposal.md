# Proposal

## Why

Launcher 的自绘标题栏已经使用本地 Piwork Logo，但 Windows 可执行文件未嵌入应用图标，Linux 窗口也没有配置图标，导致系统任务栏与窗口切换入口缺少一致的品牌标识。用户确认沿用现有 `piwork-logo.png`，需要补齐应用与窗口层面的图标。

## What Changes

- 以 `cmd/piwork-launcher/frontend/assets/piwork-logo.png` 为唯一品牌图源，派生 Windows 多尺寸 ICO，保留现有自绘标题栏 Logo。
- Windows GUI 编译时嵌入供资源管理器与 Wails 窗口加载的图标；Linux GUI 使用内嵌 PNG 配置原生窗口图标，覆盖受支持桌面环境的任务栏与窗口切换入口。
- 两条 Windows GUI 构建入口使用一致的资源生成流程，资源处理全部发生在追加 bundle 和 Trailer 之前；图标输入变化能够使过期 GUI 主体记录失效。
- 增加图标资源与最终 GUI 产物的聚焦验证，维护双语说明中的平台边界。
- 本次不增加系统托盘、安装器、自动快捷方式注册或原生系统标题栏，不承诺 Linux 文件管理器为裸 ELF 显示自定义图标。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `microvm-desktop-launcher`: 增加应用、原生窗口与现有自绘标题栏统一使用本地 Piwork Logo 的行为要求及平台边界。
- `microvm-single-binary-delivery`: 增加图标随 GUI 单文件携带、构建入口一致、资源处理顺序和图标输入失效检查的交付要求。

## Impact

- `cmd/piwork-launcher/main_desktop.go` 的平台窗口选项；现有 Header 与 Logo 资源保持同源。
- `scripts/gui-build.py`、`scripts/gui-build-windows.ps1` 及新增的共享 GUI 图标资源生成工具；优先复用锁定依赖中已有的 `winicon` / `winres`，不增加运行时依赖。
- `scripts/bundle.py` 与 Windows 主体记录的源码输入指纹、相关构建检查、双语 README 和本变更验收记录。
- CLI、Guest、虚拟机生命周期、磁盘布局和发布入口不变；不自动发布或推送。
