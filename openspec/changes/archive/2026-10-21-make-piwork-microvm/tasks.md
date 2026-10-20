# Tasks

依赖顺序固定为 Guest → microvm/KVM → 网络 → 数据 → 单文件 → 最终集成。每项指定行为及其验证完成后才勾选；当前已进入实现和真实 KVM 验收。原始输出默认保存在忽略的 `dist/`，脱敏结论归本 change 附件。

第 1–6 节的 41 项为原默认端口版本的完成记录；第 7 节的 `--port` 增量已完成，使用最终 ELF 在真实 KVM 依次验证 8080、8081、默认 7171 和 80。两版验收身份在 acceptance.md 和对应 evidence 目录中明确区分。

## 1. Step 1 — 构建完整 Guest

- [x] 1.1 建立本仓库的 Go/构建目录、忽略规则及固定上游源码获取入口，默认使用 `efce08c228c12f10d18a968b69c3398bb0e783e1`；验证本地 revision 导出与固定远程获取得到同一声明输入、不纳入 `promo/`，且不修改相邻工作区或推送远程。
- [x] 1.2 锁定 Go 1.25.5、Node 24、Guest 基础镜像/包 snapshot、Linux LTS、Docker 28+ 及下载校验，提供隔离构建入口；验证实际工具版本和 checksum，并确认 Host Docker 26 不会作为 Guest 运行时依赖。
- [x] 1.3 复用上游 Makefile/scripts 构建 harness、两套 WebUI 与统一 Go 服务端，生成本地 candidate 元数据并内嵌同版镜像引用；验证服务端/UI 输入身份、CGO disabled、`--help` 以及构建检查均通过，不再指向未知旧发行。
- [x] 1.4 从同一源码构建 production Agent、file-helper、snapshot-helper，令 package-helper 复用 production Agent，导出 Guest 离线镜像包；验证 linux/amd64、真实 image ID、协议/源码标签和服务端内嵌引用相符，生产包不以 acceptance Agent 替代。
- [x] 1.5 实现固定 kernel 配置与 kernel/initramfs 构建入口；验证产物、配置和 checksum，覆盖 MMIO 启动驱动、9P/串口、ext4、namespace/cgroup/overlayfs、veth/bridge/conntrack/NAT 及选定防火墙能力。
- [x] 1.6 制作 Debian RootFS，包含 systemd/networkd、Docker/containerd/runc、qemu-guest-agent、CA 与 Piwork/镜像；实现存储→网络→Docker→镜像→Piwork 服务依赖和安全阶段状态，验证 unit 配置、离线镜像清单及缺失挂载时拒绝替代初始化的检查。
- [x] 1.7 生成只读 rootfs.ext4、tmpfs root overlay/initramfs 和 64 GiB 稀疏 ext4 state 模板，绑定 Docker/containerd/Core 的持久 root；验证文件系统结构、离线完整性和 archive hash，第二次构建能从锁定输入重建，不要求最终 Host 安装 mkfs/qemu-img。
- [x] 1.8 增加 `make guest` 及对应双语使用说明，注明源码输入、工具链和资源输出；在干净构建副本实际执行该命令，确认得到可供下一阶段启动的完整 kernel/initramfs/RootFS/模板/manifest，构建不含 push/release。

## 2. Step 2 — 在真实 KVM 启动 microvm

- [x] 2.1 实现 Go launcher 参数和路径选择，支持默认启动、`--data-dir`、`--help`、`--cpus`、`--memory`；以有意义的参数用例验证错误退出、帮助不写数据/不需 KVM，以及默认 2 vCPU/4096 MiB 和安装路径输出。
- [x] 2.2 实现 Linux/amd64、KVM open/ioctl、资源/空间/权限及磁盘身份检查；验证真实 KVM API 检查成功，缺设备/权限错误安全失败且无 TCG 回退，已有盘缺失或错误不会被重新格式化。
- [x] 2.3 实现 QEMU argv 生成、私有 QMP/QGA/串口通道及 `make boot-dev`，实际以 microvm、KVM、pcie/acpi off 和 MMIO 设备启动第 1 阶段 Guest；用 QMP KVM 查询、设备树和 Guest 启动结果核实，保存真正执行的参数，验证空格/逗号路径不被错误解析。
- [x] 2.4 在真实 Guest 验证 init、持久挂载、cgroup/overlayfs、Docker 28+ 和 Piwork 进程，运行一个具有独立网络/卷的真实容器；以 Guest Engine 信息、容器结果和 `/healthz` 证明成功，不使用 Host Docker 容器替代。
- [x] 2.5 实现阶段探针、QEMU 存活监控、启动 deadline 和空安装/完整 ready 分流；验证未配置模型时及时提供引导方向而不卡在 `/readyz`，镜像/服务错误与 Guest 提前退出能输出安全的具体阶段。
- [x] 2.6 实现安装/目录锁与 QEMU 写盘锁，处理启动失败和孤儿 QEMU；实际尝试同数据并发启动及终止父 launcher 后再启动，确认没有第二个可写 VM、不能靠删 PID 文件或路径别名绕过，原盘字节保留。
- [x] 2.7 实现 QGA 正常关机、Guest 服务停止顺序、120 秒总关闭预算和异常收尾；真实测试 Piwork→Docker/containerd→挂载同步→QEMU 退出，另测失联/超时明确非零失败，正常退出不删数据。
- [x] 2.8 更新本阶段启动/诊断说明并记录实际 QEMU 版本、argv、MMIO/KVM 证据及 Guest 基础结果；按说明重新启动和停止一次，材料明确这是依赖 Host QEMU 的开发阶段。

## 3. Step 3 — NAT、浏览器 QuickStart 与真实 Service

- [x] 3.1 配置 Guest DHCP/DNS、默认路由及 Docker Work bridge/NAT；分别在 Guest、普通容器和真实 Work 网络完成域名解析与外部 HTTPS 请求，记录来源和结果，确认不创建 Host bridge/TAP。
- [x] 3.2 生成全部 65 条回环 hostfwd，设置精确公开 origin 和 Guest listener，加入全端口冲突检查/绑定竞争诊断；以 Host 监听检查及占用 7171、范围内 Service 端口的实际失败测试验证，无 wildcard 外露、漏端口或 7172/API 管理转发。
- [x] 3.3 实现 Guest stdout/日志过滤、私有首次授权文件和 Host 私有浏览器跳转入口，保留现有 setup/登录契约；在真实 Host 浏览器完成首管理员创建、登录和现有 QuickStart，并以合成秘密扫描 Host/Guest 日志确认无密码、Key、proof 或 Token 泄漏。
- [x] 3.4 使用生产 Agent 创建并启动真实 Work，验证 Agent 握手、私有/workspace 卷、Files 上传/读取和 Service MCP/既有认证部署接口；实际容器与 Work 身份匹配，完整交付探针在配置后成功，不把模型 fixture 宣称为真实供应商成功。
- [x] 3.5 经 Piwork 部署确定性 HTTP/WebSocket/SSE Service，使用既有 workspace grant 保存计数/SQLite 数据；从 Host 浏览器经受授权入口验证 HTTP 内容、双向 WebSocket 和流式响应，确认无 Docker Service published port。
- [x] 3.6 验证匿名访问拒绝、Service 独立来源/受支持 Cookie、停止或撤权后的连接处理；以真实浏览器及 Service 观察确认没有因公开 origin/两层 NAT 绕过既有授权，更新双语网络/端口及故障说明。

## 4. Step 4 — Host 共享、数据库边界与完整恢复

- [x] 4.1 实现 data/disks/logs 与自定义 data-dir 的确定性安装关联，Guest 自动挂载 mapped-xattr/9p2000.L 共享并检查 Host xattr/权限；验证真实挂载、同参数复用及错误挂载拒绝启动，准确打印 Host/Guest 路径而不把盘镜像称为目录共享。
- [x] 4.2 实现默认关闭的 Guest workspace 共享补丁，保持两个 local named volumes 和安装/Work 标签，将当前 Work 的独立 9P 子树接到 workspace/shared；验证新建/恢复及 Docker mount namespace/递归传播后 Agent、Files/helper 和真实 Service 看到同一子树，没有第三卷或同步 daemon。
- [x] 4.3 处理 UID/GID 10001、image copy-up、Host 新建文件权限、9P 缓存和原子替换；实际完成 Host 建→Files/Service 改、Work 建→Host 改→Work 删的内容/删除测试，并验证只读 grant 的子挂载也不可写、无 grant 和其他 Work 不能访问。
- [x] 4.4 实现已有 shared 内容的冲突保护、有归属的导入接入与卷清理边界；用冷导出/导入核对 shared 与 ext4 文件完整、导入 Work 具有独立 Host 目录，非空目标不会被挂载遮住，普通删除留存且授权 purge 不误删仍被引用或其他 Work 的数据。
- [x] 4.5 在所选 9P 模式运行 SQLite/WAL、跨进程文件锁、fsync/rename、事务中断与完整性探测，记录支持/限制；同时核实 Core、历史/Memory、Docker/containerd 和 Service 数据库 backing 都为 ext4，并通过真实事务/重开完整性检查，不以降级数据库安全选项换取通过。
- [x] 4.6 真实正常停止并二次启动，核对管理员/模型引用、Work/两卷身份、Session/Memory、ext4/9P 文件、Service 定义及持久计数；按原运行意图恢复并从 Host 再访问 Service，确认不要求重新 QuickStart 或丢失容器外持久数据。
- [x] 4.7 正常停止后仅重建同版 RootFS/清除可重建缓存并复用原数据，再测缺盘、错误格式、共享不可用和占用冲突；验证前者完整恢复、后者明确失败而不初始化替代空安装。
- [x] 4.8 更新双语存储/备份说明与 `--help`，列明 shared 普通文件和镜像内数据库/非共享 workspace 的真实边界；按说明找到双方数据并正常停止后保存整盘、共享树及关联信息，检查没有运行中 Host 并发挂载 ext4 的步骤。

## 5. Step 5 — 构建自包含单 ELF

- [x] 5.1 固定 QEMU 构建/软件包输入，冻结可运行程序、loader、DT_NEEDED/dlopen 闭包及 microvm 固件/数据与许可证；用包内运行方式实际启动已验证 Guest，检查文件访问不依赖原 Host QEMU、库目录或固件路径。
- [x] 5.2 实现内附压缩 payload/manifest/trailer 和流式提取、校验、独占 staging/原子发布；以损坏/截断包、路径越界、并发提取和中断重试等有实际风险的测试验证，不执行未验证资源、不触碰持久盘。
- [x] 5.3 增加 `make piwork-microvm` 生成 `dist/piwork-microvm`，验证 ELF 架构/校验和/资源清单，并从源码目录外运行 `--help` 和真实启动；仅复制该文件就能使用其内含 QEMU/Guest/Piwork，默认不查找 Host QEMU。
- [x] 5.4 用最终 ELF 验证空缓存首次启动、有效缓存第二次启动、损坏缓存重提取和清缓存恢复；核对不会重建整个 Guest、重复无必要导入镜像或重置原安装，磁盘永不保存在缓存中。
- [x] 5.5 更新双语构建/启动/依赖/分发说明，给出 Guest 重建、最终 ELF、默认和自定义启动命令及可直接共享/镜像内数据表；实际执行文档命令并核对必要源码、补丁、锁定清单、许可证及 hash 均随本地交付可取得。

## 6. Step 6 — 最终产物的完整 KVM 集成验收

- [x] 6.1 使用最终 ELF 和独立空安装执行一轮完整 Happy Path：QMP 核实 microvm/KVM/MMIO、Guest Docker/Piwork、真实浏览器 QuickStart、生产 Agent Work、Files、Guest/Work HTTPS/DNS 及受保护 Service HTTP/WebSocket/SSE；每项保留可关联真实对象的脱敏证据。
- [x] 6.2 在同一轮集成中写入账号/配置、Work/Session/Memory、ext4 与 Host shared 文件及 Service SQLite/计数，运行中 Ctrl+C 后第二次启动；逐项比较身份、内容、数据库完整性和 Service 恢复，记录真实关闭与恢复意图而不修改上游语义。
- [x] 6.3 若有用户提供的有效 AI Key，显式运行真实供应商 SDK Run 并验证对应文件/Service 行为；若没有则完成其余链路、将此项明确记录未验证和原因，确定性模型夹具结果单列，确认所有输出不包含秘密。
- [x] 6.4 对最终 ELF 组合验证关键失败路径：KVM 不可用、主站/Service 端口冲突、坏缓存/盘、9P 权限错误、同盘二次启动、launcher 异常退出留存 QEMU、Guest 早退和关机超时；确认错误可诊断、没有第二个磁盘写者或数据重置。
- [x] 6.5 尽可能在未预装 QEMU/Docker/开发工具的独立干净 KVM Host 上仅复制 ELF 重跑启动和 Work/Service/持久化；不可取得该环境时明确记录限制、当前 Host 的依赖隔离结果及复验命令，不把普通容器检查标为干净 Host KVM 验收通过。
- [x] 6.6 在本 change 附件整理实际 ELF/hash、固定输入、构建/启动命令、真实 QEMU argv、网络/存储布局、逐项通过/失败/未验证与准确原因；核对用户八类交付要求、OpenSpec 严格校验和源码 diff，确保没有无关 UI 改动、远程推送或 Release 发布。

## 7. 增量 — 自定义 Host 主入口端口

- [x] 7.1 增加 launcher `--port PORT`，默认 7171，仅接受 1–65535 的整数并排除 17891–17954；在 KVM 检查、缓存提取和数据写入前拒绝缺值、非数字、0、负数、越界及范围重叠，帮助显示参数/默认值/限制；前置检查仅试绑定所选主入口与全部 Service 端口，冲突或绑定权限不足明确失败且不自动换端口。
- [x] 7.2 将所选端口贯通 QEMU hostfwd、`piwork.host_port` kernel 参数及 Guest helper 的读取/校验，Guest listener 保持 7171，`--public-origin` 使用 Host 所选端口；同步 Host 健康/完整就绪探针、私有首次设置链接校验和输出地址，缺省 Guest 参数兼容 7171、显式非法值安全失败；保留现有进程内 Core transport、Agent/Service 内部端口、安装关联及独占锁。
- [x] 7.3 增加有意义的参数/Guest 配置/QEMU 映射与端口冲突回归，确认不误检查原 Host 7171、不扩大监听地址或转发 Guest 内部管理端口；更新双语启动、端口限制及更换 origin 后重新登录说明，重建包含 Guest helper 的 RootFS 和自包含 `dist/piwork-microvm`，核实帮助与资源清单。
- [x] 7.4 用重建后的最终 ELF 在真实 KVM 验证默认 7171 和非默认 8080：受控占用 Host 7171 时非默认入口仍成功且不影响原进程，公开 origin、首次设置、QuickStart、管理界面、真实 Work/Files、Service HTTP/WebSocket/SSE 和就绪探针均正确；正常停止后相同 data-dir 改用另一合法端口，重新登录/授权并核对原账号、配置、Work/Service 身份、文件及业务数据库数据恢复；验证所选主入口与 Service 冲突安全失败，单实例锁不因更换主入口而失效。
- [x] 7.5 记录端口增量的最终 ELF/hash、实际 QEMU argv、Guest 参数/公开 origin、浏览器/Service 和更换端口恢复证据及准确限制，将原版本证据与新增结果区分；确认其余网络/存储边界保持，运行 OpenSpec 严格校验，完成后才勾选增量任务，不推送远程或发布 Release。
