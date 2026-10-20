# 原生 Windows 启动关口（开发资源，非最终产物验收）

日期：2026-10-20。Host 为 Windows 11 家庭版中文版，10.0.26200，AMD Ryzen 9
7945HX；WHPX 已启用。测试从 Windows PowerShell 执行 Windows 本地目录中的 PE，
QEMU、DLL、kernel、RootFS 和数据盘均在 `C:\Users\p\AppData\Local\PiworkMicroVM-gate-20261020`。
构建由 Linux/WSL 完成，运行进程不调用 WSL。此关口不能替代后续两个最终单文件的业务验收。

实际参数见 [windows-gate.argv.json](windows-gate.argv.json)，包括临时 `-S`/跟踪选项；
经 QMP `cont` 启动。QEMU 为本项目从固定 10.0.8 源码构建的 headless PE；原生
`-accel help` 只列出 `whpx`，`-machine help` 有 microvm，设备列表包含
virtio-blk/net/serial/rng-device。没有 TCG、PCI 设备或共享设备。

## 实测结果

- Linux 6.6.159-piwork 正常启动，MP 表识别并启动两个 vCPU。
- `/dev/vda` 为只读系统盘，`/dev/vdb` 在 `/mnt/state` 挂载为读写 ext4。
- Guest 得到 DHCP `10.0.2.15/24`，网关 `10.0.2.2`，DNS `10.0.2.3`。
- 最终 DNS 查询返回 example.com 的 A/AAAA；Guest 的带 DNS HTTPS 请求得到 HTTP 200。
- WHPX API 返回处理器时钟 2495263 kHz；共同内核使用对应 `tsc_early_khz` 和可靠
  TSC。Guest `date -u` 为 06:18:24 UTC，与同次 HTTPS 返回的 Date 一致。
- Guest Docker 与原版 Piwork 服务均 active；主机 `http://127.0.0.1:8080/healthz`
  得到 `{"status":"healthy"}`。
- QMP/QGA 通过两个 Windows named pipes 并行连接，创建时 DACL 只有当前用户
  一项。连续执行 QMP 状态/寄存器请求、QGA 文件读取与真实 Guest 命令。
- 父进程关闭自身安装/磁盘锁句柄后，QEMU 继承的句柄仍阻止重新取得这两把锁。
  原生 Windows Go 测试另验证硬链接文件身份和子进程继承保护。
- Guest 写入 `/mnt/state/native-probe`，执行 sync 并读回相同内容。
- 依次停止 Piwork、Docker，sync，卸载 Core/containerd bind 及 `/mnt/state`，
  确认成功后才完成 QEMU 退出。`reboot=t` 的 triple fault 在 WHPX 中打印
  `Unexpected VP exit code 4`，本次进程退出码为 0。正式 launcher 采用已确认
  数据盘卸载后 QMP quit 的路径，避免依赖此异常表现。

## 已定位并修复的问题

1. Win32 默认 named-pipe DACL 含 Everyone/Anonymous 读权限，单独设置进程 token
   默认 DACL 无效。`private-pipe.patch` 在 QEMU 创建管道时显式应用该 DACL。
2. 管道前端暂停读时，原轮询可饿死 GLib/QMP 调度，出现 capabilities 超时。
   `pipe-poll.patch` 处理读背压和失败的 PeekNamedPipe。
3. 初始 max CPU 组合未正常启动；off IRQ 在双核 Guest 中出现 IPI 等待。实际参数
   收敛为 `qemu64`、`whpx,kernel-irqchip=on`，保持 microvm/MMIO。
4. 无参考计时器时 TSC 校准失败会退到慢的 refined-jiffies。使用 WHPX 报告频率
   初始化 Guest TSC 后，时钟和服务准备恢复。
5. Windows 默认 FD_SETSIZE=64，65 个转发 socket 会遗漏后续 UDP socket，导致
   Guest DNS 超时；原生独立 UDP DNS 查询正常。编译 QEMU 时设置 1024 后，在相同
   65 条转发和相同 DNS 环境中，DNS/HTTPS 均通过，无新增 DNS daemon 或监听。

详细本机输出：`dist/windows-gate-native.log`、`dist/windows-native-capabilities.txt`、
`dist/windows-native-tests.log`、`dist/qemu-windows-fixed-build.log`。固定工具链、
184 个 RPM 的来源/sha256 和完整包身份在 `guest/qemu/windows-toolchain.lock.json`。
所有 Piwork 二进制/镜像来自未修改的 `9a40d4443fee559335485744d0aabbf186e24b38`，
release ID 为 `0.0.8-9a40d4443fee-8093dd5fbc88`。

尚未在此关口声明：真实 Work/Service/Files、最终 PE/ELF 冷启动与恢复、最低 Windows
版本、第二台干净 Host、真实 AI 供应商调用。它们保留在各自后续任务中。
