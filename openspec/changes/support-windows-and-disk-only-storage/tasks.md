# Tasks

## 1. 最新原版 Piwork 构建输入

- [x] 1.1 在实施开始向官方远程重新解析默认分支最新 HEAD，更新 `build.lock.json` 和源码来源记录；验证完整 commit 与远程结果一致，记录时间，后续按该锁重建而不追踪浮动分支。
- [x] 1.2 修改 `scripts/source.py` 使用独立干净源码副本，删除 Piwork 补丁及自动应用逻辑；验证正常输入无补丁/dirty 标记、脏副本被拒绝或隔离，相邻 Piwork 工作区不变。
- [x] 1.3 按最新上游原有入口构建 Server、WebUI、生产 Agent/file/snapshot-helper 及 package-helper 引用；通过源码/UI hash、镜像标签/ID 和 Server 嵌入清单核对同一身份，确认不触发 push/release。
- [x] 1.4 更新双语 README 的源码刷新、锁定重建和构建依赖说明；按文档执行来源检查与锁定重建准备，确认用户运行阶段不拉源码、不依赖构建工具。

## 2. 原生 Windows microvm/WHPX 验证关口

- [x] 2.1 增加固定来源/校验的 headless Windows QEMU 构建及依赖准备入口，启用 WHPX、microvm、MMIO 和 SLIRP；验证产物为 x86-64 PE、列出所需能力，记录版本和 DLL/固件来源。
- [x] 2.2 用受管的无 9P 临时 Guest 探测资源，在 Windows 本地路径上真实启动 `microvm + WHPX`；验证 kernel、两块块设备、ext4 读写、DHCP/DNS、时钟和串口，收敛 CPU/IRQ 参数且无 TCG/PCI/其他机型回退。
- [x] 2.3 验证 QMP/QGA 的 Windows named pipe 创建、初始连接、持久会话及当前用户 ACL；实际执行 Guest 查询和一次操作，断线/超时有明确错误，确认没有管理 TCP 监听。
- [x] 2.4 验证 Windows 磁盘文件身份、拒绝共享锁句柄继承和 QEMU 生命周期保护；在 QEMU 存活、父进程异常退出及路径别名场景启动第二个写者，确认持续拒绝，不依赖不支持的 `locking=on`。
- [x] 2.5 验证 Guest 有序停止、同步/卸载与 WHPX 退出路径，记录实际 QEMU 参数、flush/退出顺序和失败诊断到本变更验收附件；明确临时资源阶段不等于最终单文件通过。

## 3. 无共享公共 Guest 和持久磁盘

- [x] 3.1 清理 Guest helper、systemd/RootFS 和 kernel 配方中的 9P 挂载、workspace-sharing 标记/参数及专用补丁，保留内部 ext4 bind；验证无共享设备时存储阶段成功，磁盘未挂载时阻止 Docker/Piwork。
- [x] 3.2 生成固定依赖的 kernel/initramfs/只读 RootFS 与无外部 backing 的 qcow2 模板，内置第 1 组的原版 Piwork 和匹配生产镜像；核对资源清单、必要驱动、镜像身份与磁盘格式。
- [x] 3.3 核对 Core、Docker、实际 containerd root、Work private/workspace 和 Service 持久卷全部位于 state ext4；使用真实容器写入文件和 SQLite 事务，重启后验证文件哈希与数据库完整性。
- [x] 3.4 保持阶段状态、镜像缺失加载和首次引导行为，加入有价值的存储/启动故障验证；确认缺失/错误持久盘不落到临时根，缺失镜像能准备、身份不符则明确失败。
- [x] 3.5 更新双语 README 的磁盘布局、Files 入口、正常关机与备份说明；在真实 KVM Guest 按说明上传下载普通 workspace 文件，确认没有新增 `shared/` 适配或 Host 共享依赖。

## 4. 公共 Launcher 与 Linux 无共享实现

- [x] 4.1 拆分公共启动流程和平台接口，统一 `--data-dir` 为安装根；覆盖默认路径、参数/帮助无副作用、安装元数据与原子新盘创建测试，确认未知内容、坏盘和缺失已有盘均不被覆盖。
- [x] 4.2 清理 Linux launcher/QEMU 构建中的 fsdev/9P、xattr 探测、Host UID 定制及共享目录关联；实际启动 KVM 检查设备和监听，确认无需 Host 用户 xattr 且全部使用 MMIO。
- [x] 4.3 保留并加强 Linux 安装根/实际磁盘独占及继承 fd 保护；通过更换端口、磁盘别名和 launcher 异常退出的真实进程场景，验证只有原写者退出后才允许再次启动。
- [x] 4.4 核对公共健康/就绪、原版首次引导、日志过滤和关机预算，在 Linux 实测首位管理员创建、正常登录、QuickStart、配置后 ready、Ctrl+C 与超时/提前退出；同步双语命令和诊断说明，保持上游授权语义。

## 5. Windows 原生 Launcher 集成

- [x] 5.1 实现 Windows 本地路径/文件身份、ACL、WHPX 能力探测及公共参数适配；在当前 Home/WHPX 主机运行原生 Windows 测试 EXE，覆盖 Unicode/空格路径、无效参数和只读帮助。按用户确认移除多版本覆盖与额外禁用虚拟化环境要求，保留能力不足时明确失败的实现。
- [x] 5.2 将第 2 组验证过的安装/磁盘继承保护和 Job 进程管理集成到正式启动路径；实际执行重复启动、大小写/junction/硬链接别名和父进程强杀，检查 VM 写者退出前保护未释放。
- [x] 5.3 集成从创建阶段受限的 QMP/QGA named pipes、持久请求/事件、取消及有界错误处理；在实际 QEMU 上验证连续操作、连接中断和权限失败，检查仅当前用户能使用控制材料。
- [x] 5.4 实现原生浏览器打开当前访问地址，复用上游 0.0.8 原有首次引导；实测首位管理员创建、正常登录及 `--no-open`，确认普通日志/进程参数不含真实秘密，不新增私有链接协议。
- [x] 5.5 实现 Windows Ctrl+C 和关闭事件收尾，只有 Guest 同步与 QEMU 退出均确认才记录 clean；实际验证正常重启恢复和窗口关闭/强杀后的异常提示，磁盘与日志均保留。
- [x] 5.6 更新双语 README 的原生 Windows 启动、WHPX 前提、参数、数据路径和正常停止方法；从 Windows 本地终端按文档启动正式 launcher，确认不使用 WSL/Hyper-V Manager/新驱动或其他安装步骤。

## 6. 两平台自包含单文件和缓存

- [x] 6.1 生成无 9P 定制的 Linux QEMU/loader/库/固件闭包及 Windows QEMU/DLL/固件闭包；检查真实依赖清单和来源，证明没有把开发目录或预装 QEMU 当作运行依赖。
- [x] 6.2 将 bundle 读写、平台清单和提取适配到 ELF/PE，接入可重现构建目标，输出 `dist/piwork-microvm` 和 `dist/piwork-microvm.exe`；验证文件类型、manifest、产物 hash 和必要许可证齐全。
- [x] 6.3 维护平台权限/ACL和原子发布的缓存提取，运行真实原生测试覆盖篡改、截断、越界路径、Windows 盘符/重解析、并发与取消；确认错误不执行未验证资源，也不修改持久盘。
- [x] 6.4 分别在最小依赖 Linux 环境与 Windows 本地目录运行最终产物，记录加载程序/库和访问路径；确认无需 Host Docker/QEMU/语言工具链，Windows 没有 WSL/ELF/发行版路径依赖。
- [x] 6.5 更新双语 README 的完整构建和仅复制一个文件启动命令；从空缓存完成首次提取，再次启动验证复用缓存/原盘，不重新构建、格式化或下载 Guest。

## 7. NAT、Files 与 Service 集成

- [x] 7.1 跟随最新原版拆分 UI/Core 两个回环转发与 origin，更新 QEMU 参数及 CLI 测试；验证默认 17891/17871、自定义端口、端口相同/占用、旧 Service 端口已占用仍启动和 HTTP 80 规范 origin，不影响占用程序。
- [x] 7.2 将验收脚本改为原有 workspace 文件路径，支持原生 Windows harness；通过真实浏览器上传下载中文名称文本/二进制，核对字节哈希、修改/删除及 Agent/获准 Service 读取同一卷，确认不依赖共享或新 UI。
- [x] 7.3 从真实 Guest 与 Work 分别验证 DNS/HTTPS，并部署现有授权链上的确定性 Service；在两平台主机浏览器验证 HTTP、WebSocket、流式响应和撤权/只读/无权限行为，生产 Agent 与模型夹具清楚区分。
- [x] 7.4 在业务验收过程中核对实际 backing mount 和数据库路径，记录 Core、历史和 Service 持久计数基线；验证生产数据库均在 ext4，文件经 Files 正常访问，日志与证据脱敏。

## 8. 最终产物端到端验收与交付核对

- [x] 8.1 用最终 Linux ELF 和全新独立 `--data-dir` 完成原版 QuickStart、真实模型请求及文件工具调用、Work、Files、联网和 Service；正常停止后原盘重启，核对管理员/模型/Work/卷身份、工具历史 HTTP 200、文件哈希和 Service 数据，并在原会话继续一次真实模型请求。证据关联实际模型/协议、本次源码和最终产物，合成样本不代替真实模型。
- [x] 8.2 用最终 Windows PE 和 Windows 本地全新独立 `--data-dir` 在当前原生 Home/WHPX 完成与 8.1 相同的真实模型、工具、Files/Service、原盘重启和继续会话验证；记录实际进程、模块、microvm/MMIO/加速器、参数及文件路径，不以 WSL/KVM 或交叉编译结果替代。
- [x] 8.3 两平台正常停止后分别删除可重建缓存，再运行最终文件；验证资源重新提取但原安装、文件、数据库和 Service 数据不变，并复验更换主端口后的重新登录。
- [x] 8.4 对最新最终 ELF/PE 各补齐 Guest 提前退出、真实关闭预算耗尽、launcher 强杀共六个异常退出用例；逐次核对诊断/未确认关闭标记、磁盘保留与写者独占，并以原盘恢复管理员/配置、Work、已确认写入的文件和 Service 数据，检查数据库完整性。汇总既有端口冲突、重复实例、坏/缺盘和损坏缓存证据；不要求准备额外 Windows 版本或关闭宿主虚拟化功能。
- [x] 8.5 按 2026-10-21 用户确认收敛验收范围：删除 Windows 多版本矩阵和第二台干净电脑验证门槛，使用当前两平台及全新独立 `--data-dir` 记录空安装；空安装不等同宿主依赖清空。真实模型结果由 8.1/8.2 实测记录，合成样本失败保留独立范围，不泛化成所有工具会话故障。
- [x] 8.6 核对构建锁、两个最终文件的 hash、资源/许可证清单、实际 QEMU 参数、网络/存储说明和脱敏验收记录一致，运行相应 Go/原生平台检查与 OpenSpec 严格校验；确认只交付本地文件，没有发布、远程推送或遗留目录共享组件。

## 9. Piwork 0.0.9 双入口更新（2026-10-21）

此前 0.0.8 验收附件保留其原始身份，不作为新版本通过证据。以下任务跟随用户最新端口约定实施，不修改上游业务源码。

- [x] 9.1 从官方远程刷新到最新完整 commit，独立干净源码构建 0.0.9 Server/WebUI/生产 Agent 与 Helper，保留源码和镜像身份。
- [x] 9.2 删除旧 Service 端口池与限制，新增 `--core-port`，仅转发 UI/Core 两个回环入口；覆盖参数、同端口拒绝和两平台 QEMU 参数测试，更新 Guest 两项监听。
- [x] 9.3 重建 Linux ELF 与 Windows PE，实际验证 UI/CLI Core、同源 Service HTTP/WebSocket/SSE、Files 和正常关机/原盘重启；两个独立安装使用不同双端口能同时运行。
- [x] 9.4 同步双语说明、当前规格、构建身份和本次验收记录，明确旧记录与本次结果及未验证项。

## 本轮收尾结果（2026-10-21）

43/43 项已完成。8.1/8.2 的两平台真实模型跨重启，以及 8.4 的六次最终产物异常退出/原盘恢复均已实际通过；逐项证据、明确保留的合成样本 503 和测试边界见[收尾验收](evidence/completion-acceptance.md)。本次主规格已同步，变更保持未归档。
