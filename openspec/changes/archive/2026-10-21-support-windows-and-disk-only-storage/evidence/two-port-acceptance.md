# Piwork 0.0.9 双入口更新验收

> 后续范围收敛、真实模型及最终产物异常恢复结果见[收尾验收](completion-acceptance.md)。本文件保留当时结果；其中版本矩阵和第二台干净电脑要求已由用户取消，真实模型是否通过以新记录为准。

2026-10-21（Asia/Shanghai）。本记录仅对应本次重建的两个产物；此前 `acceptance.md` 和原有附件保留 0.0.8 身份，不作为本次通过证据。未修改 Piwork 业务源码，没有推送或发布。

## 输入和产物

- 官方默认分支 `main` 在 `2026-10-20T21:26:10.543788+00:00` 解析为 `a6c36da16ebcc0e96f0e34ef820d857f2bea4877`，版本 0.0.9。独立 checkout 干净，补丁列表为空。
- Server、嵌入 WebUI、生产 Agent 和 Helper 从同一源码/发行身份构建；package-helper 复用原版 Agent 引用。没有使用验收 Agent 替代生产镜像。
- Linux `dist/piwork-microvm`：自包含 x86-64 ELF，391886624 bytes，SHA256 `c1fb34a767be973c92e1bdaea100c9914078c753ee49bb83b77689a2f33ee47f`。
- Windows `dist/piwork-microvm.exe`：自包含 x86-64 PE，408696024 bytes，SHA256 `4b372f391928f61db808a7ed865c2020821b5867f88da0ea6ab5a1a6bffc6a77`。
- 完整源码、UI/镜像、资源清单与产物身份见 [artifacts.json](two-port/artifacts.json)。公共 kernel/Guest 与对应平台 QEMU、运行库、固件和许可证均在文件内；未依赖 Host 预装 QEMU。

重建：`make source-check && make piwork-microvm-all`。更新上游时先执行 `make source-refresh`；普通构建使用锁定的完整 commit。此次复用未变的已构建固定 kernel/QEMU，重新构建 Piwork、生产镜像、Guest helper、RootFS 及两个最终文件。

## 实际网络实现

| 用途 | Host 默认 | Guest 监听 | 选择参数 |
| --- | --- | --- | --- |
| 浏览器 UI/ControlPlane | `127.0.0.1:17891` | `0.0.0.0:17891` | `--port` |
| CLI/backend Core API | `127.0.0.1:17871` | `0.0.0.0:17871` | `--core-port` |

只有两个 QEMU TCP hostfwd。Guest 的监听允许 NAT 到达；Host 仅监听 IPv4 回环。两项 Host 端口接受 1–65535 且不能相同，无效参数在访问虚拟化/安装数据前失败。UI 的公共 origin 跟随 Host UI 端口；完整就绪检查同时通过 Host Core 入口进行。

原版 Service 通过 UI 同源 `/services/<workId>/<serviceId>/<port>/` 访问。旧 `--service-ports`、整段 17891–17954 的检查和转发已删除。Service 仍由 Guest 内的 Piwork/Docker 管理，启动器仅启动 VM、配置两个网络入口和管理 VM 生命周期。未开放 Docker API、Agent RPC、QMP 或 QGA 的 TCP 端口。

Guest 实际 Piwork 参数为：

```text
serve --listen 0.0.0.0:17891 --core-listen 0.0.0.0:17871
      --public-origin <本次 Host UI origin>
      --data-dir /var/lib/piwork/core --no-open
```

Linux 同时运行阶段的实际转发：

```text
-netdev user,id=net0,hostfwd=tcp:127.0.0.1:8080-:17891,hostfwd=tcp:127.0.0.1:8081-:17871
```

Windows 同时运行阶段为 `19080→17891`、`19081→17871`。后续改为 `19082/19083` 并从空缓存恢复同一安装。完整实际 QEMU 命令、四入口健康检查及同时运行事实见 [concurrent.json](two-port/linux/concurrent.json)；Windows 最后一轮原生进程、模块及两个实际监听见 [windows-process-proof.json](two-port/windows/windows-process-proof.json)。两平台均为 `microvm`、硬件加速和 MMIO，无 PCI/TCG 回退。

## 实际测试

Linux 使用本机 WSL2 Linux 中可用的真实 `/dev/kvm`；Windows 是原生 Windows 11 家庭版中文 build 26200 / WHPX。Windows 文件、进程、磁盘和模块均在 Windows 本地路径；WSL 仅作为构建和发起原生测试命令的工具，产品运行不调用 WSL。不是第二台干净物理 Host 的证明。

| 检查 | Linux/KVM | 原生 Windows/WHPX |
| --- | --- | --- |
| 最终单文件、空安装、Guest Docker/内置镜像、原版管理员/QuickStart | 通过 | 通过 |
| 独立 UI 与 Core，实际仅两个回环监听 | 通过 | 通过 |
| UI 对直接 `/api/v1/` 请求返回 404，Core 保留后端 API | 通过 | 通过 |
| 两个独立 VM 同时存活，四个入口均返回健康 200 | 通过，8080/8081 | 通过，19080/19081 |
| 真实生产 Work、Files 中文文本/二进制上传下载、编辑和删除 | 通过 | 通过 |
| 原版 UI 同源 Service HTTP、SQLite 计数、WebSocket、SSE | 通过 | 通过 |
| 匿名 Service 拒绝、只读 workspace 和无卷权限 | 通过 | 通过 |
| 停止 Service 后原浏览器授权不能继续使用 | 通过 | 通过，200→503，原入口不可继续访问 |
| Guest/Work DNS、外部 HTTPS、AI API 未授权 401 可达 | 通过 | 通过 |
| 正常停止后，管理员、模型、Work/Service、文件哈希和文本 Session/Run 恢复 | 通过 | 通过 |
| Core、Work、Memory、Service 数据库在 ext4 且 integrity 为 ok | 通过 | 通过 |
| 空资源缓存再次启动，原盘数据保留 | 通过 | 通过 |
| 更换 UI/Core Host 端口后重新登录及 Service WebSocket | 通过 | 通过 |
| 默认 17891/17871 再启动；旧 17954 被测试程序占用不影响 VM | 通过 | 旧池无转发；同时运行阶段已验证 |
| 缺值/非法/相同端口、UI/Core 占用的安全失败 | 通过 | 通过 |
| 原版工具调用 Session 历史读取 | **失败，HTTP 503** | **失败，HTTP 503** |

数据持续使用安装根内 `disks/state.qcow2` 的 Guest ext4，Docker/containerd 与原有 Work 卷不放到 RootFS 临时层。没有 Host 目录共享。所有正常关机均确认同步/卸载和 QEMU 退出，测试磁盘保留，测试 VM 最终正常停止。

Linux 另在默认 `17891/17871` 和 HTTP 80 上验证了同一安装恢复。普通 Host 用户绑定 80 首次得到明确 permission denied；随后在独立 KVM 测试网络命名空间内使用相同盘/最终 ELF 成功验证浏览器规范 origin、Service 和 WebSocket，没有修改 Host sysctl 或停止占用进程。空缓存的该轮运行同时验证了最小依赖运行根。

Windows 追加 15 项真实失败/帮助测试，坏盘/缺盘测试前后核对原盘 SHA256 一致；不同双端口再次启动同一安装也被锁拒绝，原 QEMU 保持不变。Windows 控制和测试执行使用原生工具，测试工具不进入产品。

运行证据：各平台 [Linux](two-port/linux/) / [Windows](two-port/windows/) 目录中的 `browser-result.json`、`persistence-result.json`、`recovery-browser-result.json`、`guest-runtime-inspection.json`、`guest-network.json`、`memory-result.json`、端口/失败与重启记录。文件通过 allowlist 和实际测试秘密字符串检查后收集，不复制账号密码文件。

## 检查与限制

- `go test ./...` 通过；当前 network、qemu、launcher 测试 EXE 在原生 Windows 执行通过，包含 named pipe、ACL、参数、两项端口冲突和安装保护。
- Python 编译、改动 Shell/JS 语法及 OpenSpec 严格校验通过。最终 ELF/PE 的 sha256 与侧文件、bundle manifest 和本记录核对。
- 没有真实 AI Key，未宣称真实供应商调用成功。生产 SDK/Memory 合成夹具明确标为 synthetic。原版 0.0.9 的工具调用历史仍返回 503；普通文本历史为 200，原始 Run/Memory 在重启后保留。未给 Piwork 打修复补丁。
- 没有 Windows 21H2–24H2、关闭 WHPX 的测试环境或第二台干净 Host；这些原有验收缺口仍未通过。本轮没有重跑全部强杀/关机超时场景，也没有验证 0.0.8 数据盘的跨版本升级。
- 本次第 9 组 4/4 完成，原变更合计 39/43。5.1、8.1、8.2、8.4 继续保持未勾选，不将本次端口更新写成原变更全部验收通过。

可重复的端口测试入口：`make acceptance-ports`。完整 Linux 流程为 `make acceptance-microvm`；原生 Windows 流程使用 README 记载的 `acceptance-windows.ps1 -Port <UI> -CorePort <Core>`。测试需要外围工具，产品本身仍只运行单个 ELF/PE。
