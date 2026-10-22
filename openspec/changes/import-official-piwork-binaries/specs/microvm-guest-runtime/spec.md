# Spec Delta

## MODIFIED Requirements

### Requirement: 从最新干净上游源码锁定构建输入

构建准备 SHALL 明确选择源码构建或官方发行制品导入，并锁定实际源码完整 commit 与解析时间；正常重建 MUST NOT 自动跟随 main、标签或下载内容的变化。源码模式 SHALL 使用锁定提交的干净副本，不应用本项目的 Piwork 补丁、不继承脏输入、不修改相邻工作区。官方制品模式 SHALL 同时锁定官方仓库、发行标签、实际构建提交、发布提交、资产地址/大小/SHA256、来源元数据校验和及生产镜像身份，导入原版 Linux amd64 Core/CLI；输入失败 MUST NOT 静默回退到源码编译或旧版本。用户运行最终产物时 MUST NOT 拉源码、刷新分支、编译或下载内置运行依赖。

本次输入 SHALL 为 Piwork `v0.0.12` Preview，实际构建提交 `4f127751fc4805e504a1af0d7b48c02739f72489`，发布提交 `c4ce9bbd8fea9d990979332e57b61876cda20da2`。两个提交 SHALL 分别记录，程序版本与构建提交 SHALL 保留上游真实值，不将发布提交写成二进制构建身份。 native-v2 元数据 SHALL 从 `nativePrograms` 获取程序身份与摘要、从发行清单获取完整镜像身份，独立解析官方 Git 标签确定未在原始资产中声明的发布提交，并记录其来源；MUST NOT 改写下载的元数据或程序字节。准备结果的只读检查 SHALL 比较完整资产、程序/UI、镜像引用/digest/image ID/协议与锁定来源身份，不仅检查资产摘要和 image ID。

#### Scenario: 最新源码与可复现重建
- **WHEN** 实施准备批准的上游输入，随后另一构建按锁定记录重建
- **THEN** 使用相同输入模式和实际源码身份；源码模式使用干净锁定副本，官方模式使用相同 SHA256 的发行资产，不因 main 或远端标签前进而改变

#### Scenario: 构建目录残留修改
- **WHEN** 原有源码副本含本地补丁、未声明改动或与实际构建提交不符
- **THEN** 构建拒绝该输入或创建独立干净副本，不将它标为原版，也不重置其他工作区

#### Scenario: 官方构建提交与发布提交不同
- **WHEN** 0.0.12 官方标签指向 `c4ce9bbd8fea9d990979332e57b61876cda20da2`，而归档及程序报告 `4f127751fc4805e504a1af0d7b48c02739f72489`
- **THEN** 两者按锁定来源分别验证和呈现，包装层上游版本输出关联实际构建提交，不重写原版程序身份

#### Scenario: 官方资产或身份校验失败
- **WHEN** 下载不完整、大小/SHA256 不符、程序平台/版本/提交/原版状态或嵌入 UI 身份与锁不符
- **THEN** 导入失败，未验证内容不成为有效构建输入，不覆盖上一份有效输入，不生成冒充 0.0.12 的 Guest 或发行文件

#### Scenario: 锁定身份变化而准备文件未变化
- **WHEN** 镜像 digest/引用/协议、程序/UI 身份或资产记录等锁定字段变化，但准备输出字节未改变
- **THEN** 只读检查拒绝旧准备记录，不能复用或通过发布输入门槛，且不写入或下载文件

#### Scenario: 官方归档含不安全路径
- **WHEN** 官方制品输入的归档存在路径越界、重复目标、链接、特殊文件或超出导入边界的内容
- **THEN** 导入拒绝该归档，不能写出暂存目录或执行其中的非预期程序；只有通过完整性和结构校验的目标程序可进行版本检查

### Requirement: 交付完整且身份一致的 Piwork 运行资源

Guest SHALL 包含既有 Linux kernel、RootFS/init、Docker Engine/containerd/runc、证书、原版 `piwork-core` / `piwork-cli`、嵌入 WebUI、生产 Agent、package-helper、file-helper、snapshot-helper 和必要资源。Core SHALL 继续作为 Guest 原生二进制启动，使用 `--ui-port`、`--core-port`、`--data-dir`，保留持久数据位置和停止语义，不传递旧入口参数，也不为导入二进制而改为 Core 容器运行。

Core 与生产依赖 SHALL 来自同一锁定实际构建身份，校验版本、完整 commit、原版状态、资源及协议身份。官方模式 SHALL 按锁定 registry digest 取得配套镜像，核对 image ID、Linux amd64、身份/协议标签及其中程序的版本，再将所需镜像和原版 Core 引用一起内嵌。必要镜像 SHALL 能从内置资源准备，不依赖 Host Docker 或运行时在线拉取；不强改版本、不把旧镜像重标记为新版本，也不依赖标签的可变解析结果。

#### Scenario: 离线准备内置依赖
- **WHEN** 新安装启动，Guest Docker 中尚无 Piwork 镜像
- **THEN** Guest 从内置资源加载匹配的生产镜像并验证身份，不要求用户运行 Docker 命令或下载 Guest

#### Scenario: 镜像身份不符
- **WHEN** Core 引用与 Agent/Helper 的 digest、image ID、实际构建身份或协议不匹配
- **THEN** 构建或运行准备明确失败，不静默采用历史标签或验收专用 Agent

#### Scenario: 新 Core 入口启动
- **WHEN** 使用锁定 0.0.12 官方制品构建的 Guest 启动 Piwork
- **THEN** 原版 Core、Desktop、Guest Docker 和内置生产依赖可用，日志及版本关联实际构建提交，既有 Host UI/Core 入口与安全停止继续生效

#### Scenario: 官方标签被重新指向其他镜像
- **WHEN** 同名官方镜像标签对应了与锁定 digest 或 image ID 不同的内容
- **THEN** 只允许使用已核验的锁定镜像；不能接受新标签内容、跳过校验或用本地旧镜像冒充新输入

#### Scenario: Core 原生运行与生产容器分工
- **WHEN** 检查最终 Guest 的进程与镜像准备结果
- **THEN** Core 由既有 Guest 服务启动为原生进程，Agent/Helper 与 Service 使用 Guest Docker；最终产物不因导入官方包而要求 Host Docker 或额外暴露端口
