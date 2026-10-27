# Proposal

## Why

Windows MicroVM 的 libslirp Host 转发监听队列过小，浏览器并发加载资源时可能大量连接被拒绝，页面因此无法启动。Linux 交付的 Debian libslirp 也包含同样的 `listen(s, 1)`，虽尚未复现同等故障，但存在相同容量缺口；页面自身的失败恢复由 Piwork 的配套变更负责。

## What Changes

- 修复 Windows 与 Linux 各自打包的 libslirp 转发监听容量，使两个回环入口能承受正常浏览器的并发连接。
- 将两平台实际生效的 libslirp 源码、补丁和工具链纳入锁定、缓存失效、制品与对应源码校验，避免复用旧 DLL／SO 或遗漏来源。
- 使用原生 Windows 和 Linux 真实网络请求对两个转发端口执行固定并发回归，并验证最终打包运行链路及基本登录／工作台加载。
- 保持现有 Host 回环、端口配置、Host/Origin、身份和数据边界；不新增代理、端口或自动发布。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `microvm-network-access`: 明确两平台两个 Host 回环转发入口对浏览器并发连接的要求与原生回归。

## Impact

涉及 `guest/qemu/`、`scripts/qemu.sh`、`scripts/qemu-windows.sh`、`build.lock.json`、两平台 QEMU 组件缓存、打包、来源和相关测试／验收。Windows QEMU wrap 的 libslirp 与 Linux Debian 固定包来源分别验证；现有许可证和对应源码要求继续有效。Piwork 仓库同名 `fix-page-loading-blocked` 变更负责三套入口的启动和读取恢复；两侧实现后方可完成组合验收。本变更不授权对外发布。
