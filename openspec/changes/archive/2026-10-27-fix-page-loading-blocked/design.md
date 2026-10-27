# Design

## Context

Windows 的 `scripts/qemu-windows.sh` 固定 QEMU 10.0.8，并从其 `subprojects/slirp.wrap` 取得独立的 libslirp Git revision `26be815b86e8d49add8c9a8b320239b9594ff03d`。该源码的 `slirp/src/socket.c` 使用 `listen(s, 1)`；用户报告的原生 Windows 测量中两端口串行均为 30/30、六路并发各为 5/30。

Linux 构建是另一条路径：`guest/qemu/Dockerfile` 安装 Debian bookworm 的 `libslirp-dev`，`dist/qemu/dependencies.json` 显示最终使用 `libslirp0:amd64` 4.7.0-1；已检查打包的 `libslirp.so.0` 机器码，其监听调用传入 backlog 1，Debian 同版本源码的 `src/socket.c` 也有 `listen(s, 1)`。Linux 还没有完成用户所述的原生并发复现，不能把 Windows 的拒绝率直接套用到 Linux。两个 4.7.0 源码树在其他 UDP 处理代码上不同，不能简单用 Windows 源码替换 Linux 的 Debian 安全修订。

Windows `scripts/qemu-windows-bundle.py` 根据 DLL 名称收集依赖，Linux `scripts/qemu-bundle.py` 根据 `ldd` 复制系统库；`scripts/components.py` 对两个 QEMU 使用不同缓存指纹，因此修改源码本身并不能证明最终加载了新库。Piwork 仓库的同名变更负责三个网页入口；合测不能把 MicroVM 当前锁定的官方 Piwork v0.0.15 当成包含尚未发布的页面修复。

## Goals / Non-Goals

**Goals:**

- 修复两平台各自的 Host 转发监听能力，维持原两端口及安全边界。
- 使两份上游源码、补丁、所构建的 libslirp、最终 DLL／SO、缓存和本地验收可相互追溯。
- 在真实 Windows／Linux 与 Guest 上分别验证转发，再以真实输入身份组合验证页面修复。

**Non-Goals:**

- 不改变 Guest 的 Piwork 业务代码、不增加反向代理或放宽网络权限。
- 不修改已经发行制品的身份，不强制创建 tag、远程发布或更新官方 Piwork pin。

## Decisions

### 1. 对两平台的 Host 转发监听应用局部补丁

Windows 针对锁定的 QEMU wrap libslirp Git revision，在 `guest/qemu/` 保存子项目补丁；Linux 保持当前 Debian 4.7.0-1 同一快照和发行补丁，锁定其源码包及校验摘要，在隔离 builder 中构建带本地补丁的共享库。两个补丁只将 `SS_HOSTFWD` 的监听 backlog 提升为 128，其他监听及源码行为保持。Windows 在检出子项目后、Linux 在取得对应 Debian 源码后分别校验并应用；重复运行须可识别精确已应用状态，来源、版本或校验不符及非预期修改时明确失败。

固定 128 而不是复用一条连接或把浏览器请求串行化，使正常并发不被队列 1 人为限制；它不是对无限负载或任何上游服务可用性的承诺。两种 OS 的实际表现仍以原生验收为准。未来升级如已提供等价上游修复，应显式评估并移除补丁，而非盲目强制应用。

### 2. 分平台来源和最终库纳入可核验链

在 `build.lock.json` 中分别记录 Windows wrap revision 与补丁、Linux Debian 源码包与补丁的来源和摘要，与原来应用于 QEMU 根的 `windowsPatches` 区分。Windows 复核 lock、wrap、已检出 revision、补丁字节及实际 Meson 构建解析；Linux 从已固定 Debian 快照取得对应源码并校验，构建专用的已修改库，确保 QEMU 链接和运行时都使用它，而不是系统未修改的 `libslirp.so.0`。不能仅按库名称选取，也不能通过替换上游源码跳过 Debian 补丁。遇到不匹配的既有编译目录应重新配置或明确失败；测试干净构建与二次构建。

更新 `scripts/components.py` 的两平台 QEMU 指纹，让各自实际的源码、补丁、配方和工具链变化导致失效或明确失败。`scripts/qemu-windows-bundle.py` 与 `scripts/qemu-bundle.py` 必须明确取到本次构建的正确库，并为自建 Linux 库记录真实包／源码身份与许可，不再假定每个文件均未修改且能直接归属系统二进制包。记录构建输出、封装输出、最终单文件内资源与原生运行时加载路径／摘要，逐层对照。

保留现有 QEMU／libslirp 许可文本，并在 `scripts/release.py`、`scripts/bundle.py` 的对应源码与来源元数据中分别描述两个平台所用 libslirp 来源和补丁，不能把它们误记为 QEMU 根源码补丁或遗漏。锁校验、补丁打包与源码声明需覆盖新增类型；这只维护本地交付材料，不执行发行。

### 3. 在两个原生 Host 验证真实最终路径

基于现有 Windows 与 Linux 验收入口增加专用并发测试：启动隔离测试安装的最终 PE／ELF 和真实 Guest，确认两个健康入口就绪后，对每个端口先运行 30 个串行请求，再用并发屏障运行五批、每批六个独立新 TCP 连接的 HTTP 健康请求。每次请求显式禁止连接池复用和应用层重试，并有 10 秒截止，分别记录成功、拒绝、其他错误、超时和实际响应。按 Spec 对实际选择的两个可用端口各要求串行及并发 30/30，并验证回环和 Guest 转发边界；默认端口被其他安装占用时使用隔离的自定义端口，不干扰该安装。

Linux TCP 可能在队列拥塞时通过内核重传掩盖问题，因此同时检查本次 QEMU 实际回环监听的有效 backlog 与系统上限，确认不再是 1，并记录连接耗时；不修改全局 sysctl。分别从实际运行 QEMU 进程核对 Windows DLL 与 Linux SO 路径和摘要，与构建及最终产物内嵌依赖匹配；在相同网络下打开原版 `/login`／Desktop 并检查关键资源。按实际执行的 CLI／GUI、平台和输入分别记录，未运行的入口不能宣称已端到端通过。测试只清理本次安装及其资源，日志使用合成账户并放到 `dist/` 或所属变更验收附件。

### 4. 双仓库合测的输入边界

本地合测使用隔离的 MicroVM 构建输入，将已核对的 Piwork 页面修复构造成可追溯的测试 Guest；记录实际源码树、构建身份、QEMU／libslirp 摘要及测试步骤。可使用隔离源码模式或明确标识的本地测试制品，但不能把测试输入写作官方发行、覆盖官方锁或改写历史发布记录。先单独测试转发和 Piwork 的浏览器故障注入，再进行完整组合；缺少真实平台／虚拟化或其他前提时记录未验证项，不以模拟测试冒充端到端结果。

## Risks / Trade-offs

- [补丁已应用但选中了旧或其他来源 DLL／SO] → 强制核验实际依赖来源、缓存身份和运行进程加载文件，再做两平台原生并发测试。
- [替换 Linux 系统库丢失 Debian 修订] → 从原快照的精确 Debian 源码构建，只叠加局部 backlog 补丁并记录源码包身份。
- [增加 backlog 不保证 Guest 永远响应] → 先等待真实就绪，并区分拒绝、其他错误、超时及 HTTP 错误，不把所有失败归因于队列。
- [上游升级改变 libslirp 源码布局] → 锁定上游来源，补丁校验失败即停止并重新评审，不自动模糊套用。
- [本地 Piwork 输入和官方发行混淆] → 以隔离测试身份记录源码及制品，不更改当前官方 pin 或历史证据。

## Migration Plan

按本地构建链更新锁和补丁，重建或失效两平台 QEMU 缓存，运行构建及原生回归，然后与 Piwork 页面修复的隔离构建做组合验收。运行安装的数据盘及端口配置无需迁移；回退时使用先前的配套源码和制品，历史产物身份保持原样。本计划不包含对外发布。
