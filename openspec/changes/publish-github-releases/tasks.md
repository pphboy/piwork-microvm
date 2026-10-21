# Tasks

## 1. 版本身份与 `--version`

- [x] 1.1 在 `internal/launcher` 增加构建期可注入的版本变量（自身版本、上游 Piwork 版本与完整 commit、bundle manifest 版本），并提供默认开发版本；验证：单元测试断言未注入时自身版本形如 `0.0.0-dev.<非空>`，且不等于任何发布版本字面量
- [x] 1.2 实现 `--version`，使其与 `--help` 同级、在任何副作用（读取安装目录、检查加速器、绑定端口）之前返回且退出码为 0；验证：单元测试断言输出包含自身版本、上游版本与完整 commit、bundle manifest 版本三行，并断言未创建任何安装目录
- [x] 1.3 在 `scripts/bundle.py` 构建 launcher 时注入版本：存在对应 annotated tag 时注入该 tag 的版本，否则注入开发版本；验证：以显式版本构建一次并运行产物 `--version`，断言输出与注入值一致

- [x] 1.4 让构建接受显式发布版本（环境变量优先于 HEAD 的 tag，再回退开发版本），由 `make release` 传入；验证：设置该变量构建一次，产物 `--version` 报该值；不设置时仍回退 tag 或开发版本

## 2. 发布清单

- [x] 2.1 实现发布清单生成，输出 `inputs`、`artifacts`、`verification` 三组；验证：对现有 `dist/` 产物生成清单，断言三组字段齐全，且 `artifacts` 中每个 sha256 与 `sha256sum` 的独立计算结果一致
- [x] 2.2 使 `inputs` 取自 `build.lock.json` 的锁定输入身份；验证：连续生成两次清单，断言两次 `inputs` 完全相同（而 `artifacts` 允许不同）
- [x] 2.3 使 `verification` 记录基准（锁定输入或产物字节）、平台、时间与证据路径，未运行的平台标注为未验证；验证：在无任何验收证据时生成清单，断言平台被标为未验证且输出中不出现表示通过的表述
- [x] 2.4 移除 `scripts/acceptance-record.py` 对 `dist/delivery.json` 的重复写出，避免与发布清单语义重叠；验证：运行该脚本后断言 `openspec/changes/support-windows-and-disk-only-storage/evidence/two-port/artifacts.json` 仍被写出，且 `dist/delivery.json` 不再产生

## 3. 发布门槛

- [x] 3.1 实现 preflight：工作树干净、`make source-check` 通过、目标版本尚未打过 tag；验证：分别构造脏工作树、锁定源码被修改、tag 已存在三种情况，断言各自被拒绝并给出对应原因
- [x] 3.2 将 `go test ./...` 与两平台产物构建纳入门槛；验证：故意使一个测试失败，断言发布被拒绝且不产生 tag

- [x] 3.3 门槛校验产物自报版本与目标版本一致；验证：用与产物不符的版本运行发布，断言被拒绝且不产生 tag

## 4. 发布说明与对应源码

- [x] 4.1 实现发布说明模板，包含"对应源码"一节与"已知限制"一节；验证：渲染一次，断言含 Linux 6.6.159 与 QEMU 10.0.8 的上游版本与锁定 sha256、GPL §3(b) 书面提供承诺、以及 Guest rootfs 分发包许可证未随附的已知限制
- [x] 4.2 生成 `qemu-patches.tar.gz` 打包 `guest/qemu/*.patch`；验证：解包后与源文件逐字节一致，且补丁数量与 `build.lock.json` 中记录的 Windows 补丁数一致

## 5. 发布步骤与 Make 目标

- [x] 5.1 实现 `make release VERSION=<v>`，执行 preflight、测试、构建、清单、说明五步，全部产物落在本地；验证：运行后断言未创建 tag、未产生任何远程发布，且清单与说明已生成
- [x] 5.2 实现 `make release-publish VERSION=<v>`，打 annotated tag 并上传两个产物、各自 `.sha256`、发布清单与 `qemu-patches.tar.gz`，并提供 dry-run 模式；验证：dry-run 输出目标仓库、tag 名与完整资产清单，且断言未创建 tag、未调用远程发布
- [x] 5.3 在 preflight 中检查 `gh` 存在且已认证；验证：在 `gh` 不可用或未认证的环境下断言提前失败，且失败发生在任何构建之前

## 6. 文档

- [x] 6.1 在 `README.md` 与 `README.zh-CN.md` 新增发布一节，说明版本号约定、资产命名、验收声称基准与对应源码；验证：两版 README 的标题数、表格行数与代码围栏数一致，且新增相对链接目标均存在
- [x] 6.2 在 `AGENTS.md` 记录发布约定（构建不发布、发布为独立步骤、tag 为版本事实来源）；验证：条目存在且与 `design.md` 的 D1/D5 一致

## 7. 集成校验

- [x] 7.1 在干净工作树上端到端演练 `make release VERSION=0.1.0` 与 `make release-publish VERSION=0.1.0` 的 dry-run，断言清单、说明、资产与 tag 名齐全且一致，且全程未产生 tag 与远程发布
- [ ] 7.2 执行首次公开发布 `v0.1.0`（需用户明确授权后执行），并在 GitHub 上核对资产齐全、校验和与发布清单一致；验证：Release 页面包含两个产物、各自 `.sha256`、发布清单与补丁归档，且发布说明含对应源码与已知限制两节
