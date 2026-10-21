# Design

## Context

动机与范围见 [proposal.md](proposal.md)。基线为 GUI 已归档提交 `0aa2fa5`，不重做其 CoreLoop、语言偏好或日志导出实现。本变更横跨 Guest 构建、启动参数及两个平台产物，需要本设计；不引入新架构。

已只读核实的事实：

- 上游冻结 main 为 `29e3471e02e53094c1e1f427a88de6a2a24fb963`，第二父提交是已核验的 `19f3e0f78deabbdf67f7db997c6d276b6dfda145`；`package.json` 声明 `0.0.10`。后续规格归档提交不属于此次代码输入。
- `scripts/source.py` 已支持本地 clone mirror、精确 detached checkout、干净副本和官方 origin 校验；`--refresh-lock` 会追逐远程 HEAD，本次不使用。
- `scripts/piwork.py`、`rootfs.py` 和 `cmd/piwork-guest` 仍使用 `piwork-serve`。新入口仅接受 `--ui-port`、`--core-port`、`--data-dir`，保留 `app.listening` 与 SIGTERM 收尾；不能继续传旧 `serve`、`--listen`、`--core-listen`、`--public-origin`、`--no-open`。
- QEMU 当前把两个 Host 端口转发到固定 Guest 17891/17871，Guest 只接收 Host UI 端口。新 Core 校验实际监听端口对应的 Host/Origin，并保留内部 Agent RPC 7172。
- `/mnt/state/core` 已 bind 到 `/var/lib/piwork/core`，Docker/containerd 和卷也已在 ext4。新版 Core 的持久 `logs/` 在其数据目录内，不需额外挂载或共享。
- 新 Desktop 的管理员账户菜单已有唯一 `Export logs`；创建/查询及下载经 `/_desktop/api/log-exports`，内容地址为 `/_desktop/api/log-exports/<id>/content`。上游已有相关来源、脱敏及缺口规则，Launcher 不复制这套功能。

## Goals / Non-Goals

**Goals:** 使用冻结提交和现有工具链完成最小入口/端口适配，证明新 Guest 的业务故障 ZIP 在两平台真实 GUI 路径可取，并验证旧盘副本的安全恢复。

**Non-Goals:** 不修改上游业务源码、Kernel/QEMU 版本、磁盘格式、发布体系或 GUI 设置；不增加反向代理、诊断平台和上传端。不扩展模型调用、全部署/网络矩阵或重跑已接受的 GUI 布局与全故障测试。

## Decisions

### D1. 一次统一构建，冻结真实身份

只更新 `build.lock.json` 的 Piwork 输入字段，记录实际取得该冻结提交的时间和 main 来源。沿用 `PIWORK_SOURCE=/home/p/Projects/piwork`，让现有 source 流程创建按提交分目录的干净构建副本；不要求相邻工作区清空或重置，也不复制其未提交内容。实际副本须满足 commit、tree、`modified=false`、无补丁校验；main 的后续前进不改变锁。

由本仓库的 `make guest PIWORK_SOURCE=/home/p/Projects/piwork` 统一构建上游 Core/CLI、生产 Agent/Helper、镜像归档与 Guest；将现有构建/拷贝/帮助冒烟中的旧二进制名称替换为 `piwork-core`。main 不再重复构建同批资源，Kernel/QEMU 沿用既有锁与资源。Guest 完成后，沿原 Linux GUI 和 Windows 原生 Go/MinGW 构建入口生成主体，再用现有 `bundle.py --entry gui` 分别附加新资源；不对两个 GUI 各重复构建一遍 Guest。

记录源码声明 `0.0.10`、完整 commit、真实 dirty 状态、上游镜像身份和 wrapper 开发版本；不注入虚构 `0.0.11`、正式 release override 或修改官方发行记录。保持 metadata、许可证、manifest、SHA 和 EOF Trailer；检查新 Guest/资源身份，不能只因缓存存在就当成升级。相同 Kernel/QEMU 可复用，旧 Guest payload 不复用。CLI 仅做受影响的构建、help/version、参数及一个真实自定义端口路径证明，不扩大旧发行矩阵。

备选的从 main 工作区直接拷贝二进制、构建时重新解析最新 HEAD、修改发布系统均不采用。

### D2. 两个选定端口贯穿 Host 与 Guest

统筹已裁决：保持两个 IPv4 回环入口、默认 UI 17891/Core 17871；合法自定义端口传入 Guest 后实际监听同一端口。沿现有内核命令行传配置，保留 UI 参数并补 Core 参数；QEMU 的两个 `hostfwd` 目标使用对应选值。Guest 启动原版 `piwork-core --ui-port <PORT> --core-port <CORE_PORT> --data-dir /var/lib/piwork/core`。Guest 内 Core 客户端/探针如有固定地址，同步使用实际 Core 端点；不把 Host 回环概念当作跨 VM 地址。Launcher 的健康检查与系统浏览器继续使用实际 Host URL。

UI/Core 参数均在 CLI 解析和共享服务的环境/数据访问之前拒绝 7172，解释内部 Agent RPC 保留原因；保留相同、越界、占用与绑定竞争检查，不自动换端口，不发布第三个入口。Guest 参数也做必要有效性校验。GUI 无设置变动，仍用默认值。

不新增反向代理，不放宽上游 Host/Origin/CSRF。修改既有 QEMU/Guest 参数断言和端口证明脚本，只以一对常规自定义端口实际验证 Guest 监听、内部 Core、浏览器登录和请求；7172 分别作为 UI/Core 的拒绝补针对性回归，证明没有访问加速器或创建数据。其余原有来源、端口 80 规范化和授权契约保留，不把本次常规端口实测写成完整端口矩阵；遇到确实影响交付的可复现问题短报，不擅自改上游或增加代理。

### D3. 原盘副本恢复，不做迁移器

安装元数据、Guest ext4 标记、Core 路径、Docker/卷布局和 GUI 偏好格式保持不变。使用已明确归属测试的旧安装：确认全部写者安全退出后，把 `installation.json` 与无 backing 依赖的 `disks/state.qcow2` 成组备份到专属验收根；保留来源不写，实际启动只针对副本。不要对用户现有 VM、盘或服务操作。

副本启动后核对原安装 ID、管理员/配置和可核对的 Work 文件、Service 持久值；安全停止并以同一副本重开，再核对这些值及新增 Core 日志确在 ext4。保留 GUI 英文默认、切换及已有语言选择，不重新实现偏好。兼容检查失败则保留副本和错误，不重置、格式化或新建空安装。回退只能使用未升级的停机备份与原产物，不声称旧二进制能回滚读取已升级的副本。

备选的自动数据迁移、宿主目录映射和直接升级用户原盘均不采用。

### D4. 复用 Desktop 业务导出，聚焦真实验收

Windows/WebView2/WHPX 与 Linux/WebKitGTK/KVM 分别实际打开新 GUI，用专属安装/配置走启动、真实 `/healthz`、系统浏览器和新版 Desktop。每平台使用已有受控测试服务/生产运行时生成可关联 Work/Service 的真实故障输出、普通标记及合成敏感值，不调用真实模型、不增加产品模拟开关。

从管理员账户菜单唯一 `Export logs` 导出，等待真实收集/打包与浏览器下载，保存到 Host 并打开 ZIP，核对清单、Core 和相关应用来源、故障标记及脱敏。以专属测试来源制造一个上游支持的可控缺口，核对 UI 与 `manifest.json` 的部分结果一致；只影响测试来源。可复用同一受控夹具和两平台操作步骤，不重演上游全部幂等/故障/授权矩阵，不把浏览器开始下载当作已经保存。

Launcher 现有运行错误导出继续服务于 Core 尚未启动的情形；不把它与 Desktop 业务故障 ZIP 混同。现有双语 README、帮助、构建/排障说明同步入口、7172 限制、数据/日志位置、开发身份、保存后自行发送及已测边界。原始技术日志与 Guest 原版 UI 的语言不由 Launcher 翻译。

实施后运行一次 `go test ./...`，补本次参数、来源/身份和构建脚本的必要回归；只有改到相应并发逻辑才追加 race。保留已通过且不受影响的 GUI 历史证据身份，记录当前产物和新输入的实际结果，不重新勾成新验收。按 AGENTS 分规划、功能及其回归、跨功能文档、验收提交；不 push、发布或自行归档。

## Risks / Trade-offs

- [冻结输入与后续 main/旧缓存混淆] → 按完整 SHA 构建独立副本，检查源码、镜像、Guest manifest 和真实运行身份；不改变冻结提交。
- [端口只改一侧导致来源或内部客户端错误] → 同时传入 UI/Core，保留两个回环转发；补一个实机自定义路径及 7172 提前拒绝，不扩矩阵。
- [升级写坏原安装或误称空盘为恢复] → 仅运行停机完整备份副本，先后核对原身份和实际持久值；兼容失败保留字节。
- [导出有包却无相关来源或凭据泄漏] → 解包核对故障标记、已知敏感值和清单缺口；HTTP/静态/单元结果不冒充真实 GUI 交付。

## Migration Plan

apply 获准后按任务顺序锁定输入、适配、统一重建，再以停机副本验收。新用户继续正常首次引导；已有用户数据不自动迁移或删除。本轮只落规划，等待单独 apply。
