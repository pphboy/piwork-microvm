# Tasks

## 1. 从镜像提取许可证树

- [x] 1.1 在 Guest 镜像构建后增加提取步骤：用一次 `debugfs -R 'rdump /usr/share/doc <tmp>'` 导出文档树，再从 `<tmp>/*/copyright` 选出许可证文件，输出到 `dist/guest/guest-licenses/<package>/copyright`；验证：提取结果与镜像内 `usr/share/piwork-guest-packages.txt` 的包数对照，逐一确认每个包要么有 `copyright`、要么被记为缺口
- [x] 1.2 生成 `dist/guest/guest-licenses/index.json`，记录组件名、来源包、相对路径、大小与 sha256；无文本的包记录 `present: false` 与原因；验证：索引条目数等于已安装包数，且每个 `present: true` 条目的 sha256 与独立 `sha256sum` 一致
- [x] 1.3 让提取只读且不依赖 root：验证：在无 root 权限下运行；运行前后 `dist/guest/rootfs.ext4` 的 sha256 不变；`debugfs` 缺失时给出明确错误并非零退出
- [x] 1.4 确认 BusyBox 的许可证经由 `busybox-static` 的 `copyright` 被覆盖，并在索引中明确标注来源包；验证：在镜像的包清单中找到 `busybox-static`，且其条目在索引中 `present: true`

## 2. 打进产物 payload

- [x] 2.1 在 `scripts/bundle.py` 中把许可证树加入 payload，路径前缀 `provenance/guest-licenses/`；验证：构建后从产物内能解出该目录，且条目数与 `dist/guest/guest-licenses/` 一致
- [x] 2.2 保持确定性打包：条目排序、权限 0444、`mtime` 0、`uid/gid` 0；验证：连续两次构建，`bundle-manifest-<platform>.json` 中许可证相关条目完全一致，且 payload 的 sha256 稳定
- [x] 2.3 记录产物体积增量；验证：对比加入前后 `dist/piwork-microvm` 的字节数，把增量写入任务的完成说明（实测 391,890,720 → 392,490,610，+599,890 字节，+0.15%）

## 3. 发布侧

- [x] 3.1 在发布步骤中生成 `guest-licenses.tar.gz`（与 2.2 相同的确定性规则），并加入发布资产；验证：dry-run 输出的资产清单包含该文件，同时仍为 6+1 个资产
- [x] 3.2 更新发布说明的"已知限制"：许可证文本随产物提供并给出路径，只有真实缺口才写入限制；验证：渲染一次说明，断言其中指向 `provenance/guest-licenses/` 与 `guest-licenses.tar.gz`，且不再出现"只能存在于镜像内部"的表述

## 4. 文档

- [x] 4.1 在 `README.md` 与 `README.zh-CN.md` 的发布一节补充许可证资产的说明；验证：两版 README 标题数、表格行数与代码围栏数一致，新增相对链接目标存在
- [x] 4.2 在 `AGENTS.md` 记录"产物必须随附可读许可证文本"的约定；验证：条目存在，且与 design 的 D2/D4 一致

## 5. 集成校验

- [x] 5.1 端到端重建两个平台产物并演练发布 dry-run，断言许可证树在产物内可解出、资产清单包含 `guest-licenses.tar.gz`、发布说明措辞已更新，且全程未创建 tag、未发布
- [x] 5.2 抽出产物内的许可证树，随机抽取若干组件核对文本与其来源包一致；验证：抽查条目与镜像内对应 `copyright` 逐字节相同
