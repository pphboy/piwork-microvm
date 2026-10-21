# Design

## Context

动机见 `proposal.md`。以下是影响本设计的现状与约束。

- 现状：唯一的版本身份是上游 Piwork 的 `0.0.9-a6c36da16ebc-0e1261f05b9d`；`git tag -l` 为空；启动器无 `--version`（`internal/launcher/run.go` 里的 `Version int` 是 `installation.json` 的 schema 版本，与产品版本无关）。
- `dist/delivery.json` 由 `scripts/acceptance-record.py` 在**验收步骤**写出，且是 `openspec/changes/support-windows-and-disk-only-storage/evidence/two-port/artifacts.json` 的同源副本；`dist/` 被 gitignore。
- `scripts/rootfs-assemble.sh` 用 `mke2fs` 生成 ext4，未固定 UUID，因此每次重建 `rootfs.ext4` / `state.qcow2` 字节都不同，最终产物 hash 随之改变。README 已声明不承诺逐字节重现。
- 许可证现状：上游 Piwork 为 Apache-2.0（可再分发）；Linux 6.6.159 **未打补丁**（`guest/patches/` 为空）；QEMU 10.0.8 带 2 个补丁（`guest/qemu/private-pipe.patch`、`guest/qemu/pipe-poll.patch`）；`dist/qemu*/licenses/` 随产物提供 QEMU 依赖与 Go 模块许可证。
- 产物体积：Linux 约 390 MB，Windows 约 408 MB。仓库托管在 GitHub，`gh` 2.46.0 已安装并以 `pphboy` 登录，当前无任何 Release。
- 仓库约定：构建产物、VM 磁盘、运行时状态与凭证不进 Git（`AGENTS.md`）。

## Goals / Non-Goals

**Goals:**

- 让包装层拥有自己的版本身份，并让产物能自报版本。
- 让发布可重复：同一条门槛、同一份清单结构、同一套资产命名。
- 让验收声称在产物字节不可复现的前提下仍然**准确**，不产生任何过度声称。
- 让公开发布满足 GPL 对应源码义务，且不把发布能力混进构建流程。

**Non-Goals:**

- 不追求字节可复现构建。本设计接受"每次重建字节不同"，并据此设计验收声称的基准。
- 不引入 CHANGELOG 文件；GitHub Releases 与 tag 即发布记录。
- 不解决 Guest rootfs 内分发包许可证未随附的问题；只要求如实披露。
- 不做代码签名、公证或自动更新。Windows 产物未签名带来的 SmartScreen 提示属于已知现象。
- 不改变任何运行期行为：VM 启动、网络、磁盘与持久化语义均不受影响。

## Decisions

### D1：版本以 annotated tag 为事实来源，构建时注入

自身版本与上游版本解耦。发布版本由 annotated git tag 唯一确定；构建时经 `go build -ldflags -X` 注入到启动器包，`--version` 读该注入值。

- 备选：仓库内提交 `VERSION` 文件 —— 会与 tag 漂移，且多一处需要同步的状态。
- 备选：写进 `build.lock.json` —— 该文件描述的是**输入**（上游 commit、工具链），不是本产品的版本。
- 备选：直接沿用上游版本号 —— 会把两条版本轴绑死，只改 launcher 时无法命名新版本。
- 非发布构建注入 `0.0.0-dev.<短 sha>`，与任何发布版本可明确区分。

### D2：发布清单独立于验收记录

新增 `release-manifest.json`，由构建/发布步骤产出。**不**复用 `dist/delivery.json`：后者是验收步骤的产物，复用会让"发版"必须先跑完验收，与快门槛直接冲突；而且它是验收证据的副本，字段语义属于验收而非发布。

- 备选：改造 `delivery.json` 为发布清单 —— 需要把它从验收步骤解耦，且要清理其中验收专属字段，收益不抵风险。
- 清单是**发布资产**，不提交进仓库，与"构建产物不进 Git"的约定一致。

### D3：验收声称以锁定输入为基准

清单的 `verification` 组显式记录基准，取值区分"锁定输入"与"产物字节"。在产物字节不可复现的前提下，本设计的取值恒为锁定输入，并要求同时记录：跑了哪些平台、何时、证据路径、以及哪些平台**未**运行。

- 备选：让验收绑定产物 hash —— 需要先实现字节可复现，属于独立变更（见 Non-Goals 与 Risks）。
- 该设计使"发布"与"已验证"成为两件可分别陈述的事，避免把输入级证据读成产物级验证。

### D4：资产名带版本号

资产命名为 `piwork-microvm-v<version>-linux-amd64`、`piwork-microvm-v<version>-windows-amd64.exe`，各配 `.sha256`。

- 备选：固定名 `piwork-microvm` —— 不同版本下载到同一目录后无法分辨，且与仓库内 `dist/` 的本地产物路径语义混淆。
- 代价：`releases/latest/download/<固定名>` 这类直链不可用，稳定指针只能是 Release 页面。接受该代价。

### D5：发布边界落在两个独立目标上

`make release VERSION=<v>` 只执行 preflight / test / build / manifest / notes（步骤 1–5），产物全部落在本地。`make release-publish VERSION=<v>` 执行 tag 与 `gh release create`（步骤 6–7）。

- 备选：单一命令加 `--publish` 开关 —— 边界只存在于参数里，不如两个目标在 Makefile 中可见、可审计。
- 该切分让"构建流程不发布"成为结构性事实，而不是约定。

### D6：GPL 对应源码用"补丁资产 + 书面提供"

发布说明的"对应源码"一节写明：Linux 6.6.159 未修改，对应源码为上游 tarball，其 sha256 已锁在 `build.lock.json`；QEMU 10.0.8 由 2 个补丁修改，补丁源码以 `qemu-patches.tar.gz` 随发布提供，上游 tarball 同样按锁定 sha256 指明；并给出 GPL §3(b) 的书面提供承诺。

- 备选：把完整源码 tarball 一并作为资产（约 280 MB）—— 在仅有两个小补丁的前提下不必要；若将来需要更保守的分发姿态，可单独追加，不影响本设计。

### D7：`--version` 与 `--help` 同级，不触碰虚拟化与数据

`--version` 输出三行：自身版本、上游 Piwork 版本与完整 commit、bundle manifest 版本。它 SHALL 像 `--help` 一样在读取任何安装目录、检查加速器或绑定端口**之前**返回，退出码为 0。

- 该顺序与现有 `--help` 的处理一致（`internal/launcher/run.go` 中 `--help` 在任何副作用之前返回），避免 `--version` 变成需要 KVM 才能运行的操作。

## Risks / Trade-offs

- [产物字节不可复现，验收永远无法绑定到发布产物] → 以锁定输入为声称基准，并在清单中显式记录基准字段；字节可复现留作独立变更。
- [快门槛意味着某平台可能在未验收的情况下随发布出海] → 规格强制如实标注未运行平台；清单与发布说明均须出现该状态，不得出现暗示通过的表述。
- [Windows 产物未签名，公开下载会触发 SmartScreen 提示] → 在发布说明中说明；签名不在本次范围。
- [Guest rootfs 内分发包许可证未随附] → 规格要求显式列为已知限制；后续独立变更解决。
- [`gh` 是可选的构建期外依赖] → preflight 检查 `gh` 存在且已认证并提前失败；且发布是独立目标，构建流程不依赖它。
- [`-ldflags -X` 的变量路径写错时会静默不注入] → 用聚焦测试断言 `--version` 输出非空且形如预期，覆盖发布与非发布两种构建。
- [资产各约 400 MB，上传耗时且可能中断] → 接受；不为此引入分卷或压缩改造。

## Migration Plan

无需迁移：仓库尚无任何已发布版本，`v0.1.0` 是首个。既有安装不受影响，因为本变更不改变任何运行期行为。

回滚：删除 tag 与对应 GitHub Release 即可；构建与本地产物不受影响。
