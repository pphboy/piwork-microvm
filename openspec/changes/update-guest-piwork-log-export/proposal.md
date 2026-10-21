# Proposal

## Why

已归档的桌面 Launcher（`0aa2fa5`）仍携带 Piwork 0.0.9 和旧 `piwork-serve` 入口，不能交付上游刚完成的 Desktop 故障日志导出。本变更只升级 Guest 输入和必要适配，使用户从现有 GUI 打开新版 Desktop，将真实故障日志 ZIP 下载到 Host。

## What Changes

- 锁定 **CORE_MAIN_READY `29e3471e02e53094c1e1f427a88de6a2a24fb963`**（已确认包含 `19f3e0f78deabbdf67f7db997c6d276b6dfda145`）；通过 `PIWORK_SOURCE=/home/p/Projects/piwork` 克隆干净、精确提交的构建副本，不追逐远程或后续 main HEAD、不复制工作区改动。
- 构建、装入并启动 `piwork-core --ui-port/--core-port/--data-dir`，替换旧入口及失效参数；UI/Core 默认仍为 17891/17871，自定义 Host 端口传入 Guest 并让实际监听、QEMU 转发和内部 Core 客户端一起联动，保持两个 IPv4 回环入口及原有来源校验，GUI 不新增设置。
- **BREAKING（已批准）**：UI 和 Core 选项均拒绝内部 Agent RPC 保留端口 7172，在访问虚拟化/数据前报错；同端口、范围和占用检查保留。只补一个真实常规自定义端口路径与 7172 拒绝验证，不重跑网络矩阵。
- 原安装身份、qcow2/ext4 和数据路径不变；仅用已安全停止的专属旧安装备份副本验证升级和重启恢复，不操作用户原盘。
- 重建 Piwork、生产 Agent/Helper、Guest 及 Windows/Linux GUI 的现有内嵌资源；复用 Kernel/QEMU 和原封装校验，CLI 仅做受影响的构建/端口冒烟。
- 在两平台真实 GUI 启动的新 Guest 中，从 Desktop 唯一管理员入口导出可控 Work/Service 故障 ZIP，打开核对日志、脱敏及缺口；保留默认英文/语言选择、一次安全停止和原盘副本复用。同步现有中英文说明及验收事实。

不新增诊断系统、上传服务、反向代理、GUI 设置或发布流程；不修改 Piwork 业务源码或放宽 Host/Origin/CSRF，不要求真实 AI Key，不重跑既有 GUI 全套或全部署矩阵。网络取舍已裁决，无待选方案。

## Capabilities

### New Capabilities

无；复用现有能力。

### Modified Capabilities

- `microvm-guest-runtime`：允许锁定指定的干净本地 main 合并提交，交付新 Core 入口和原版 Desktop 日志导出。
- `microvm-network-access`：Guest HTTP 端点随新版入口适配，保留 Host 两端口及来源契约。
- `microvm-launcher-lifecycle`：明确 7172 提前拒绝这一兼容限制，并使首次引导说明对应本次冻结输入。
- `microvm-persistent-storage`：用停机备份副本验证上游升级后的原身份和数据恢复。
- `microvm-single-binary-delivery`：记录新输入的两平台聚焦整合验收，更新双语构建、排障与日志交付事实。

## Impact

涉及 `build.lock.json`、`scripts/source.py`（仅必要的精确输入记录）、`piwork.py`、`rootfs.py`、Guest 入口、QEMU 端口参数及其针对性测试；现有 GUI/CLI 构建和内嵌资源流程、README 与帮助。保持 Kernel/QEMU 锁定值、安装格式、Wails CoreLoop 和发布体系。

MicroVM 链路统一构建全部上游二进制、镜像和 Guest，main 不再重复构建同批资源；后续上游规格归档提交不改变此次冻结输入。记录源码声明版本 `0.0.10`、完整 commit、真实 dirty 状态及 wrapper 开发身份，不强改为 `0.0.11` 或改官方发行记录。已观察到的兼容风险及最小验收见 design/tasks；实施、文档、规划和验收按职责提交，不 push 或发布。
