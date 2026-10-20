# MicroVM Guest Runtime Spec Delta

## Purpose

定义 Piwork MicroVM 内完整 Linux 运行环境及其可重现构建契约，使统一服务端、现有 Agent/helper 和真实 Work 容器能够在一个 KVM Guest 中运行，而不是只展示静态网页。

## ADDED Requirements

### Requirement: 从固定源码构建完整 Guest

构建系统 SHALL 从明确锁定的 Piwork 源码构建统一 Linux 服务端及其嵌入式工作台、管理和首次引导资源，并交付同一构建身份的生产 Agent、package-helper、file-helper、snapshot-helper 及必要脑包/运行资源。Guest SHALL 包含可直接启动的 kernel、RootFS/init、证书及 Docker Engine/containerd/runc，不要求最终用户构建 Guest 或手动准备内部容器。

#### Scenario: 从干净输入重建
- **WHEN** 开发者按交付命令从声明的固定输入构建
- **THEN** 得到匹配源码、UI、协议和镜像身份的 Guest 资源与构建清单，不使用未知来源的历史镜像代替当前源码产物

#### Scenario: 必要镜像缺失或不匹配
- **WHEN** Guest 中的必要 Agent/helper 缺失或平台、协议、嵌入引用不匹配
- **THEN** 构建或运行准备明确失败，不宣称完整交付就绪，不静默采用另一发行镜像

### Requirement: Linux 支持容器和 MMIO 设备

Guest kernel SHALL 支持本交付所用 VirtIO-MMIO、块设备、网络、9P、串口控制及 ext4，并具备 Docker 所需 namespaces、cgroups、overlayfs、veth、bridge、conntrack、NAT 和实际选用的 iptables/nftables 能力。Guest SHALL 使用可协商的 Docker Engine 28+，其运行时持久存储位于 ext4。

#### Scenario: 真实 Docker 容器运行
- **WHEN** Guest 完成启动并通过自己的 Docker Engine 创建带持久卷和独立网络的容器
- **THEN** 容器真实运行、读写持久存储并完成 DNS/出站请求，没有因缺少 kernel 能力而退化为模拟或宿主容器

### Requirement: 按持久存储和依赖状态启动

Guest SHALL 先完成 RootFS/init、持久盘与共享目录挂载，再配置 DHCP/DNS、启动 Docker、校验或加载镜像，最后启动统一 Piwork。各阶段 SHALL 提供不含秘密的成功或失败状态，必要持久存储不可用时 MUST NOT 在临时目录初始化新安装。

#### Scenario: 首次正常开机
- **WHEN** 新 Guest 连接合法空持久盘和 Host 数据目录
- **THEN** 各阶段按依赖顺序完成，Piwork 使用预期数据路径和 Guest Docker，浏览器能够进入现有引导

#### Scenario: 持久盘或 9P 挂载失败
- **WHEN** 必要挂载失败、磁盘身份错误或文件系统不可写
- **THEN** Guest 报告具体失败阶段并阻止 Piwork 创建替代空状态，保留原盘供诊断

### Requirement: 复用完整 Piwork 业务运行时

Guest SHALL 运行现有统一 Piwork 入口及真实 TS Agent harness、Go helper 和 Service 控制链路，保留 Work/Service 身份、两卷布局、权限、配置及恢复语义。运行就绪 SHALL 以真实运行依赖和实际 Work 行为验证，不能由 HTTP 首页或静态进程存在推断。

#### Scenario: 创建真实 Work
- **WHEN** 用户完成 QuickStart 后在工作台创建并启动 Work
- **THEN** Guest Engine 创建当前安装的真实 Agent、私有卷、workspace 和 Work 网络，Agent 握手就绪，Files 和获准 Service 使用同一 workspace

#### Scenario: 缺少外部 AI Key
- **WHEN** 验收环境没有有效供应商 Key
- **THEN** 可以验证真实容器、文件和 Service 链路，并将模型测试标为未验证；任何确定性模型夹具必须单独标识，不得称为真实模型调用成功
