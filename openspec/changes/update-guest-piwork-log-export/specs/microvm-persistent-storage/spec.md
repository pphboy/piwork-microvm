# MicroVM Persistent Storage Spec Delta

## ADDED Requirements

### Requirement: 上游升级在停机备份副本中保留原安装

升级 SHALL 继续使用原安装元数据、身份、`disks/state.qcow2`、Guest ext4 和既有 Core/Docker/卷路径。升级与重启验收 SHALL 仅使用已确认安全停止的专属旧安装完整备份副本，保留元数据与磁盘的关联；MUST NOT 写用户原盘、用新模板替换旧盘或自动重置不兼容的业务安装。上游数据兼容失败 SHALL 明确报告并保留原文件，不声称升级或回滚成功。

Core 新增的持久日志 SHALL 位于原 Core 数据挂载内，和既有管理员、配置、Work 文件及 Service 持久数据一起保留；GUI 偏好及语言选择继续保存在现有 Host 配置文件。升级后 SHALL 以一次真实安全停止、原副本再次启动及原有身份/数据核对证明恢复，不以重新 QuickStart 建立空安装代替恢复。

#### Scenario: 新 Guest 使用旧盘副本并重启
- **WHEN** 新产物使用专属旧安装的停机备份副本启动，安全停止后再以该副本启动
- **THEN** 原安装身份、管理员、配置、可核对 Work 文件及 Service 数据保持，新持久日志位于 ext4，已有语言偏好未被安装完成写回覆盖

#### Scenario: 升级失败时保护原安装
- **WHEN** 副本无法通过原有磁盘或上游存储兼容检查
- **THEN** 启动明确失败且不重建磁盘，用户原盘与备份来源保持原状，验收保留失败原因及未验证项
