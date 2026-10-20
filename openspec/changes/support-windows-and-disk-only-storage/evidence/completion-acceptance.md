# 最终产物收尾验收

2026-10-21（Asia/Shanghai）。本记录对应 `support-windows-and-disk-only-storage` 本轮确认范围：现有 Linux/KVM 与原生 Windows Home/WHPX、独立全新安装、真实模型跨重启、最终产物异常退出恢复。Windows 多版本矩阵和第二台干净电脑不再是交付门槛。新 `--data-dir` 代表空安装，不代表宿主依赖或 bundle 缓存被清空。

## 输入与测试边界

- 原版 Piwork 0.0.9，commit `a6c36da16ebcc0e96f0e34ef820d857f2bea4877`，release `0.0.9-a6c36da16ebc-0e1261f05b9d`。未修改 Piwork 业务源码。
- Linux 最终 ELF：391886624 bytes，SHA256 `c1fb34a767be973c92e1bdaea100c9914078c753ee49bb83b77689a2f33ee47f`。
- Windows 最终 PE：408696024 bytes，SHA256 `4b372f391928f61db808a7ed865c2020821b5867f88da0ea6ab5a1a6bffc6a77`。
- 本轮只调整验收程序与文档/规格，正式产物字节未变；最终 hash 关联于证据。没有发布或推送。
- Linux 是 WSL2 内的实际 `/dev/kvm`；Windows 是原生 Windows 11 Home build 26200/WHPX。Windows 产品的可执行文件、缓存、安装根和运行路径均位于 Windows 本地。Linux 调用 PowerShell 仅用于自动化测试，不是产品运行依赖。
- Linux 专属安装：`dist/runs/final-completion/linux/installation`，UI/Core 为 18080/18081。
- Windows 专属安装：`%LOCALAPPDATA%\PiworkMicroVM-completion-20261021\安装 数据`，UI/Core 为 19180/19181。
- 使用现有实际模型配置 `deepseek-flash` / `anthropic-messages`。凭证仅存在受限测试输入与原版 Guest 配置中；证据不包含密钥、密码或 Token。没有修改或停止用户 UI 8080 的原安装。

## 网络和存储

两平台都只将 Host IPv4 回环上的 UI/Core 两个端口通过 QEMU user-mode NAT 转发到 Guest 17891/17871。Service 仍由原版 Piwork 管理，通过 UI 同源 `/services/...` 访问，验证 HTTP、WebSocket、流式响应及授权行为。没有旧 Service 端口池，也没有新增 Host 管理 TCP 接口。

用户数据都在安装根 `disks/state.qcow2` 内的 ext4：Core 配置和数据库、Docker/containerd 持久根、原版 Work workspace/private named volumes、历史及 Service 数据均在该盘。Host 不直接展开用户文件，上传下载使用 Piwork Files。没有 9P/SMB/FUSE 共享。缓存与数据盘分开，完整备份需先正常停止，再一并备份 `installation.json` 和数据盘。

Windows 本轮真实 argv/模块见 [native-process-proof.json](completion/windows/native-process-proof.json)，Linux KVM、机型、无 PCI、库路径及仅两个回环监听见 [qemu-proof.json](completion/linux/qemu-proof.json)。完整公共参数、Guest 启动参数和先前两平台同时运行的实际 argv 见[双入口验收](two-port-acceptance.md)。Linux 使用 KVM，Windows 使用 WHPX；均为 `-M microvm` 和 virtio-mmio。

## 最终执行结果

两平台均完成新安装、真实模型文件工具调用、正常关机和原盘重启；重启后可在原会话继续真实请求，历史读取 HTTP 200，浏览器显示原工具结果。两平台三类异常退出及原盘恢复均已通过，共六个用例。任务 8.1、8.2、8.4 已据此完成，本变更 43/43 项完成，保持未归档。

| 实测 | Linux/KVM | 原生 Windows/WHPX |
| --- | --- | --- |
| 实际模型 / 协议 | deepseek-flash / anthropic-messages | deepseek-flash / anthropic-messages |
| 首轮工具调用 / 重启继续后累计 | 3 / 4 | 2 / 3 |
| 工具历史 HTTP / 浏览器原结果 | 200 / 通过 | 200 / 通过 |
| 管理员、模型、Work、Files 哈希、Service 持久数据恢复 | 通过 | 通过 |
| Guest 提前退出 + 原盘恢复 | 通过 | 0.354 秒，Launcher 退出 1；通过 |
| 真实关机超时 + 原盘恢复 | 125.37 秒，退出 1；通过 | 125.34 秒，退出 1；通过 |
| Launcher 强杀 + 原盘恢复 | 退出 -9，存活 QEMU 拒绝第二写者；通过 | 退出 137，QEMU 随 Job 退出；通过 |

恢复检查针对故障前已确认提交的文件和数据库，不承诺强杀发生时未提交事务也能保存。两平台每次恢复后原 Core/Work/Memory/Service 数据库均 `integrity_check=ok`，实际 backing 为 ext4，原 named volume 身份不变。

完整产物身份与六项故障验收摘要见 [artifacts.json](completion/artifacts.json)。真实模型及原会话重启继续证据：[Linux](completion/linux/real-model-restart.json)、[Windows](completion/windows/real-model-restart.json)；原版浏览器历史验证：[Linux](completion/linux/real-history-browser-restart.json)、[Windows](completion/windows/real-history-browser-restart.json)。

| 故障原始记录 | Linux | Windows |
| --- | --- | --- |
| Guest 提前退出 | [记录](completion/linux/fault-early-exit.json) | [记录](completion/windows/fault-early-exit.json) |
| 关机超时 | [记录](completion/linux/fault-shutdown-timeout.json) | [记录](completion/windows/fault-shutdown-timeout.json) |
| Launcher 强杀 | [记录](completion/linux/fault-launcher-kill.json) | [记录](completion/windows/fault-launcher-kill.json) |

每个平台还保存三组 `real-model-after-*`、`persistence-after-*`、`service-after-*`、`inspection-after-*`，分别对应历史/文件、账号配置身份、浏览器 Service 数据和实际数据库/卷完整性。最后一次恢复检查见 [Linux 数据库](completion/linux/inspection-after-launcher-kill.json)与 [Windows 数据库](completion/windows/inspection-after-launcher-kill.json)。Windows 强杀后 QEMU 的进程退出码为 0，但 Guest 并未完成有序关机，异常标记仍正确保留；没有把进程退出码当成 clean 证明。

所有专属测试 VM 已正常停止，测试磁盘保留。Linux 12 个、Windows 27 个日志文件对实际测试管理员密码和模型凭证的扫描均无泄漏，交付证据通过白名单收集和相同凭证检查。测试使用的额外临时模型凭证输入已删除；Guest 内原版配置随测试盘保留。`dist/delivery.json` 已更新。本轮没有改变正式 ELF/PE 的字节，也没有修改 Piwork 源码、推送或发布。

## 既有防护证据

- 当前 0.0.9 两入口的无效参数/端口冲突见 [Linux port-preflight](two-port/linux/port-preflight.json)；Windows 同版的无效参数、端口占用、未知目录、缺盘/坏盘拒绝覆盖见 [native-failures](two-port/windows/native-failures.json)，原盘字节保持。
- 当前 Windows 同版更换端口也不能重复写同一安装，见 [two-port-failures](two-port/windows/two-port-failures.json)；本轮 Linux 强杀后的真实第二启动器拒绝结果见 [fault-launcher-kill](completion/linux/fault-launcher-kill.json)。本轮 Windows 每次故障前后也分别记录安装、磁盘和大小写别名锁的状态。
- 同版清缓存并恢复原盘的结果见[双入口验收](two-port-acceptance.md)。此前 0.0.8 的 Linux 缺盘/坏盘、存储未挂载和损坏缓存测试保留在[历史验收](acceptance.md)及其附件，明确保留旧身份；旧 Service 端口池的冲突测试不再适用于当前网络设计，也不把历史故障注入冒充本轮新执行。
- 本轮 `go test ./...`、原生 Windows network/qemu/launcher 测试 EXE、`make source-check`、主规格和变更的严格 OpenSpec 校验通过。单元测试与旧记录用于补充，六次最终产物异常退出和原盘恢复均单独记录实际运行证据。

## 复现入口

测试使用独立带 `.acceptance-owned.json` 标记的安装根，不能向用户日常安装注入故障。所有脚本均为测试工具，不打包进产品。生产启动命令仍是 `./piwork-microvm` 或 `piwork-microvm.exe`。

- Linux 启停/故障：`scripts/acceptance-launch-linux.py`、`scripts/acceptance-exits-linux.py`，通过最终 ELF 启动；`early-exit`、`shutdown-timeout`、`launcher-kill` 分别执行三种故障。
- 业务与恢复：`scripts/acceptance-browser.mjs`、`acceptance-storage.mjs`、`acceptance-baseline.mjs --verify`、`acceptance-real-model.mjs first|restart|check`、`acceptance-real-history-browser.mjs`、`acceptance-recovery-browser.mjs`。
- Linux Guest 实际数据库/卷检查：`scripts/acceptance-inspect.py --recovery-only --runtime <安装根>/runtime.json`。
- Windows 完整串行入口：`scripts/acceptance-completion-run-windows.ps1 -Root <专属根> -Tools <原生 Node/Playwright 目录>`；其调用 `acceptance-completion-windows.ps1` 和 `acceptance-exits-windows.ps1`，使用最终 PE、原生 Edge 与原生测试控制器。
- Windows 数据库检查在最终 PE 停止后，由持有原盘独占锁的补充 Guest 检查程序执行；结果单独注明，并确认 ext4 正常卸载。补充程序不代替最终 PE 启动测试。
- `PIWORK_REAL_MODEL_FILE` 指向权限受限的 JSON 输入（`name`、`model`、`api`、`baseUrl`、`credential`）；不要把内容放进终端命令、日志或证据。`PIWORK_ACCEPTANCE_OUT`、`PIWORK_ACCEPTANCE_PORT`、`PIWORK_ACCEPTANCE_CORE_PORT`、`PIWORK_ACCEPTANCE_PHASE` 选择证据路径和本次专属端口/阶段。

## 历史失败与范围

此前合成 Responses 夹具的 `call-1|fc-1` 历史 503 保留为独立失败，详见[双入口验收](two-port-acceptance.md)。本轮实际使用的是上述模型/协议，不能据此声称所有 Responses 供应商或所有工具 ID 都无问题。

本轮最初并行运行两平台浏览器时出现浏览器关闭、fetch 失败与 WSL interop 等待超时；没有据此判定产品通过，也没有证明唯一原因。随后仅停止专属测试 VM、串行运行两平台，保留失败记录并重新执行。一次 Linux 下载被浏览器标记为 canceled，下载步骤增加最多三次 canceled 重试；最终仍要求下载成功并核对完整字节 SHA256。

Linux 故障 harness 曾错误要求诊断包含 `QEMU`/`lock` 字面量；实际产品分别输出 `Guest exited unexpectedly` 和 `another instance owns this installation or disk`。修正测试断言后重验，未更改产品诊断或绕过独占验证；强杀后的重复写者检查在同一个仍存活 QEMU 上再次完成，记录于该用例证据。
