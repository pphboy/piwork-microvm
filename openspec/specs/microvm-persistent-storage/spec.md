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

### Requirement: 桌面目录偏好与业务安装根独立持久化

桌面入口 SHALL 在独立的当前用户配置位置原子保存选定的绝对安装根，复用平台默认数据规则，不在安装根内混入 GUI 偏好或 WebView 缓存。首次成功标记 SHALL 绑定该路径的有效安装身份，并且只能在真实 WebUI 健康检查成功后形成；磁盘准备元数据、一次点击或一次失败不足以形成该标记。目录设置 SHALL 在成功后默认隐藏，在未完成或失败且无本次写者时可修改。选择新目录 MUST NOT 删除、迁移、重置旧磁盘或覆盖既有安装。

#### Scenario: 默认根与已选目录
- **WHEN** 无偏好时首次打开，或有有效偏好时重新打开 GUI
- **THEN** 分别使用 Windows `%LOCALAPPDATA%\PiworkMicroVM` / Linux XDG 用户数据目录下 `piwork-microvm`，或先前选择的同一完整安装根，不受可执行文件名、位置或当前工作目录影响

#### Scenario: 复制模板后启动失败
- **WHEN** 安装元数据已表示磁盘准备完成，但 Guest 未启动或 `/healthz` 尚未成功就失败
- **THEN** GUI 不记录首次成功完成，目录设置仍可用，重试仍遵循原盘校验和不覆盖规则

#### Scenario: 记录成功并恢复原盘
- **WHEN** WebUI 确实已健康，随后正常停止、关闭 GUI 并重开
- **THEN** 默认隐藏首次目录设置，保留原目录与安装身份，再次启动使用原数据盘并恢复既有数据

#### Scenario: 偏好错误或目标安装不再匹配
- **WHEN** 偏好不可读/损坏、写入失败，或其成功标记关联的安装身份缺失/不匹配
- **THEN** 显示可理解的问题，不静默以默认目录新建空安装冒充恢复；目录选择的失败不改变已持久化的原选择，不能将陈旧成功标记用于隐藏未完成安装设置

### Requirement: 桌面语言独立原子持久化且兼容旧偏好

GUI SHALL 仅在现有 GUI 偏好文件增加一个语言字段，保存明确选择的 `en` 或 `zh-CN`，不把语言写入 Guest 业务数据或按可执行文件位置保存。无偏好或有效旧偏好没有语言字段时 SHALL 使用英文，不依据系统语言自动改为中文；旧数据根、安装身份和成功标记 SHALL 保留。切换语言 SHALL 原子保存且不改变当前安装根、身份、VM 或完成判定；选择目录和保存健康完成标记也 SHALL 保留已选语言。写入/同步/替换失败 SHALL 保留原有效偏好并提供本地化错误，不伪称新选择已持久化。

#### Scenario: 旧安装首次使用语言功能
- **WHEN** 已有 GUI 偏好含数据根和安装身份但没有语言字段，且系统语言为中文
- **THEN** 以英文打开同一安装，保留身份与完成状态，不重置磁盘或创建默认空安装

#### Scenario: 语言保存与安装状态互不覆盖
- **WHEN** 用户切换语言、重新选择目录，或当前健康完成标记被保存
- **THEN** 各自只更新对应偏好事实，保存语言不改变安装状态，保存目录/完成标记不丢失语言，重开后恢复一致选择

#### Scenario: 语言偏好保存失败
- **WHEN** 新语言选择的写入、同步或原子替换失败
- **THEN** 旧偏好和业务数据保持原状，用户获得明确的未保存提示，重开仍采用原有效语言，不假报保存成功
