# Design

## Context

动机见 `proposal.md`。影响本设计的现状：

- Guest rootfs 由 `scripts/rootfs-assemble.sh` 用 `mke2fs` 从 `dist/rootfs.tar` 构建，安装包列表在镜像内的 `usr/share/doc/*/copyright`（167 份）与 `usr/share/piwork-guest-packages.txt`。
- 许可证实物：内核与 QEMU 的文本已在 `provenance/kernel.COPYING`、`qemu/licenses/`；Go 与 `x-sys` 在 `provenance/licenses/`。缺的只是 Guest 镜像内部这一块。
- `scripts/bundle.py` 以确定性方式打包（条目排序、固定权限、`mtime` 0、gzip `mtime` 0），payload 直接决定产物字节。
- `debugfs`（e2fsprogs）已是构建前置，`scripts/release.py` 已用它只读读取包清单。
- 产物体积约 390 MB / 408 MB，发布资产上传耗时明显。

## Goals / Non-Goals

**Goals:**

- 让收到产物的人**不启动 VM** 就能读到 Guest 内每一类组件的许可证文本。
- 提取与打包保持确定性、只读、无需 root。
- 缺口如实记录，不静默省略。

**Non-Goals:**

- 不提取 Debian 源码；对应源码仍由发布说明的书面提供覆盖。
- 不做 SPDX 归类或文本改写。
- 不改动 `qemu/licenses/`、`provenance/licenses/` 的既有处理。

## Decisions

### D1：用单次 `debugfs rdump` 提权树，而不是挂载或逐文件读取

`debugfs -R 'rdump /usr/share/doc <dir>'` 一次导出整棵文档树，再从 `<dir>/*/copyright` 中选取。只读、不需 root、不挂载，且与 `release.py` 已有的 `debugfs` 用法一致。

- 备选：loop 挂载 ext4 —— 需要 root，且在 CI/容器里容易失败。
- 备选：逐文件 `debugfs -R 'cat ...'` —— 167 次进程启动，慢且易错。
- 备选：`e2cp` 或 `libguestfs` —— 引入新依赖，收益不抵成本。

实现时必须检查 `debugfs` 是否存在并给出明确错误，而不是让后续步骤以晦涩方式失败。

### D2：许可证树布局与索引

```
dist/guest/guest-licenses/
  <package>/copyright
  index.json
```

`index.json` 每个条目记录：组件名、来源包、相对路径、大小、sha256；无可提取文本的包记录 `present: false` 与原因。索引让"缺了什么"可见，而不只是"有什么"。

### D3：确定性打包

沿用 `bundle.py` 既有规则：条目排序、权限 0444、`mtime` 0、`uid/gid` 0、gzip `mtime` 0。许可证树作为 payload 的一部分，路径前缀 `provenance/guest-licenses/`。

- bundle manifest 版本保持 2：文件格式未变，只是多了一批文件。

### D4：发布侧额外提供 `guest-licenses.tar.gz` 资产

树同时打进产物和单独资产。资产让读者不必下载约 400 MB 的产物就能阅读；打包规则与 D3 相同。

- 备选：只做产物内嵌 —— 可用但不好用，拒绝。

### D5：BusyBox 不单独处理

BusyBox 来自 rootfs 的 `busybox-static` 包，其 `copyright` 就在同一棵文档树里；initramfs 中的二进制只是该包 `/bin/busybox` 的副本。因此 D1 的提取天然覆盖它，无需第二条路径。实现时需确认包名，并把结果写进索引。

### D6：提取属于构建，不属于发布

新增文件进入 payload 会改变产物字节，因此提取必须发生在 `make guest` 阶段；发布步骤只负责把 `dist/guest/guest-licenses/` 打成资产并更新说明。这样"产物自带许可证"对任何构建路径都成立，而不只在走发布流程时成立。

## Risks / Trade-offs

- [`debugfs` 不存在或版本差异导致 `rdump` 行为不同] → 构建前置显式检查并给出明确错误；只依赖 `rdump` 这一稳定子命令。
- [167 个包的许可证文本会增加产物体积] → 实现后测量实际增量并在任务中记录；若显著，考虑对许可证树单独压缩存放。
- [部分包没有 `copyright` 文件] → 索引记录 `present: false`，不伪造也不省略。
- [payload 变化使既有产物 hash 改变] → 属预期；发布清单与验收声称本就以锁定输入为准。
- [文档树中出现符号链接或异常路径] → 只接受常规文件的 `*/copyright`，其余跳过并计入索引缺口。

## Migration Plan

无需用户侧迁移：新构建的产物自带许可证树，既有安装不受影响。下一次发布自然包含该资产；已发布的 v0.1.0 保持不变。
