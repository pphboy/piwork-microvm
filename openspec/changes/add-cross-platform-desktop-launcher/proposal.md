# Proposal

## Why

当前 MicroVM 已有 Windows/Linux 自包含 CLI 和完整的磁盘保护、启动及关机链路，但普通桌面用户仍需终端操作。增加符合 Piwork Desktop 风格的轻量桌面入口，使用户双击程序、启动 Piwork、打开系统浏览器即可进入原有工作台。

本次规划修订同时落实 verification 的 C1/W1–W5，补齐英文/简体中文及本地诊断获取；既有任务勾选和历史实机记录不能代替修复后重新验证。

## What Changes

- 增加 Wails v2 稳定版、Go 与 Vanilla HTML/CSS/JS 桌面入口，初始窗口 800×600，直接迁移已确认的 `piwork-launcher-800x600.html`；使用 Piwork Tokens/Controls、本地 Logo/SVG、自绘 Header、菜单及真实窗口控制。
- 实现唯一主路径及真实未启动/启动中/运行/错误/安全停止状态。只有本次 VM 的 WebUI `/healthz` 返回 200 才允许打开浏览器；保留原版 Piwork WebUI 的管理员、模型及 Runtime 配置职责。
- 最小重构现有 `internal/launcher` 为 CLI/GUI 共用的可取消运行服务，通过结构化事件传递真实阶段和状态；复用已有 bundle、加速检查、两端口转发、数据锁、qcow2、QGA/QMP 和关机流程。
- 增加原生目录选择及独立用户偏好持久化。默认使用 `platform.DefaultData()`；首启不强制选目录，失败仍可改目录，不将磁盘模板复制完成或一次启动点击视为安装成功。
- 增加原生剪贴板、系统浏览器、帮助/About 弹窗、折叠日志与保存对话框；导出本次日志或当前安装全部日志，沿用并复查脱敏规则。
- 修复 Windows 控制通道连接阶段取消绕过安全收尾、错误结束与停止的竞态，以及旧会话事件/快照覆盖当前界面的问题；以真实 clean/unclean 结果裁决退出。
- 导出本次日志使用完整会话文件而非展示缓冲；支持普通可写保存目录，正确传播写入/同步失败，失败不替换原目标。
- GUI 支持 `en` 与 `zh-CN`，没有语言偏好时固定英文，不随系统语言自动切换；在现有菜单切换并独立持久化，不增加设置页或重启 VM。全部应用自有文案双语，第三方技术日志保留原文。
- 在 VM/Guest 无法启动时仍能通过 GUI 导出真实、脱敏的 Launcher 本地诊断包，用户自行发给维护者；窗口无法创建时记录可获取的自身诊断及位置，不引入上传服务。
- 同步英文/简中 README、使用帮助、构建、排障和交付说明中的事实、命令与验证边界，并在两平台真实 GUI 中复验修复、语言和故障取日志链路。
- 保留现有 CLI 入口及参数语义，新增 `dist/piwork-microvm-gui`、`dist/piwork-microvm-gui.exe`。GUI/CLI 分别构建，继续以最终文件尾部 Trailer 读取内置 MicroVM 资源；明确 WebKitGTK/WebView2 系统前提、版本、许可证与校验身份。
- 对两平台安排真实窗口、真实 KVM/WHPX CoreLoop、安全关机和原盘恢复验收；自动化、静态布局检查和旧 CLI 证据不能替代本次 GUI 的实际运行结果。

## Capabilities

### New Capabilities

- `microvm-desktop-launcher`: 桌面 CoreLoop、Piwork 视觉、目录选择、窗口/菜单/剪贴板、日志查看导出、英文/简中切换与独立本地诊断获取。

### Modified Capabilities

- `microvm-launcher-lifecycle`: 提供共用的上下文生命周期和结构化事件，区分 WebUI 可访问与业务 Runtime 完全就绪，覆盖进程创建后的连接阶段取消、并发收尾和跨会话迟到状态保护，保留 CLI 行为。
- `microvm-persistent-storage`: 规定桌面目录及语言偏好与业务安装根隔离、健康成功判定、失败后的选择和旧偏好兼容，不更改既有磁盘格式或持久化边界。
- `microvm-single-binary-delivery`: 增加与 CLI 并存的 GUI 单文件产物、内置双语资源、桌面系统依赖、构建隔离、Trailer 兼容及双语文档/独立真实 GUI 验收要求。

## Impact

- 涉及 `internal/launcher`、必要的 `internal/platform` 子进程显示适配；新增桌面控制器、Wails 入口及嵌入式静态前端。现有 `internal/bundle` 和 `internal/qemu` 的校验、控制与锁继续复用。
- 扩展 `scripts/bundle.py` 和 Makefile 的入口选择/原生 GUI 构建适配，不全局启用 CGO，不覆盖 CLI 中间产物和清单。保留现有 build.lock、包装层独立版本和上游发行身份；新增 Wails 依赖锁定及相应许可证。
- 更新中英文 README、测试装置及独立 GUI 验收记录。现有 CLI 发布流程保持其既有资产与显式发布边界，本变更只交付本地 GUI 构建，不发布 Release、不推送远程。
- 不修改上游 Piwork 业务源码、不更换锁定的 Guest/Piwork 输入、不增加共享目录或 Infra Daemon；不引入 React/Vue/Electron/Tailwind、嵌入式 Piwork 浏览器或额外设置向导。
- 上游 Piwork/Guest 升级、`piwork-serve` 到 `piwork-core` 的入口与参数适配，以及升级后的最终整合交付属于后续独立变更；本变更不能提前刷新上游 pin 或宣称这些整合已完成。
- 日志交付为用户在 GUI 导出本地包后自行发送，不设计上传接收端，不自动发送日志；遵循 AGENTS 分开提交规划、功能、用户文档和验收记录。
