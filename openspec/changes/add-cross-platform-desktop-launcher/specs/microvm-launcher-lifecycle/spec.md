# MicroVM Launcher Lifecycle Spec Delta

## ADDED Requirements

### Requirement: 命令行与桌面共享可取消且可观测的生命周期

CLI 与桌面入口 SHALL 复用同一个 MicroVM 运行生命周期，支持调用方请求停止、接收真实阶段/状态事件和读取当前一致状态。停止请求 SHALL 进入已有有序收尾流程，不将取消直接解释为 Kill QEMU。状态事件 SHALL 区分运行会话，旧会话的延迟事件和日志展示不得覆盖新会话的状态；GUI 事件订阅或展示失败不得阻塞磁盘同步。CLI 的参数、信号、返回码、版本输出和默认浏览器行为 SHALL 保持既有语义。

从实际进程创建起，尚未连接控制通道的 VM 也 SHALL 受同一生命周期管理；调用方取消或连接失败 SHALL 执行独立 120 秒预算的有序收尾。仅取消错误或进程退出本身 MUST NOT 被视为磁盘已干净同步，结果 SHALL 反映实际 clean/unclean 并按实际写者退出顺序释放保护。并发停止与错误结束 SHALL 保持状态同步，事件和调用快照 SHALL 一致拒绝已结束会话/较旧状态。

#### Scenario: CLI 与 GUI 发起相同安装的启动
- **WHEN** 分别通过 CLI 和 GUI 使用相同运行选项启动
- **THEN** 使用相同加速、资源校验、两入口转发、磁盘独占和 QGA/QMP 流程，GUI 不另写一套 MicroVM 或通过解析 CLI 输出获取状态

#### Scenario: 调用方取消启动或运行
- **WHEN** 桌面停止/关闭或 CLI 信号取消当前生命周期
- **THEN** 启动前取消不会再创建 VM，已经创建的 VM 经同一安全关机流程处理，最终返回真实结果并按顺序释放写者保护

#### Scenario: 旧事件与慢速界面
- **WHEN** 前端暂时不可用、日志大量输出或旧会话有迟到事件
- **THEN** 运行与关机流程继续有界推进，当前状态可恢复读取，旧事件不把已停止/新启动会话误标为运行

#### Scenario: Windows 已创建进程但管道尚未连接
- **WHEN** Windows QEMU 已创建，QGA/QMP 仍在连接，用户取消或连接失败
- **THEN** 记录该 VM 已创建并经同一独立预算收尾，不能在取消连接分支直接 Kill 并冒充未创建/干净停止；异常标记与最终结果相符

#### Scenario: 错误返回与停止竞争
- **WHEN** Guest 错误结束与调用方停止请求同时发生
- **THEN** 请求状态和 clean/unclean 裁决受到一致同步保护，无数据竞争或重复关机，并保留真实错误

#### Scenario: 事件与快照跨会话乱序
- **WHEN** 新会话已开始，旧会话事件或较早读取的快照随后到达前端
- **THEN** 旧数据被拒绝，当前会话、状态、日志和健康门控保持最新事实，不因不同会话的序号不可直接比较而回退

## MODIFIED Requirements

### Requirement: 根据实际状态交付可用入口

Launcher SHALL 观察 Guest 阶段、QEMU 存活及本次主入口的健康/就绪状态，不以固定 sleep 宣布启动成功。入口可访问与业务 Runtime 完全就绪 SHALL 分别报告；实际 WebUI `/healthz` 返回 200 且本次 QEMU 存活时才允许交付浏览器入口。空安装 SHALL 允许用户进入原有首次引导，不因尚未配置管理员或模型而无限等待完整 ready；已配置安装 SHALL 继续验证并报告完整运行依赖，不将 WebUI 可访问等同模型和容器依赖已经完成配置。

#### Scenario: 首次启动等待 QuickStart
- **WHEN** 新安装的引导页面已可用但尚无管理员或模型配置
- **THEN** 用户获得主入口和原版 QuickStart，launcher 明确等待用户设置，不把配置缺失当成 Guest 崩溃

#### Scenario: 启动失败
- **WHEN** QEMU 提前退出、Guest 阶段报错或达到启动期限
- **THEN** launcher 返回具体阶段、可理解原因和脱敏日志路径，并收尾本次启动，不只报告端口等待失败

#### Scenario: 桌面只在真实入口可访问后开放浏览器操作
- **WHEN** WebUI 尚未健康，或仅收到 Guest 阶段事件但还未通过健康检查
- **THEN** 桌面保持启动中，不显示可用的 WebUI 操作；通过检查后才报告入口可访问，并独立保留业务 Runtime 的准备状态
