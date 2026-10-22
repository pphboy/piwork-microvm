# Design

## Context

动机与范围见 `proposal.md`，输入、构建和发布契约见三个能力的 delta spec。此次涉及输入身份迁移、下载/归档校验、多个构建入口及发布恢复，满足编写设计的条件。

现有 `scripts/piwork.py` 总是调用 npm、上游 Go 编译和三个生产镜像构建；`scripts/rootfs.py` 只消费 `dist/piwork/bin`、元数据和镜像归档，可保留这个交界面。`scripts/bundle.py` 与发布检查都依赖干净源码副本；保留来源副本可继续提供 LICENSE 和审计依据，不必因此编译源码。Kernel/QEMU 目标为 PHONY，已有编译缓存仍会重新进入配方；RootFS 每次组装产生新 UUID。GUI/CLI 各有独立资源清单和尾部 Trailer。

当前 `scripts/release.py` 只枚举两个 CLI、只执行 Go 测试，且默认读取历史真实模型证据，未匹配当前完整输入。GUI Windows 主体需要原生 Windows 编译，不能以 WSL 交叉编译替代。

已经只读核验官方 0.0.11 归档 SHA256 和目录：两个可执行文件在 `piwork-linux-amd64-a19c6f595fa6/bin/`，另有 LICENSE、包内 SHA256SUMS、程序/镜像记录、release-inputs、release-manifest、server-build、构建信息和手册。官方版本检查使用 `--version` 输出 JSON；Core 内嵌依赖引用可按上游原生打包规则重建并核对。

## Goals / Non-Goals

**Goals:**

- 后续正式制包优先消费明确锁定的官方 Core/CLI 和匹配镜像，保留现有 Guest 消费路径及离线启动能力。
- 把下载、校验、底座复用、Guest 组装、四种封装和发布串成可重复的流程，阶段结果与耗时可查。
- 正确保留实际构建身份、发布身份、许可、已测范围和旧盘备份边界。

**Non-Goals:**

- 不改 Core 运行方式、业务源码、GUI/字体、用户数据格式或默认网络入口。
- 不实现运行中覆盖只读 RootFS、在线更新器、差分下载、Core 容器化、CI 迁移或分块 bundle 压缩。
- 不把本轮升级扩大为真实模型、全故障、多版本 Windows 或完整历史矩阵验收；不改已发布 v0.2.0。

## Decisions

### D1. 锁定输入模式，区分程序构建提交与发行提交

在现有锁中增加 `piwork.inputMode`；缺少字段的旧锁按 `source` 处理，当前新锁明确使用 `official-release`。保留 `piwork.url` 和 `piwork.commit` 的含义：commit 永远是实际构建提交，所以本次是 `a19c6f595fa6b2515d19146f3510dfc9f1ba4b8c`。在 `piwork.release` 下另记标签、发布提交 `2142491f5103b58731de4872d153bd1b876860de`、预发布状态、发行元数据、资产与镜像锁。字段为增量扩展，不改变现有系统/工具链锁的含义；未知模式明确失败。

新增 `scripts/piwork_release.py`，提供显式 `lock --tag v0.0.11`、`prepare` 与只读 `check`。只有 lock 子命令更新发行输入；正常构建使用已锁内容，不查询 latest 或自动升级。旧的 `source-refresh` 仅作用于源码模式，官方模式下应拒绝并指向显式发行锁更新，避免只改 commit 而留下旧资产记录。

本次官方资产地址均在 `https://github.com/pphboy/piwork/releases/download/v0.0.11/` 下：

| 资产 | SHA256 |
| --- | --- |
| `piwork-linux-amd64-0.0.11.tar.gz`（26362017 bytes） | `a909248c9bd9a6571eb26a0dc52773af0a28a932ce24ea3c6706025700be30a9` |
| `release-build.json` | `edbe300808844233c64dffcf0e738338d1039b8b1de4ac3fcff9a58fc1ad97ad` |
| `release-manifest.json` | `f2f821b7b6fca6d407dd014280045854174655cccc70d97a4ff1cf6796bc1c36` |
| `SHA256SUMS` | `4b349242606a11b79445143f19aa35af027de442c6dfa311bd27ebfbe26699b6` |

同时锁定元数据中的版本 0.0.11、sourceInputHash `d60025d65577833bc6a625cbb4964c7f9d782be5d74f42ece1b65bcd74395632`、两个 UI hash、linux/amd64、Go 身份、原版状态、镜像 ID 和协议标签。锁定值来自明确官方发行及其交叉校验，不能仅从文件名推断，也不宣称有上游未提供的数字签名。

`source.py` 仍取得并验证实际构建提交的独立干净副本，供许可、来源和源码模式使用；官方 prepare 不执行其 npm、Go 或 Dockerfile 编译。把官方发布 commit 当作编译 commit，或直接让现有 source-refresh 跟随 main，都不能准确描述这些官方字节，因此不采用。

### D2. 官方输入原子导入到现有制包目录

`piwork.py` 按锁选择现有源码分支或官方 prepare。官方 prepare 在 `dist/downloads/` 按 SHA256 缓存下载，先验证预期大小、外部资产摘要和元数据，再在受管暂存目录检查整个 tar 的成员结构、重复项、文件类型、目标路径及展开边界。只接受预期单层根目录下的普通文件/目录，拒绝越界、链接、设备等；不使用不受限制的 extractall。

校验包内 SHA256SUMS、programs/server-build/release-inputs/release-manifest 的交叉身份；先静态核对 ELF amd64 和无额外动态依赖，再在隔离临时数据/配置目录执行 Core/CLI `--version`。比较 JSON 的 program、version、commit、modified、os/architecture、goVersion 和 UI hash。Core `--help` 保留三个既有启动参数；不需要执行任何上游构建脚本。

按上游原生打包规则，从锁定引用生成依赖 JSON/base64，核对 Core 二进制确实包含该串；不能只信相邻 JSON，或修改官方 Core 的内嵌引用以适配本地旧镜像。

所有检查成功后，原子发布以下兼容输出：

- `dist/piwork/bin/piwork-core` 与 `piwork-cli`，字节保持官方原样。
- `dist/piwork/metadata.json`，采用官方 release-inputs 中现有字段，并记录导入来源。
- `dist/piwork/images.json` 与 `dist/guest/images.tar`，格式继续满足 Guest 的 `reference` / `id` 消费接口。
- `dist/piwork/upstream-release/` 下的官方元数据、归档内许可和完整性记录；导入完成记录绑定所有实际输出摘要。

中断或检查失败只丢弃本次暂存，不覆盖已验证输入；没有有效缓存时明确失败，不转用旧文件或源码编译。官方入口只获得制包文件，不触碰用户正在运行的 VM 或安装盘。

### D3. 同步引入官方生产依赖，保持 Guest 原生 Core

使用以下镜像的完整 digest，另外从锁核对官方 image ID、版本/commit/原版状态、平台与协议标签：

| 角色 | 仓库 | Registry digest |
| --- | --- | --- |
| Agent / package-helper | `docker.io/pphboy/piwork-agentd` | `sha256:0a6a181f7e6e63e626350828e6b624180f241ac712f2c0e91850dbe82d0ca66e` |
| file-helper | `docker.io/pphboy/piwork-file-helper` | `sha256:ff0ed5d519d1db0ba4c53474622a1a3e4d1391e31849fafd5e1601c464b48d73` |
| snapshot-helper | `docker.io/pphboy/piwork-snapshot-helper` | `sha256:d1c8ef00e48529a047e8db1611e1b37d42ceab496fbbb4be883bbcfa6f44fbb6` |

官方 tag 后缀为 `0.0.11-a19c6f595fa6-d60025d65577`。下载按 digest，保存到 Guest 归档时保留 Core 内嵌的官方 tag 引用，并再次核对其指向的 image ID；本地同名引用若冲突应拒绝，不重新标记旧镜像冒充新版本。沿用上游隔离版本探测方式核对 service-mcp、package-helper、file-helper 和 snapshot-helper 的实际 `--version`；不启动业务容器完成这些检查。

只内嵌原流程需要的三个镜像，package-helper 与 Agent 共用一份。官方 Core 容器不是本次输入，Guest 仍通过现有服务运行原生 Core。最终 Guest 从内置 archive 加载这些镜像，用户首次运行无需 Host Docker 或在线拉取；构建可下载官方镜像，始终不向 registry 推送。

只换 Core 后继续携带 0.0.10 镜像会与官方内嵌引用和来源身份失配，因此不采用。

### D4. 以实际组件输入和输出校验复用底座

加入一个小型组件记录检查器，由 Make 的共享底座入口调用现有 Kernel/QEMU 配方。记录保存到已忽略的 `dist/`，包括组件输入指纹、输出文件清单/大小/摘要和工具链身份。Kernel 指纹只取其 Linux 锁、config.fragment、配方、构建镜像/快照与有效参数；平台 QEMU 指纹包含 QEMU 锁、平台配方、补丁、工具链及打包规则。不能把整个 build.lock 的 hash 当作每个底座的唯一 key，否则只换 Piwork 仍会使底座失效。

命中必须同时满足输入相同、声明输出齐全且摘要相符；否则运行原配方或明确失败，成功后才原子写记录。保留完整重建选项用于恢复与验证。既有无记录文件不能仅凭存在被认定有效；首次可从已核验 v0.2.0 产物清单、对应源码配方和相同组件锁恢复完整证明并建立记录，证明不足就重建，不手工绕过检查。

系统底座继续利用锁定 Dockerfile 的有效层缓存，记录其锁定基础镜像及生成身份。Guest 组装仍沿 `rootfs.py` 的输入界面，应用文件/镜像变化时生成新 RootFS；同一发行只准备一次 Guest 并供四种入口使用。共用 Guest 完成记录覆盖导入文件、镜像、Guest agent、组装/初始化配方、系统基础输入及生成输出摘要；跨命令复用也需完整命中，不能只看 RootFS 是否存在。

本轮保留四份独立 tar.gz 与现有 Trailer，不实现压缩块缓存或改变 CLI/GUI 的许可资源差异。阶段日志记录导入、镜像准备、底座命中、Guest 组装、封装与上传时间；完整重建的 RootFS 仍使用新 UUID，缓存命中只是复用已生成文件，不构成字节可复现承诺。

### D5. 让四种产物携带一致来源与可读许可

`bundle.py` 和发布检查按 inputMode 调用对应的只读验证，不再把“干净源码存在”当作官方输入已验证的充分条件。原来源副本、build.lock、官方输入完成记录/元数据与实际镜像身份一起进入可读 provenance；许可采集继续覆盖 Guest 包、BusyBox、内核、QEMU、平台运行库、Go 和 GUI 依赖。

官方原生包已观察到根 LICENSE 和 Go 构建信息，不能据此假设含完整依赖许可树。保留这些原始文本，并按导入程序的实际模块版本/校验信息取得并索引相应许可；配套镜像中的分发组件沿同样的可读文本和缺失索引规则处理，不在引入新输入时丢弃原先的许可范围。成品发布另附可读许可归档，任何真实缺失在索引及说明中列明。

四个包装层主体仍以本次版本 0.2.1 重新链接，上游 commit 使用实际构建提交。GUI Windows 延续原生 Windows Go/Wails/MinGW 构建；不新增 WSL 或跨平台桌面运行要求。现有构建脚本为主体生成绑定 source/input 指纹、入口、平台、版本及主体 SHA256 的构建记录；封装核对记录与实际前缀，发布核对最终 Trailer 和资源输入。CLI 再做 `--version` 检查，实际 GUI About 在专项验证中核对。

发布表从同一四入口定义取 artifact/manifest 名称，避免 GUI 借用 CLI manifest。已准备四个文件时 `REUSE_ARTIFACTS=1` 只跳过重建，不跳过来源、版本、测试和完整性门槛；需要 native Windows 主体时给出既有构建步骤，不能默默用旧文件或进行不支持的 Wails 交叉编译。

### D6. 冻结本次发行计划，草稿完成后再公开

`make release VERSION=0.2.1` 只执行本地门槛、准备文件与说明；测试入口覆盖仓库现有 Go/Python 与新增输入/缓存/发布测试。`make release-publish VERSION=0.2.1` 是独立远端步骤，沿用户已提出的发布目标执行。四个资产名继续沿用 CLI 规则，并为 GUI 使用 `piwork-microvm-gui-v0.2.1-<platform>-amd64[.exe]`。

在版本专属 dist 暂存目录冻结发行计划：目标源码提交、完整输入、四个文件及附件大小/摘要、创建时间、发布清单和最终 notes。发布重试读取冻结计划，不重新生成时间戳或改写清单。Gate 通过后创建/验证 annotated tag、确保对应源码已推送，建立草稿并上传；远端资产大小和 SHA256 与冻结计划全部相同后才公开，并最终核验公开状态及链接。

同版本重试允许 tag 已存在，但必须为同一 annotated tag 目标和同一发行计划；匹配且完整上传的文件可跳过。已完成但不匹配的文件/标签、不同源码或已公开版本内容变化均报错，不强推、覆盖或自动删除。对于上传失败留下的占位，只在草稿与冻结计划归属均可核实、远端明确尚未完成且没有有效摘要时，记录占位 ID 后受控清理并重传；其他冲突停止处理。上传失败保留草稿并按文件重试，不实现文件内部续传。把四个文件改成在线小更新包才能显著降低总传输量，这不是本次范围。

清单沿输入/产物/验收三个区段，输入指纹来自规范化完整锁定信息，不包含本次重建文件摘要；每个产物单独记录实际摘要。验收读取增加严格输入匹配：没有完整指纹的历史记录不能自动赋予当前输入 verified。分别列出构建检查、GUI/Guest 整合、真实模型与上游验证来源，缺失项写 not-verified，不沿用当前脚本的历史真实模型默认结论。

### D7. 在旧盘副本上验证升级，记录实际提速

本轮两平台以独立新安装核对启动、Core/CLI 0.0.11 实际构建身份、内嵌镜像、浏览器工作台和一次正常停止/重开；做小范围生产 Work 启动、Files/Service 和实际管理员日志 ZIP 打开检查。Linux 额外证明一组自定义 UI/Core 端口，7172 在访问安装前仍被拒绝。沿用已有专用 GUI/浏览器/日志导出工具，不引入新服务或真实模型 Key。

旧盘验证只对已正常停止的专用 0.0.10 测试安装同时备份 `installation.json` 和 state.qcow2，启动单独副本，核对账号/Work/Files/Service 等既有数据及正常停止/重开，原副本前后摘要不变。上游记录未承诺通用兼容或直接降级，因此只报告这次实际副本结果；回退使用未触碰的停机备份与旧发行文件，不能用旧 Core 打开已升级副本来冒充可靠回退。

结果保存在本变更的聚焦验收记录和允许列表证据中，独立于代码提交，不改历史证据。原始 ZIP、磁盘、二进制、运行状态及凭证不进 Git。没有实际运行的平台/步骤如实未验证，快门槛不因此伪造通过。

首次完整准备与随后同输入准备分别记录阶段耗时和命中；用小型受控输入验证“仅换应用不使底座失效”，不为测时间反复完整编译。先前 AI 工作量估计 2–4 小时、后续更新 20–45 分钟均是估算/目标，不是验收硬门槛；本轮实测会把编译节省与网络传输成本分开说明。

## Risks / Trade-offs

- [官方包/元数据身份不同或标签后来变化] → 冻结资产 SHA256、实际构建/发布提交与程序身份，不能解析 latest 替代锁定输入。
- [旧镜像标签或缓存污染] → 按 digest 取像，核对 image ID、程序/协议身份及全部缓存输出；不自动覆盖冲突引用。
- [导入包使来源或许可退化] → 记录原包与实际模块/镜像输入，保留可读许可树和缺失索引；不能仅复制一个 LICENSE 就宣称完整。
- [旧盘或升级回退失去数据] → 仅测停机备份副本，保留原盘，报告实际兼容范围，不承诺通用降级。
- [双平台主体旧版本或人工补传遗漏] → 四入口清单、绑定主体摘要的构建记录、版本/About 与 Trailer 检查，草稿完整后公开。
- [缓存提速仍被压缩/1.6GB 上传主导] → 记录分阶段耗时和逐文件重试；保持完整单文件交付，不宣称已实现差分更新。
- [README 并行变更仍写旧发行信息] → 本次仅同步必要版本/构建事实；README 精简及新演示素材继续在其独立变更中按实施时的实际发行输入处理。

## Migration Plan

1. 先以独立提交完成规划、输入模式/校验、配套镜像、缓存与发布行为的实现和对应测试，保持已有源码模式可显式运行。
2. 锁定 0.0.11 官方输入，首次证明/建立底座缓存，准备新 Guest；在原生环境构建四个 0.2.1 主体与资源。
3. 完成专项验证，分别提交代码、双语事实说明与本变更验收证据；不混入另一 README 变更或任何运行制品。
4. 工作树及输入/产物门槛通过后，以本地 release 计划准备所有资产，执行独立发布并核验 v0.2.1 的 tag、公开资产与摘要。

源码模式、完整重建和旧发行文件保留为明确选项；任何官方输入失败只停止当前构建，不修改运行安装。发布前可回退实现提交并继续用旧版；公开后用新的包装层版本修正，不改写旧标签或 Release。
