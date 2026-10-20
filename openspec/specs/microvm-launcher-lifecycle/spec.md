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

两平台 SHALL 支持无参数、`--data-dir DIR`、`--port PORT`、`--core-port PORT`、`--cpus N`、`--memory MiB`、`--no-open` 和 `--help`。默认 SHALL 使用 2 vCPU、4096 MiB 内存、UI 17891 和 Core 17871。两个 Host 端口 SHALL 接受 1–65535 的整数且不得相同，不再排除旧 Service 端口池。无效参数 SHALL 在访问虚拟化、准备数据或启动 VM 前失败，`--help` SHALL 无需虚拟化能力且不写用户数据。

#### Scenario: 查看帮助与参数错误
- **WHEN** 用户查看帮助，或输入缺值、非整数、越界/重叠端口、无效资源或未知参数
- **THEN** 分别只显示完整帮助，或返回可理解的非零错误，不创建磁盘、不启动 VM

#### Scenario: 选择数据目录和端口
- **WHEN** 用户指定可用安装根目录和合法 `--port 8080`
- **THEN** launcher 使用该目录内的持久盘，并以 `http://127.0.0.1:8080` 作为本次浏览器入口

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

Launcher SHALL 观察 Guest 阶段、QEMU 存活及本次主入口的健康/就绪状态，不以固定 sleep 宣布启动成功。空安装 SHALL 在 Docker/镜像及原有首次引导可用时交付入口，不因尚未配置模型而无限等待完整 ready；已配置安装 SHALL 验证完整运行依赖。

#### Scenario: 首次启动等待 QuickStart
- **WHEN** 新安装的引导页面已可用但尚无管理员或模型配置
- **THEN** 用户获得主入口和原版 QuickStart，launcher 明确等待用户设置，不把配置缺失当成 Guest 崩溃

#### Scenario: 启动失败
- **WHEN** QEMU 提前退出、Guest 阶段报错或达到启动期限
- **THEN** launcher 返回具体阶段、可理解原因和脱敏日志路径，并收尾本次启动，不只报告端口等待失败

### Requirement: 复用原版首次引导且不泄漏秘密

Launcher SHALL 使用锁定上游 Piwork 的原有首次引导，不创建默认管理员、不修改业务授权或绕过 QuickStart。锁定的 0.0.9 延续原有浏览器创建首位管理员和正常登录，不使用私有设置链接。真实 API Key、Token 和密码 MUST NOT 写入普通日志。浏览器自动打开不可用或指定 `--no-open` 时 SHALL 输出当前回环访问地址。

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
