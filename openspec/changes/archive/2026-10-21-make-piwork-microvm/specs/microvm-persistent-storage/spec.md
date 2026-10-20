# MicroVM Persistent Storage Spec Delta

## Purpose

定义 Host 可直接访问的共享文件和 Guest ext4 持久状态之间的明确边界，保证数据库、Work 与 Service 的完整恢复，同时通过真实目录共享提供可双向操作的用户文件，而不是以镜像文件存在代替共享。

## ADDED Requirements

### Requirement: 明确数据目录与安装关联

默认安装 SHALL 使用 `~/.local/share/piwork-microvm/` 下的 `data/`、`disks/`、`logs/`，分别保存直接共享文件、持久盘和脱敏日志。`--data-dir DIR` SHALL 指定 Host 直接共享的数据目录，并确定性关联一组独立持久盘/安装状态；同一路径再次启动必须使用原安装，不得由临时运行目录或缓存身份决定数据归属。目录、关联元数据和现有磁盘 SHALL 进行所有权、可写性和独占检查。

#### Scenario: 自定义目录重启
- **WHEN** 用户首次以 `--data-dir /path/to/data` 启动，正常退出后以相同参数再次启动
- **THEN** 复用同一共享目录、持久盘和安装身份，显示其实际存储位置，不创建空白替代安装

### Requirement: 提供真正的双向 9P 用户文件共享

Host 选定的 `data/` SHALL 使用 VirtIO-9P/MMIO 自动挂载到 Guest，并为 Work 提供明确的普通共享文件范围。该范围 SHALL 对 Host 与当前 Work 的 Files/获准 Service 可读写，不依赖双向同步副本、导出后复制或 Host 挂载正在使用的 ext4 镜像。共享 SHALL 保留每个 Work 的隔离，不能让一个 Service 获得整个 Host 数据根或其他 Work 文件。

#### Scenario: Host 创建与 Work 修改
- **WHEN** Host 在当前 Work 的声明共享范围创建普通文件，随后通过 Files 或获准 Service 读取并修改
- **THEN** 读取到原字节，修改后的同一文件直接在 Host 可见，无需导入、重新构建或运行同步任务

#### Scenario: Work 创建删除与 Host 修改
- **WHEN** Work 在共享范围创建文件、Host 修改它，随后 Work 删除它
- **THEN** 双方依次观察相同内容和删除结果，未访问其他 Work 或 Core 私有状态；权限/UID、缓存或原子替换失败不得被忽略

### Requirement: 数据库和容器内部存储使用 ext4

Docker `data-root`、containerd 实际持久内容、镜像/容器元数据、Core 配置/SQLite/凭证、Work 私有历史/Memory，以及普通 workspace 与声明持久的 Service 数据 SHALL 使用 Host `disks/` 中 ext4 持久盘。直接共享范围 SHALL 明确限定为适合共享的普通用户文件；数据库所需的锁、同步、事务和崩溃恢复不得依赖未经证明可靠的 9P 行为。

验收 SHALL 实测选用 9P 模式的 SQLite/WAL、文件锁和同步限制，并对 ext4 上实际使用的数据库验证事务、重启与完整性。9P 测试失败 SHALL 记录为该文件系统的限制并保持数据库在 ext4，不更改 SQLite 安全选项掩盖失败。

#### Scenario: 检查实际 backing filesystem
- **WHEN** 检查 Docker、Core 数据库、Agent 私有卷和 Service 业务数据库的实际挂载
- **THEN** 它们位于预期 ext4 持久盘，普通共享文件单独位于 9P，不把 tmpfs、容器可写层或 9P 上的内部数据库称为可靠持久状态

#### Scenario: 9P 数据库能力不可靠
- **WHEN** 跨进程锁、WAL、fsync/rename 或崩溃恢复测试发现不支持或不一致
- **THEN** 结果明确记录，生产数据库继续在 ext4，普通文件共享仍须实际可用，不能用存在风险的全目录 9P 挂载代替拆分存储

### Requirement: 保留既有 Work 两卷和 Service 授权语义

共享接入 SHALL 保留当前 private/workspace 两个受管卷身份、安装/Work 标签、文件权限、Service workspace none/只读/读写授权、删除留存与显式 purge 规则。普通 ext4 workspace SHALL 支持数据库；共享子范围不能被误称为全部 Work 数据直接可见。任何 Guest 专用适配 SHALL 不向 Service 暴露 Agent 私有数据或任意 Host bind 权限，不改变冷快照对既有两卷用户文件的完整处理。

#### Scenario: 相同 workspace 与只读 Service
- **WHEN** Agent/Files 写入 workspace 或共享子范围，Service 分别以只读、读写和无 workspace 权限运行
- **THEN** 读写共享同一数据，只读不能写，无授权不可访问；私有历史/Memory 始终不可由 Service 或 Host 普通共享目录直接读取

#### Scenario: 删除、导出与恢复
- **WHEN** 具有共享文件的 Work 停止、移除 Service、冷导出/导入或显式清理留存卷
- **THEN** 原有身份、数据留存、完整快照与授权清理规则保持，共享挂载不隐藏已有文件、遗漏快照内容或绕过引用检查

### Requirement: 正常停止与重建 Guest 保留完整安装

正常退出、再次启动、清除可重建缓存或替换同版 RootFS SHALL 保留管理员、模型/凭证引用、Work 定义/配置、Session/Memory、workspace、Service 定义和声明持久的数据。恢复 SHALL 遵守原 Work 运行意图和 Service enabled 状态，不自行重置配置。已有数据盘缺失、损坏或格式不支持时 SHALL 明确失败，不静默重新格式化。

#### Scenario: 完整二次启动
- **WHEN** 首次安装写入账号/配置、真实 Work 文件/历史及 Service 业务数据后正常关闭并再次启动
- **THEN** 原身份和字节保持，允许的 Work/Service 恢复后可从 Host 访问，数据库完整性检查成功，不要求重新 QuickStart

#### Scenario: 清缓存或持久盘异常
- **WHEN** 只删除可重建缓存，或发现记录中的持久盘缺失/损坏
- **THEN** 前者仅重新提取只读运行资源并恢复原安装，后者报告持久数据故障并保留剩余文件，均不自动创建空安装冒充恢复

### Requirement: 如实说明直接可访问与镜像内数据

交付说明及 launcher 帮助 SHALL 列出共享目录的 Host/Guest/Work 路径，以及 ext4 镜像中的 Core、私有卷、workspace 非共享文件和 Service 数据。SHALL 说明普通文件共享不等于完整备份，完整备份需要正常停止后的磁盘及关联共享目录；运行中不得同时在 Host 读写挂载该 ext4 镜像。

#### Scenario: 用户查找数据或备份
- **WHEN** 用户查看 `--help` 或交付说明
- **THEN** 能确定哪些文件可直接编辑、哪些保存在镜像内，以及如何正常停止并保存完整安装，不被告知 `data/` 单独就是全部数据库和 Work 的备份
