# Proposal

## Why

Core 已在 Guest 中以原生二进制运行，但现有构建仍从源码编译 Core/CLI、WebUI 和生产镜像，重复处理未变化的底座；发布脚本也只覆盖 CLI，升级小版本需要人工补齐 GUI。Piwork 0.0.11 已提供可校验的官方 Linux 二进制与配套镜像，可以保留现有运行方式、缩短后续制包流程，并完成本次升级和 MicroVM v0.2.1 发布。

## What Changes

- 增加官方发行制品输入模式，构建时导入原版 `piwork-core` / `piwork-cli`，校验归档、版本、平台、实际构建提交、嵌入 UI 身份和配套镜像；保留明确选择的源码构建模式，不在输入错误时静默切换。
- 本次固定使用 Piwork `v0.0.11` Preview，分别记录实际构建提交 `a19c6f595fa6b2515d19146f3510dfc9f1ba4b8c` 与发布提交 `2142491f5103b58731de4872d153bd1b876860de`，锁定官方资产 SHA256 与 Agent/Helper 镜像 digest / image ID。
- 构建阶段取得配套生产镜像并内嵌，继续由 Guest Docker 离线加载；Core 仍由 systemd 启动，保留原数据盘、网络入口和停止语义。
- 按组件输入及输出校验复用 Kernel、两平台 QEMU 和已有系统底座缓存；一次准备 Guest，供 Windows/Linux GUI 与 CLI 封装。记录导入、镜像准备、Guest 组装、封装和上传耗时，不承诺未经实测的固定发版时间。
- 补齐四个发行产物的发布门槛、来源清单、版本校验、可读许可与独立发布步骤；使用草稿上传并校验完整资产，重试时复用已核对的同版本资产。
- 对 Piwork 0.0.11 做两平台针对性启动、实际工作台/日志导出、正常停止和旧盘备份副本恢复验证，同步现有双语构建与升级说明；完成后发布包装层 v0.2.1。

## Capabilities

### New Capabilities

无。扩展现有 Guest 输入、单文件构建与发布能力。

### Modified Capabilities

- `microvm-guest-runtime`：允许锁定官方原版发行制品输入，明确构建/发布提交和 Core/生产镜像的一致性，替换此前仅允许固定源码重建的本轮输入约束。
- `microvm-single-binary-delivery`：补充官方制品来源与按组件输入复用的构建规则，调整官方制品升级的聚焦验证范围，保持单文件资源格式、许可和用户运行前提。
- `microvm-release-publication`：门槛、清单和公开资产覆盖两平台 GUI/CLI；验收记录绑定当前完整输入，独立发布支持草稿校验和失败后的同版本重试。

## Impact

- 主要涉及 `build.lock.json`、`Makefile`、`scripts/source.py`、`scripts/piwork.py`、新增发行制品导入/校验模块、现有构建缓存与封装入口、`scripts/release.py` 以及对应测试、双语说明。
- 官方二进制模式省去上游 Node/WebUI/Go 与 Agent/Helper 的本地编译；构建时仍需要取得镜像并组装 Guest。新安装的最终产物仍自包含，运行无需 Host Docker 或在线下载依赖。
- Kernel/QEMU/Guest 系统锁、Launcher 界面和字体、上游业务代码、磁盘格式及既有历史证据保持原身份。此变更与 README 精简/演示素材变更分开推进。
- 不增加在线更新器、差分更新包、Core 容器化、CI 迁移或新 bundle 格式；四个完整发行文件的网络上传成本仍存在。
- apply 期间按用户补充的优先级继续完成二进制替换、空目录部署和 Release；已有数据的 SQLite/WAL 恢复问题保留为已知问题，原版制品不打补丁，不把全新安装通过描述为旧数据已修复。
