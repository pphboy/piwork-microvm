# microvm-persistent-storage Specification

## Purpose

定义首版仅使用 Host qcow2 磁盘文件承载 Guest ext4 的持久化契约，完整保存账号、配置、Work 文件历史和 Service 数据。用户通过 Piwork 上传下载文件，启动、清缓存和正常退出均不改变数据归属。

## Requirements

### Requirement: 数据根目录完整承载安装身份和持久盘

`--data-dir DIR` SHALL 指定完整安装根目录，至少包含安装关联元数据、`disks/state.qcow2` 和 `logs/`。Linux 默认 SHALL 使用遵循 XDG 的用户数据目录下 `piwork-microvm`，Windows 默认 SHALL 使用 `%LOCALAPPDATA%\PiworkMicroVM`。同一根目录 SHALL 确定同一安装，不能由可执行文件位置、当前工作目录或缓存 hash 决定用户数据身份。

#### Scenario: 自定义根目录重复启动
- **WHEN** 用户以自定义 `--data-dir` 初始化，正常退出后从不同工作目录再次使用相同安装根
- **THEN** 复用原安装和磁盘，输出实际数据与日志位置，不生成另一个空安装

### Requirement: 独立 qcow2 磁盘提供 Guest 本地 ext4

两平台 SHALL 使用 Host 的 qcow2 文件作为可写持久块设备，Guest SHALL 将其作为本地 ext4 使用。该数据盘 SHALL 不依赖缓存中的外部 backing 文件；只读系统资源和临时根层 MUST NOT 承担用户持久状态。Host SHALL 无需 ext4 驱动或目录共享能力。

#### Scenario: Host 原生文件系统承载数据盘
- **WHEN** Windows 在本地 NTFS 或 Linux 在支持的本地文件系统中保存安装根并启动
- **THEN** QEMU 读写普通 qcow2 文件，Guest 观察到本地 ext4，数据库使用正常锁、WAL 和同步语义

### Requirement: 完整业务数据和容器卷持久化

Core 数据库、管理员、模型配置/凭证引用、Work 定义、private/workspace 卷、Session/Memory、Docker/containerd 持久内容以及 Service 定义和声明的持久数据 SHALL 落到数据盘。上传文件 SHALL 写入现有 Work workspace 卷；临时目录仍按上游既有语义处理，不新增任意容器路径都持久化的承诺。

#### Scenario: 真实文件和数据库写入
- **WHEN** 用户配置安装、上传文件、运行 Work 并让 Service 写入其持久目录和数据库
- **THEN** 检查实际 backing filesystem 时，这些数据都在持久 ext4，文件在 named volume 中，不在共享目录或临时 RootFS

### Requirement: 只在明确的新安装中初始化磁盘

首版 SHALL 定义新安装的原子初始化，不承担旧 9P 安装识别、兼容或迁移。一般数据保护 SHALL 拒绝覆盖未知目录内容；已有安装记录的磁盘缺失、格式不支持或损坏时 MUST NOT 自动格式化、替换磁盘或创建空安装冒充恢复。

#### Scenario: 新安装与不完整初始化
- **WHEN** 用户在空的受管安装根首次启动，或首次初始化曾被中断
- **THEN** 仅在能确认属于未完成新安装时安全完成初始化，安装身份与数据盘关联一致，不覆盖不明来源文件

#### Scenario: 已有磁盘故障
- **WHEN** 已记录安装的数据盘缺失、损坏或被未知内容替换
- **THEN** 启动报告数据故障并保留剩余字节，不复制新模板覆盖原数据

### Requirement: 重启和重建缓存保留完整安装

正常退出、再次启动、删除可重建缓存或重新解包同版系统资源 SHALL 保留管理员、配置、Work、历史、文件和 Service 持久数据。恢复 SHALL 遵守上游 Work/Service 运行意图，不自行重置或强制改变业务状态。

#### Scenario: 关机后恢复同一安装
- **WHEN** 用户完成真实业务写入、正常停止，再次启动并按原有方式恢复 Work/Service
- **THEN** 原身份、文件哈希、历史和数据库计数保持，可继续通过 Files 下载和浏览器访问 Service

#### Scenario: 仅清理缓存
- **WHEN** 用户正常停止后删除受管运行资源缓存，再运行同一产物
- **THEN** 程序只重新解包系统资源，继续使用原磁盘和安装，不要求重新 QuickStart

#### Scenario: 异常退出后的原盘恢复
- **WHEN** 在专属验收安装确认账号/配置、Work、文件和 Service 数据已写入，再触发 Guest 提前退出、关机超时或 launcher 强杀，并在全部原写者退出后启动原盘
- **THEN** 原安装身份、文件哈希和已提交的数据库数据保持，数据库完整性检查通过，不以新建磁盘或重新 QuickStart 冒充恢复，也不承诺未完成事务已持久化

### Requirement: 明确备份和文件访问边界

帮助与交付说明 SHALL 说明用户文件位于磁盘镜像内，通过 Piwork Files 上传下载；普通 Host 目录不直接展示它们。完整备份 SHALL 在确认正常停止后包含磁盘及安装关联元数据。运行时 MUST NOT 在 Host 同时读写挂载该 ext4 镜像，不能将复制运行中的镜像称为已验证的一致备份。

#### Scenario: 查看数据位置和备份说明
- **WHEN** 用户查看帮助或启动输出
- **THEN** 能找到实际磁盘路径、文件上传下载入口、正常停止及完整备份方法，不被引导去安装 Host ext4 驱动或将缓存当作用户数据
