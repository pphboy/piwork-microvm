# MicroVM Single Binary Delivery Spec Delta

## ADDED Requirements

### Requirement: 随产物提供可读的第三方许可证文本

分发产物 SHALL 为 Guest 镜像内分发的每一类第三方组件提供可直接阅读的许可证文本，MUST NOT 要求启动 VM 才能取得。覆盖范围 SHALL 至少包含 Guest rootfs 内的全部已安装分发包、initramfs 中的 BusyBox、内核与 QEMU 及其随产物提供的运行库。许可证文本 SHALL 位于产物解压资源中可预见的路径，并以组件标识或来源包名定位。产物 SHALL 另附一份索引，列出每个组件、其来源包与对应的许可证文件；某个包确实无可提取文本时，索引 SHALL 如实标注该缺口，MUST NOT 静默省略。

#### Scenario: 无需启动 VM 即可阅读许可证
- **WHEN** 用户解压产物资源后查看许可证目录
- **THEN** 能按组件名找到每个已安装包的许可证文本，全程不需要启动 Guest

#### Scenario: 镜像内的分发包变化
- **WHEN** Guest rootfs 的安装包集合发生变化并重新构建产物
- **THEN** 许可证树与索引随之更新，新增包的文本出现在产物中，不再存在的包不再列出

#### Scenario: 某个包缺少可提取文本
- **WHEN** 某个已安装包没有 `/usr/share/doc/<pkg>/copyright`
- **THEN** 索引如实标注该组件缺少随附文本，不静默省略该包

#### Scenario: 提取过程不改动镜像
- **WHEN** 构建过程生成许可证树
- **THEN** 以只读方式读取镜像内容，不挂载、不修改 `rootfs.ext4`，也不需要 root 权限
