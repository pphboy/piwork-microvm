# Verification Report: add-cross-platform-desktop-launcher

核验日期：2026-10-22（Asia/Shanghai）。Schema：`spec-driven`；来源：当前仓库的本地 OpenSpec root。

**结论：发现 1 项 CRITICAL、5 项 WARNING；修复阻断项前不应归档。**
任务表的 39/39 与 apply 的 `all_done` 仅表示任务跟踪状态；本次独立核验发现了现有测试未覆盖的反例。
本轮没有修改实现、任务勾选或既有验收结论文件，没有启动 VM、操作桌面、提交、推送或归档。

## Summary

| 维度 | 结果 |
| --- | --- |
| Completeness | 39/39 已勾选；四份 delta spec 的 17 项需求均找到实现位置（15 ADDED、2 MODIFIED）；无 REMOVED/RENAMED 项；没有不可读的跟踪文件 |
| Correctness | 已映射 17/17 项需求，检查 40 个场景的代码及现有测试/验收证据；发现 C1 与 W1–W5 六项偏差，不能视为全部满足规格 |
| Coherence | 基本遵循 D1–D9 的架构与仓库模式；D2 的旧事件处理、D4 的取消/并发、D7 的日志导出存在下述偏差；无额外代码风格建议 |

所有规定的核验维度均执行，没有因缺少规格、设计或实现证据而跳过检查。实机历史证据与本轮新跑的检查分开列出。

## CRITICAL

### C1 — Windows 控制管道连接阶段取消，会直接 Kill 已创建的 QEMU，并可能误报 clean

- **位置**：`internal/launcher/service.go:457`、`:493`、`:505`、`:307`、`:311`；`internal/desktop/controller.go:314`。
- **触发**：Windows 已成功创建 QEMU，QGA/QMP 私有管道尚在连接时，用户停止或确认关闭启动中的 GUI。
- **代码事实**：`connectCtx` 派生自用户可取消的 Context；`Connect` 收到取消会返回错误（`internal/qemu/transport_windows.go:82`、`:102`）。连接错误分支直接 `cmd.Process.Kill()`，没有进入共享的独立 120 秒 `shutdown()`。共享服务在 `StartVM` 返回成功后才设置 `started=true`，该路径因而还缺少“已创建 VM”的准确结果。若返回错误包装 `context.Canceled`，控制器的 `finish` 又会把用户请求后的该错误归为 clean，尽管未确认 Guest 同步/卸载且 `unclean.json` 可能仍在。
- **违反**：`microvm-desktop-launcher`「停止与关闭窗口执行同一安全收尾」；`microvm-launcher-lifecycle`「命令行与桌面共享可取消且可观测的生命周期」及「调用方取消启动或运行」。对应任务 2.4、3.4、8.7。
- **建议**：从实际创建进程的边界起就让生命周期拥有该 VM；连接阶段取消/失败也必须走独立预算的有序收尾，并传回真实 clean/unclean 结果。控制器不要仅凭包装后的 `context.Canceled` 推断已创建 VM 的干净退出。补 Windows 管道连接被延迟时的停止/关闭回归，核对未提前 Kill/Quit、磁盘标记与锁释放。
- **证据等级**：已追踪完整代码路径。本轮未对这一个窄连接窗口另做 Windows 实机重放；已有“启动中关闭”成功记录不证明所有启动子阶段都安全。

## WARNING

### W1 — Guest 错误收尾与 Stop 存在实际数据竞争

- **位置**：`internal/desktop/controller.go:314`、`:502`。
- **问题**：`finish()` 在获得 `c.mu` 前读取 `s.requested`；`Stop()` 在该锁内写入相同字段。Guest 错误返回与用户停止同时发生时没有统一同步保护。
- **复现**：隔离 overlay 测试并发执行非空 Guest 错误的 `finish()` 与 `Stop()`；`go test -race` 明确报告这两处访问的 `DATA RACE`。这不是对真实 VM 的测试，也没有写用户安装。
- **建议**：将该读取及退出结果裁决纳入同一互斥保护（或等价同步方案）；新增 Guest 失败与 Stop/Close 同时发生的回归，重新运行 race。对应任务 3.1、3.4、7.1，设计 D4。

### W2 — 前端会接受旧会话的迟到状态并错误显示运行中

- **位置**：`cmd/piwork-launcher/frontend/app.js:126`、`:207`。
- **问题**：两处过滤都只在 session 相等时比较 seq。切换到新会话后，旧 session 的事件仍被接受；`onStatus` 先覆盖 `ui.status`，后续 `applyStatus` 也无法识别它来自已结束会话。
- **复现**：在隔离 Node VM 中加载实际 `app.js`，依次传入旧会话 idle、新会话 starting、旧会话迟到的 running；实际最终 session 变回旧会话、state 为 running，打开按钮被启用。后端 `OpenPiwork` 仍有当前状态门控，因此不能据此声称后端实际启动了第二个 VM。
- **建议**：建立跨会话可比较的快照/事件 revision，或等价的当前/已结束会话门控；统一处理订阅事件与 RPC 快照，并补“新会话开始后旧事件/旧快照迟到”的前端测试。对应任务 2.2、4.2，生命周期「旧事件与慢速界面」场景及设计 D2。

### W3 — 导出本次日志只导出了有界展示缓冲

- **位置**：`internal/desktop/exports.go:22`；`internal/desktop/logs.go:18`、`:47`。
- **问题**：`ExportCurrent` 读取 `c.logs.text()`，没有读取状态中的当前日志文件。缓冲最多保留 4000 行/256 KiB，长行也会截断；较长会话的前部日志会静默丢失。
- **复现**：当前日志文件 5001 行、145031 字节，导出只有 116000 字节，首行消失，调用仍返回成功。
- **建议**：从当前会话 `LogPath` 读取完整日志并再次脱敏；有界缓冲仅用于显示。超过合理大小上限时明确报错，不能把截断内容当作完整本次日志。补超过展示行数/字节上限的导出测试。

### W4 — Linux 无法把全部日志导出到常见的可写 0755 目录

- **位置**：`internal/desktop/exports.go:65`；`internal/platform/platform_linux.go:29`。
- **问题**：`ExportAll` 对用户选择的保存目录调用安装用的 `PrivateDir`，要求父目录必须 0700。用户自有且可写的 0755 Downloads/Desktop 因而被拒绝；日志保存位置不是受管安装根。
- **复现**：在专属临时目录中创建当前用户拥有的可写 0755 Downloads，选择其中的 ZIP 路径，得到 `directory must be private and owned by the current user`。
- **建议**：只要求导出父目录存在且可写，安全创建 0600 临时文件并原子替换；不要要求用户改变普通下载目录权限，也不要改写该目录的权限。补标准 0755 目录的导出回归。

### W5 — 导出写入/同步错误被变量遮蔽，截断文件也会报告成功

- **位置**：`internal/desktop/exports.go:166`。
- **问题**：`if _, err := f.Write(data)` 声明了内部 err；Write 和 Sync 的错误没有带出作用域。后续检查的是 `CreateTemp` 时已为 nil 的外层 err，仍可能 Close、Rename 并返回成功。
- **复现**：仅在独立测试子进程中设置 `RLIMIT_FSIZE=1024`，请求写入 16384 字节；实际文件只有 1024 字节，函数却返回 nil。该资源限制没有应用于 Launcher、当前终端或宿主其他进程。
- **建议**：显式保留和传播 Write/Sync 的错误，确认完整写入并同步成功后才替换目标；失败保留旧目标并删除临时文件。补实际写入阶段失败的回归，不能只测目录无写权限。

W3–W5 均对应「日志查看和原生导出只呈现真实诊断」及「导出本次或全部日志」场景、任务 5.3、5.4、设计 D7。

## SUGGESTION

无。上述发现均为具体行为或测试缺口，没有增加风格整理任务。

## 需求实现与场景映射

下面的“已有证据”指已阅读的测试或真实验收记录；发现项不是因为只搜索到文件名就判定通过。

| 规格需求 | 主要实现位置 | 已有证据 / 本轮结论 |
| --- | --- | --- |
| 双击进入唯一桌面主路径 | `main_desktop.go:233`；`controller.go:262` | 两平台默认根真实窗口/CoreLoop、原版引导记录 |
| 保持原型与 Piwork Desktop 的视觉和交互 | `main_desktop.go:33`；`frontend/index.html`、`app.css` | 本地 UI 来源/hash 与 800×600 五态截图；无生产模拟开关或远程静态资源依赖 |
| 目录选择直接复用完整安装根 | `controller.go:541`；`preferences.go:25`；平台 ValidateSelectedRoot | 取消、中文/空格、重开、已有安装/未知目录、失败换根测试与实机记录 |
| 真实状态驱动启动反馈与可用入口 | `service.go:348`；`controller.go:412`；`app.js:207` | 健康未成功/首次引导门控有覆盖；前端迟到状态存在 W2 |
| 运行状态提供可操作的浏览器和数据位置 | `controller.go:600`、`:612`、`:624` | 真实浏览器与剪贴板、Guest 退出测试/记录 |
| 启动错误可理解且可重试 | `service.go:160`；`controller.go:313` | 加速/端口/坏盘/资源/启动期限测试及真实错误截图 |
| 停止与关闭窗口执行同一安全收尾 | `controller.go:490`、`:657`；`service.go:411` | 正常/取消确认/超时/故障恢复有覆盖；Windows 连接阶段缺口 C1，错误与 Stop 并发 W1 |
| 自绘 Header 使用真实窗口与外链操作 | `main_desktop.go:200`、`:233`；`app.js:374`；`app.css:35` | 原生拖动/最小化、菜单外链、Help/About 与截图记录 |
| 日志查看和原生导出只呈现真实诊断 | `logs.go`；`exports.go`；`events.go:137` | 首次/历史/脱敏/取消/归档均有既有测试；新反例 W3–W5 |
| 并发操作不增加 VM 或破坏数据保护 | `controller.go:262`；`service.go:253`、`:263` | 重复 Start、单会话与跨进程/磁盘锁测试，真实强杀后写者/Job 记录；不把这些结果当作 W1 已覆盖 |
| 命令行与桌面共享可取消且可观测的生命周期 | `run.go:112`；`service.go:152`；`events.go` | 共用路径、慢消费者、阶段、CLI 信号与返回码已有覆盖；C1/W1/W2 |
| 根据实际状态交付可用入口 | `service.go:348`、`:366` | WebUI 与业务 ready 分离、未配置首次引导、Guest 错误/超时已有覆盖 |
| 桌面目录偏好与业务安装根独立持久化 | `preferences.go`；`controller.go:138`、`:368`；`install.go` | 原子保存、有效身份、健康后标记、损坏/写失败/不匹配、原盘恢复测试/记录 |
| 分平台交付自包含可执行文件 | `bundle.py:174`、`:265`；GUI 构建脚本 | 两个实际交付文件、真实窗口/自有资源记录、本轮 manifest/payload/SHA 复核 |
| GUI 构建隔离并保留文件尾资源格式 | `Makefile:30`；`gui-build.py:61`；`bundle.py:56`、`:114` | CLI CGO=0 / GUI CGO=1 与命名隔离；两平台 Trailer/manifest/payload 校验通过 |
| 桌面依赖和来源可复核 | `go.mod`；`ui-sources.json`；中英文 README | Wails v2.17.0、UI 复制内容 hash 本轮匹配；系统库/开发包区分与原生版本记录 |
| GUI 验收与 CLI 和历史证据分别记录 | `acceptance.md`；`evidence/gui-runs.json`；两平台 completion 报告 | 历史/最终产物、真实平台、旧 CLI、业务/数据库检查分别记录，没有以单元探针冒充实机通过 |

实现路径在本表中使用相应 `internal/desktop`、`internal/launcher`、`cmd/piwork-launcher` 或 `scripts` 下的文件；具体问题以上方完整路径为准。所有 40 个场景都属于上述 17 项需求，没有 removal/rename-only 或故意跳过的规格项。

## 本轮执行的验证

通过：

- `go test ./...`。
- 既有 `go test -race ./internal/launcher ./internal/desktop`。
- `python3 -m unittest discover -s scripts -p '*_test.py'`：6 项通过。
- `go test -tags 'desktop production webkit2_41' ./cmd/piwork-launcher`：Linux 桌面入口编译检查通过，该包没有 Linux 单元测试。
- `openspec validate add-cross-platform-desktop-launcher --strict`。
- `git diff --check`。
- 两个最终 GUI 文件的自身 Trailer/manifest、payload SHA256、旁置 `.sha256`；复制 UI 文件与来源记录中的 hash 匹配。

新增隔离探针的失败是本报告的发现，不应混写成既有测试已覆盖或全部通过：

```sh
go test -overlay dist/verify-desktop/overlay.json ./internal/desktop \
  -run '^TestVerify(ExportAll|CurrentExport|AtomicWrite)' -v
go test -race -overlay dist/verify-desktop/overlay.json ./internal/desktop \
  -run '^TestVerifyFinishStopRace$' -count=1
node dist/verify-desktop/frontend-probe.mjs
```

探针使用 Go overlay 和独立 Node VM；没有向产品源码注入测试接口。可复核的源文本快照与失败输出保存在
`evidence/verify-2026-10-22/`。其中 `.go.txt` 是证据文本，不会被 `go test ./...` 当作新包运行。

## 实机证据与适用范围

本轮阅读了两平台 completion 报告、业务/数据库/故障/最终默认根记录及对应截图文件清单；实机执行属于此前 apply 验收，本轮没有重新启动 VM 或自动操作用户桌面。

- Linux：真实 WSLg/WebKitGTK + KVM；最终 ELF 的原盘恢复、health 200、Service 计数 2→3、安全关闭有独立记录。
- Windows：原生 Windows 11 Home build 26200、WebView2 + WHPX；运行不依赖 WSL，最终 EXE 的默认根与中文/空格路径均有记录。
- Work/Files/Service HTTP、WebSocket、SSE、SQLite integrity 与持久化有既有真实证据。Linux 外网探测的一次 503 和单独成功重试也分别保留，没有抹去失败。
- 真实模型推理/AI 会话恢复、其他 Windows build/Linux 桌面不是本变更新列的强制验收范围；仍沿用验收报告的“未验证”说明，不将其追加为新的归档前置条件。

## Final Assessment

**1 critical issue found. Fix before archiving. 5 warnings to address; 0 suggestions.**
主要 CoreLoop、单文件结构和既有实机结果有证据支持，但“39/39 已勾选、所有边界均满足”的更强结论不成立。
优先修复 C1，并处理 W1–W5、补回归后重新核验。本轮不修改任务状态、不实施修复、不归档。
