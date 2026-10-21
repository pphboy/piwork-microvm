# microvm-launcher-lifecycle Specification

## Purpose

定义 Linux/KVM 和 Windows/WHPX 的原生单程序启动契约，覆盖统一命令行、硬件能力检查、磁盘独占、实际就绪、首次授权和有序关闭，使用户无需配置虚拟机或操作容器即可使用 Piwork。

## Requirements

### Requirement: 支持 Linux 和原生 Windows 11 Home

Launcher SHALL 支持 Linux x86-64/KVM 与原生 Windows 11 Home x86-64/WHPX，Windows 最低兼容目标为 21H2。运行 MUST NOT 依赖 WSL、Hyper-V Manager、Pro 专属功能、Docker Desktop 或额外文件系统/网络驱动。Windows Hypervisor Platform 未启用或能力不足时 SHALL 清楚报错，不自动修改系统功能。

#### Scenario: Windows Home 原生启动
- **WHEN** 用户在已启用所需虚拟化能力的 Windows 11 Home 上从 Windows 本地路径执行 EXE
- **THEN** launcher 使用 Windows 原生进程、路径和虚拟化接口启动，不调用 WSL，不以 24H2 的文件共享功能作为条件

#### Scenario: 加速能力不可用
- **WHEN** Linux KVM 不可访问，或 Windows WHPX 无法创建可用虚拟化环境
- **THEN** 启动明确失败并说明实际能力或权限问题，不要求用户更换为 Pro 来满足并不存在的产品前提

### Requirement: 提供统一且无副作用的命令行入口

两平台 SHALL 支持无参数、`--data-dir DIR`、`--port PORT`、`--core-port PORT`、`--cpus N`、`--memory MiB`、`--no-open` 和 `--help`。默认 SHALL 使用 2 vCPU、4096 MiB 内存、UI 17891 和 Core 17871。两个 Host 端口 SHALL 接受 1–65535 的整数、不得相同，且均 MUST NOT 为内部 Agent RPC 保留端口 7172；不额外排除旧 Service 端口池。无效参数 SHALL 在访问虚拟化、准备数据或启动 VM 前失败，`--help` SHALL 无需虚拟化能力且不写用户数据。

#### Scenario: 查看帮助与参数错误
- **WHEN** 用户查看帮助，或输入缺值、非整数、越界/重叠端口、无效资源或未知参数
- **THEN** 分别只显示完整帮助，或返回可理解的非零错误，不创建磁盘、不启动 VM

#### Scenario: 选择数据目录和端口
- **WHEN** 用户指定可用安装根目录和合法 `--port 8080`
- **THEN** launcher 使用该目录内的持久盘，并以 `http://127.0.0.1:8080` 作为本次浏览器入口

#### Scenario: UI 或 Core 指定 7172
- **WHEN** 任一 Host 端口选项指定 7172
- **THEN** launcher 在环境和数据访问前说明内部 Agent RPC 保留限制并返回参数错误，帮助和双语说明反映这一兼容变化

### Requirement: 使用唯一硬件加速 MicroVM

Launcher SHALL 启动一个 QEMU `microvm`，使用 VirtIO-MMIO，不使用 PCI 设备；Linux SHALL 使用 KVM，Windows SHALL 使用 WHPX。MUST NOT 静默回退到 TCG、其他机型或在 Host 直接运行 Piwork。

#### Scenario: 核实实际运行方式
- **WHEN** 验收检查运行中的 QEMU、Guest 设备和 Host 虚拟化状态
- **THEN** 实际观察到本平台硬件加速、microvm、MMIO 设备及一个产品 VM，而非仅从配置字符串推断

### Requirement: 持续独占安装和数据盘

安装和磁盘 SHALL 在任何写入准备前获得独占保护，持续覆盖全部 VM 写者的生命周期。不同端口、路径别名或 launcher 意外退出 MUST NOT 允许另一个 VM 同时写同一磁盘。

#### Scenario: 重复启动及路径别名
- **WHEN** 原 VM 正在使用安装，另一进程更换端口或通过符号链接、junction、大小写别名再次启动同一磁盘
- **THEN** 第二次启动在写入前明确失败，原 VM 和数据不受影响

#### Scenario: Launcher 异常结束
- **WHEN** launcher 被异常终止
- **THEN** 若 QEMU 存活则仍阻止第二个写者，若 QEMU 被联动终止则记录未确认的关闭状态，直到真实写者退出才允许再次独占

### Requirement: 根据实际状态交付可用入口

Launcher SHALL 观察 Guest 阶段、QEMU 存活及本次主入口的健康/就绪状态，不以固定 sleep 宣布启动成功。入口可访问与业务 Runtime 完全就绪 SHALL 分别报告；实际 WebUI `/healthz` 返回 200 且本次 QEMU 存活时才允许交付浏览器入口。空安装 SHALL 允许用户进入原有首次引导，不因尚未配置管理员或模型而无限等待完整 ready；已配置安装 SHALL 继续验证并报告完整运行依赖，不将 WebUI 可访问等同模型和容器依赖已经完成配置。

#### Scenario: 首次启动等待 QuickStart
- **WHEN** 新安装的引导页面已可用但尚无管理员或模型配置
- **THEN** 用户获得主入口和原版 QuickStart，launcher 明确等待用户设置，不把配置缺失当成 Guest 崩溃

#### Scenario: 启动失败
- **WHEN** QEMU 提前退出、Guest 阶段报错或达到启动期限
- **THEN** launcher 返回具体阶段和可理解的脱敏原因，并收尾本次启动；GUI 已显示的启动错误沿用现有日志记录和导出，日志文件已生成时提供真实路径，不只报告端口等待失败，也不伪造未生成的日志路径

#### Scenario: 桌面只在真实入口可访问后开放浏览器操作
- **WHEN** WebUI 尚未健康，或仅收到 Guest 阶段事件但还未通过健康检查
- **THEN** 桌面保持启动中，不显示可用的 WebUI 操作；通过检查后才报告入口可访问，并独立保留业务 Runtime 的准备状态

### Requirement: 复用原版首次引导且不泄漏秘密

Launcher SHALL 使用锁定上游 Piwork 的原有首次引导，不创建默认管理员、不修改业务授权或绕过 QuickStart。本次冻结输入 SHALL 延续原有浏览器创建首位管理员和正常登录，不使用私有设置链接。真实 API Key、Token 和密码 MUST NOT 写入普通日志。浏览器自动打开不可用或指定 `--no-open` 时 SHALL 输出当前回环访问地址。

#### Scenario: 原版管理员创建及登录
- **WHEN** 新安装就绪并进入当前回环地址
- **THEN** 用户通过原版页面创建首位管理员、确认密码并正常登录；已初始化安装仍要求正常登录，保留原有 CSRF、会话及 Work 权限

### Requirement: 正常停止和异常退出如实区分

Ctrl+C 和受支持的正常停止事件 SHALL 请求 Guest 有序停止 Piwork、Work、Docker，完成同步和文件系统收尾，再等待 QEMU 退出并释放独占。关闭预算 SHALL 覆盖 Piwork 原有 drain 时间。窗口关闭、系统结束会话、超时或强制终止未能确认完整收尾时 SHALL 标记异常，不声称正常关闭，任何路径 MUST NOT 删除用户磁盘。

#### Scenario: Work 运行中按 Ctrl+C
- **WHEN** 用户在真实 Work/Service 运行时正常停止 launcher
- **THEN** 依赖按序停止，数据盘完成同步，QEMU 退出，下一次可恢复原安装

#### Scenario: Windows 关闭事件或强杀受限
- **WHEN** Windows 的关闭期限或外部强杀使完整 drain 无法确认
- **THEN** 当前诊断或下次启动清楚显示关闭未确认，保留数据并执行必要恢复检查，不将强制进程退出当成干净关机

#### Scenario: 最终产物异常退出恢复验收
- **WHEN** 分别在当前 Linux/KVM 和 Windows Home/WHPX 上，对最终产物执行 Guest 提前退出、真实关闭预算耗尽及 launcher 强杀
- **THEN** 六个用例均保留原磁盘及适当的异常诊断，真实写者存活时仍拒绝第二写者，写者退出后可重新启动原安装并核对故障前已确认写入的数据；未验证或恢复失败的用例不得标记通过

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
