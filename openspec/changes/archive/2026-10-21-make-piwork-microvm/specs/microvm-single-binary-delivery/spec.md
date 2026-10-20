# MicroVM Single Binary Delivery Spec Delta

## Purpose

定义可分发 Linux ELF 的完整资源、首次提取、后续复用及真实验收证据，区分外部 QEMU 开发阶段与最终自包含交付，让一个程序即可启动完整 Piwork MicroVM 的承诺可以被重复验证。

## ADDED Requirements

### Requirement: 交付自包含 Linux ELF

最终产物 SHALL 为 `dist/piwork-microvm` Linux x86-64 ELF，包含 launcher、可执行的 QEMU 及必需库/固件、Guest kernel/RootFS、Piwork 统一服务端、生产 Agent/helper 和必要资源。最终 Host SHALL 不需预装 QEMU、Docker、Node、Go、源码或手工下载 Guest 资源；首次业务使用可要求外部网络和用户自己的模型配置。

#### Scenario: 仅复制一个程序
- **WHEN** 将最终产物复制到仅有受支持 Linux x86-64/KVM 的干净 Host 并执行
- **THEN** 自动启动内含资源提供的真实 MicroVM 与 Piwork，不调用未声明的 Host QEMU/动态库/固件，不要求执行构建或 Docker 命令

#### Scenario: 只有外部 QEMU 阶段可用
- **WHEN** 当前阶段还依赖宿主 `qemu-system-x86_64`
- **THEN** 产物和验收明确标为开发阶段，不能将自包含或干净 Host 验收项标记完成

### Requirement: 校验并复用受管理缓存

launcher SHALL 在首次启动提取压缩资源到受当前用户管理的缓存，按包身份和内容完整性校验并原子发布，后续启动复用有效资源，不重新构建 Guest 或覆盖持久数据。缓存中断、不完整或损坏时 SHALL 能安全重新提取，不能执行不完整二进制；归档提取不得写出目标目录。

#### Scenario: 首次与后续启动
- **WHEN** 空缓存首次启动后再次运行同一产物
- **THEN** 首次完成提取，后续使用相同有效运行资源并复用持久盘，均不重新构建 Guest/镜像

#### Scenario: 缓存损坏或提取被中断
- **WHEN** 已有缓存不完整、hash 不匹配或提取进程被终止
- **THEN** 下次启动在独占校验后重建相应缓存或明确失败，用户磁盘和共享文件不受影响

### Requirement: 提供可重现输入和本地构建入口

仓库 SHALL 提供 kernel 配置、Guest RootFS/init 配方、Piwork 源码 revision、镜像引用/身份、QEMU/运行库闭包、依赖版本/校验及完整本地构建和启动命令。构建清单 SHALL 记录真实源码修改状态、UI 输入身份和产物 hash；随 QEMU/kernel/系统组件交付必要许可证材料。构建不得隐含 push 或发布 Release。

#### Scenario: 审核和重建制品
- **WHEN** 另一开发者取得完整源码变更和构建命令
- **THEN** 可以重新生成同一锁定依赖组合的 Guest 与单文件产物，并核实资源来源、身份及校验，不依赖原开发者未提交的私有文件或已运行容器

### Requirement: 以真实 KVM Happy Path 作为完成依据

交付 SHALL 实际执行并记录 microvm+KVM、Guest Linux、Docker、Piwork、Host 浏览器 QuickStart、Guest/Work 联网、真实 Work、真实 Service HTTP/WebSocket/流式访问、9P 双向文件、正常退出和第二次启动恢复。证据 SHALL 包含实际命令参数、资源版本/身份、测试来源、预期与观察及失败项；代码审查、mock、普通 Docker 容器或软件模拟不能替代 KVM 证据。

#### Scenario: 完成实际 Happy Path
- **WHEN** 验收使用最终 ELF 从独立空安装执行完整流程并重启
- **THEN** 每项可关联真实 VM、Work、Service 和文件/数据库结果，报告实际 QEMU 参数与网络/存储布局，没有仅凭 launcher 退出码推断业务成功

### Requirement: 准确记录未验证条件

验收 SHALL 明确区分“通过”“失败”“未验证”及各自原因。缺少真实 AI Key 时不得声称供应商调用已成功；干净 KVM Host 不可取得时 SHALL 记录限制并仍验证当前 Host 上已打包资源的独立使用，不能用容器内检查宣称完成独立 Host KVM 验收。

#### Scenario: 外部条件缺失
- **WHEN** 无有效供应商 Key或没有第二台干净 KVM Host
- **THEN** 完成其余可执行测试并明确保留对应未验证项、实际原因和复验命令，不虚构成功、不把总体交付阶段自动升级为全部验收完成
