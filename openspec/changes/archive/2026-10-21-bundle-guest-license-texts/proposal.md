# Proposal

## Why

v0.1.0 公开发布的产物内含 Guest 镜像，其中分发 167 个 Debian 包与 initramfs 中的 BusyBox。这些组件的许可证文本目前只存在于 `rootfs.ext4` 内，不启动 VM 就无法阅读，发布说明因此只能把"文本在镜像内部、不可直接阅读"列为已知限制。对公开发布而言这是真实的可读性缺口：收到产物的人应当能直接看到每类组件适用什么许可，而不必先引导一台虚拟机。

## What Changes

- 构建 Guest rootfs 之后，从镜像中提取每个已安装包的 `/usr/share/doc/<pkg>/copyright`，连同 initramfs 中 BusyBox 的许可证，生成一棵结构化许可证树。
- 许可证树以确定性方式（条目排序、固定权限、`mtime` 0）打入产物 payload 的 `provenance/guest-licenses/`，并附一份索引，列出组件名、来源包与对应的许可证文件。
- 每个发布额外附一个 `guest-licenses.tar.gz` 资产，读者不必下载约 400 MB 的产物即可阅读。
- 发布说明的"已知限制"一条改为正向陈述：许可证文本随产物提供且路径明确。若某个包确实没有可提取的文本，索引如实标注该缺口，而不是静默省略。
- 提取必须只读：不挂载镜像、不要求 root 权限，使用 `debugfs`（e2fsprogs 已是构建前置）。

不在本次范围：

- 不提取或归档 Debian 源码；对应源码仍由发布说明中的书面提供覆盖。
- 不对许可证文本做 SPDX 归类或内容改写，只保证可读、可定位、可核对。
- 不重复处理 QEMU 依赖与 Go 模块的许可证 —— 它们已在 `qemu/licenses/` 与 `provenance/licenses/` 中随产物提供。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `microvm-single-binary-delivery`：新增一条要求 —— 产物必须随附可直接阅读的第三方许可证文本，且不得要求启动 VM 才能取得。

## Impact

- `scripts/rootfs.py` / `scripts/rootfs-assemble.sh`：镜像构建后提取许可证树。
- `scripts/bundle.py`：把许可证树加入 payload 的 `provenance/`，保持确定性打包。
- `scripts/release.py`：发布说明措辞调整，并在资产清单中增加 `guest-licenses.tar.gz`。
- `README.md` / `README.zh-CN.md`：发布一节说明该资产与许可证位置。
- 构建依赖：新增对 `debugfs` 的显式依赖（已在 e2fsprogs 中，当前构建环境已具备）。
