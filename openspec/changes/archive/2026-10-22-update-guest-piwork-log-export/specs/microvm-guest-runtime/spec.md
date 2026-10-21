# MicroVM Guest Runtime Spec Delta

## MODIFIED Requirements

### Requirement: 从最新干净上游源码锁定构建输入

构建准备 SHALL 锁定明确批准的上游默认分支完整 commit 和解析时间，再以该 commit 构建。更新可以解析官方远程最新 HEAD，或使用统筹者明确冻结的本地 main 合并提交；本次 SHALL 使用 CORE_MAIN_READY `29e3471e02e53094c1e1f427a88de6a2a24fb963`，确认包含已核验的 `19f3e0f78deabbdf67f7db997c6d276b6dfda145`，通过既有本地 Git 来源构建干净副本。后续 main 规格归档提交 MUST NOT 自动改变本次输入。正常重建 SHALL 使用锁定输入；用户运行产物时 MUST NOT 拉源码、刷新分支或编译。构建 SHALL 不应用本项目的 Piwork 补丁，不继承脏源码副本，不修改相邻 Piwork 工作区。

#### Scenario: 最新源码与可复现重建
- **WHEN** 实施准备明确批准的上游提交，随后另一构建按已生成的锁定记录重建
- **THEN** 使用同一完整 commit，均记录真实源码身份且没有应用 Piwork 补丁；本次固定为 CORE_MAIN_READY，不因后续 main 前进而变化

#### Scenario: 构建目录残留修改
- **WHEN** 原有源码副本含本地补丁、未声明改动或与锁定 commit 不同的内容
- **THEN** 构建拒绝该输入或创建独立干净副本，不将它标为原版，也不重置其他工作区

### Requirement: 交付完整且身份一致的 Piwork 运行资源

Guest SHALL 包含既有 Linux kernel、RootFS/init、Docker Engine/containerd/runc、证书、Piwork 统一 Linux 入口及嵌入 WebUI、生产 Agent、package-helper、file-helper、snapshot-helper 和必要资源。本次统一入口 SHALL 为原版 `piwork-core`，使用其 `--ui-port`、`--core-port`、`--data-dir`，保留现有持久数据位置和停止语义，不传递已移除的旧入口参数。Server 与镜像 SHALL 使用同一锁定源码和真实构建身份，记录源码声明版本、完整 commit、dirty 状态及资源身份；不强改为另一正式版本或复用旧产物冒充升级。Guest 中必要镜像 SHALL 可以从内置资源准备，不依赖 Host Docker。

#### Scenario: 离线准备内置依赖
- **WHEN** 新安装启动，Guest Docker 中尚无 Piwork 镜像
- **THEN** Guest 从内置资源加载匹配的生产镜像并验证身份，不要求用户运行 Docker 命令或下载 Guest

#### Scenario: 镜像身份不符
- **WHEN** 内置 Server 引用与 Agent/Helper 的镜像身份或协议不匹配
- **THEN** 构建或运行准备明确失败，不静默采用历史标签或验收专用 Agent

#### Scenario: 新 Core 入口启动
- **WHEN** 使用此次冻结输入构建的 Guest 启动 Piwork
- **THEN** 原版 Core、Desktop、Docker 和内置生产依赖可用，日志及版本能关联同一完整提交，不以旧 `piwork-serve` 或失效参数启动

## ADDED Requirements

### Requirement: 从原版 Desktop 管理员入口取得故障日志包

GUI SHALL 继续通过系统浏览器打开 Guest 中原版 Desktop。有效管理员 SHALL 能从其账户菜单唯一的 `Export logs` 入口创建、观察并下载原版 ZIP 到 Host，无需终端或宿主目录共享；应用 MUST NOT 新增另一业务日志入口、上传服务或改变上游授权。下载请求 SHALL 沿现有 WebUI 同源路径通过两个既有 Host 入口完成，不额外发布端口。

ZIP SHALL 保留上游 Core 与管理员所属 Work/Service 的日志范围、脱敏及缺口表达。浏览器开始下载 MUST NOT 被描述为本地保存完成；实测 SHALL 打开已保存 ZIP 核对来源、受控故障标记、敏感值过滤和可观察的缺口，不将 Launcher 的运行日志当作业务故障包。

#### Scenario: 可控故障的实际浏览器导出
- **WHEN** 专属 Guest 内真实 Work/Service 产生已知故障，管理员在 Desktop 账户菜单导出日志
- **THEN** Host 获得可打开的 ZIP，包含相关 Core/应用诊断及正确来源标识，已知测试凭据不泄漏，导出不额外停止或重新创建 Work

#### Scenario: 可控来源缺口
- **WHEN** 专属测试安装中一个日志来源按上游支持的故障条件变为不完整
- **THEN** Desktop 与已下载包的清单如实显示缺口及部分结果，不用空日志或 HTTP 成功冒充完整收集，也不要求真实模型调用
