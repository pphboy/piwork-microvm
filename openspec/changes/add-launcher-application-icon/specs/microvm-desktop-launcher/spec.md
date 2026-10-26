# Spec Delta

## ADDED Requirements

### Requirement: 应用与窗口统一使用 Piwork 图标

GUI SHALL 沿用现有本地 `piwork-logo.png` 的图形作为应用和窗口图标，不另行设计或使用框架默认图标。Windows GUI 文件在资源管理器中的应用图标、运行时任务栏及窗口切换图标 SHALL 使用该 Logo；Linux GUI SHALL 为原生窗口提供该 Logo，供支持窗口图标的桌面环境在任务栏与窗口切换入口显示。自绘标题栏 SHALL 继续显示同源 Piwork Logo，保持现有名称、拖动区域、最小化及受保护的关闭操作，不额外叠加系统标题栏。全部图标 SHALL 离线可用，缩放时保持比例和透明背景，不拉伸或裁去 Logo 主体。

#### Scenario: Windows 文件与运行窗口图标一致
- **WHEN** 用户在原生 Windows 查看最终 GUI EXE，双击打开并查看任务栏和 Alt+Tab 窗口切换入口
- **THEN** 文件图标、运行窗口图标和自绘标题栏均可辨认为同一 Piwork Logo，小尺寸及高 DPI 下保持比例，不显示通用或框架默认应用图标

#### Scenario: Linux 窗口提供本地图标
- **WHEN** 用户在支持窗口图标的 Linux 桌面环境离线打开 GUI，并查看任务栏或窗口切换入口
- **THEN** 原生窗口提供内嵌 Piwork Logo，受支持入口与自绘标题栏显示同源图形，不依赖旁置图片或远程服务

#### Scenario: 标题栏操作保持可用
- **WHEN** 用户在 800×600 窗口拖动标题空白区，点击最小化或关闭
- **THEN** Logo 可见且不遮挡操作，窗口移动、最小化与既有安全关闭行为保持有效，没有新增原生标题栏

#### Scenario: Linux 桌面环境控制文件及应用入口图标
- **WHEN** Linux 文件管理器显示裸 ELF 文件，或桌面环境需要已注册应用入口才能显示品牌图标
- **THEN** 双语说明 SHALL 明确文件图标和应用入口由桌面环境及 `.desktop` 注册控制，本次不保证裸 ELF 的自定义文件图标，也不自动安装入口或修改用户桌面配置
