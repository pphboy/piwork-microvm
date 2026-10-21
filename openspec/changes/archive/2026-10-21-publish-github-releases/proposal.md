# Proposal

## Why

本仓库目前没有自己的发布概念。唯一的版本身份是上游 Piwork 的 `0.0.9-a6c36da16ebc-0e1261f05b9d`：没有 git tag，启动器报不出自身版本，构建流程明确不发布任何东西，产物 hash 只存在于一份被 gitignore 的验收记录里。要开始迭代对外版本，包装层需要自己的版本身份、可重复的发布门槛，以及一个满足 GPL 对应源码义务的发布步骤。

## What Changes

- 引入 piwork-microvm 自己的语义化版本，与上游 Piwork 版本**解耦**。annotated git tag 是唯一事实来源，首个公开版本为 `v0.1.0`；它打包的上游 pin 记录在清单中，不参与本仓库版本号。
- 启动器新增 `--version`，输出自身版本、上游 pin（版本 + 完整 commit）与 bundle manifest 版本；非发布构建报 `0.0.0-dev.<短sha>`。今天启动器无法回答"我是哪一版"，迭代发布后这会立刻成为支持成本。
- 新增发布清单 `release-manifest.json`，由构建/发布步骤产出，字段分三组：`inputs`（锁定输入身份，跨重建稳定）、`artifacts`（本次两产物的路径、大小、sha256）、`verification`（验了什么、依据是什么、何时、哪些平台）。
- 发布门槛为**快门槛**：工作区干净、`make source-check` 通过、`go test ./...` 通过、两平台产物构建成功。验收状态按**锁定输入**记录，不按产物字节。
- 新增独立发布步骤：打 annotated tag，用 `gh release create` 发布公开 GitHub Release，资产包含两个二进制、各自 `.sha256`、`release-manifest.json` 与 QEMU 补丁源码归档。
- 发布说明包含"对应源码"一节：Linux 6.6.159（未修改，指向上游 tarball 与 `build.lock.json` 中的 sha256）、QEMU 10.0.8（含 2 个补丁，补丁源码随资产发布）、以及 GPL §3(b) 的书面提供承诺。
- 明确验收声称的**基准**：Guest ext4 rootfs 使用随机 UUID，每次重建产物字节都不同，因此验收证据只能支持"输入级"声称，不得表述为"该产物字节已通过验收"。
- 修改 `microvm-single-binary-delivery` 中"构建流程 SHALL 不推送镜像、远程仓库或发布 Release"一句：保留"构建不推送镜像/远程仓库"和"容器镜像始终仅本地"的约束，明确公开 Release 由**独立发布步骤**执行，而非构建流程的一部分。

不在本次范围：

- 不追求字节可复现构建（固定 ext4 UUID、归一化时间戳）。它能让验收绑定产物 hash，但属于另一个量级的改动，留作后续独立变更。
- 不新增 CHANGELOG 文件；GitHub Releases 与 tag 作为发布记录，避免再引入一个会与 tag 漂移的文件。
- 不解决 Guest rootfs 内 Debian 包许可证未随附的问题（产物目前只带包清单）。公开发布下这是真实缺口，本次在发布说明中**显式记为已知限制**，不掩盖。

## Capabilities

### New Capabilities

- `microvm-release-publication`：包装层自身的版本身份、发布门槛、发布清单、公开 Release 的发布步骤，以及验收声称的基准与 GPL 对应源码义务。

### Modified Capabilities

- `microvm-single-binary-delivery`：修改"提供可复现输入和真实来源身份"中关于不发布 Release 的表述，改为区分构建流程与独立发布步骤。

## Impact

- `internal/launcher`：新增 `--version` 及其输出格式。
- `cmd/piwork-microvm` / `scripts/bundle.py`：构建时经 `-ldflags -X` 注入版本；非发布构建回退为开发版本号。
- 新增 `scripts/release.py` 与 `Makefile` 的 `release` 目标，实现七步流程与发布边界。
- 新增发布说明模板（含对应源码一节）。
- `README.md`：新增发布一节，说明版本、资产与验收声称基准。
- 运行期行为不变：不改变 VM 启动、网络、磁盘或持久化语义；不改变既有命令行参数的语义。
