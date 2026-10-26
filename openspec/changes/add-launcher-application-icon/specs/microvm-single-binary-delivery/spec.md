# Spec Delta

## ADDED Requirements

### Requirement: GUI 单文件携带并校验图标输入

两平台 GUI 最终单文件 SHALL 携带其原生窗口及自绘标题栏所需的 Piwork 图标，Windows GUI 另 SHALL 内含多尺寸应用图标资源。已支持的 GUI 构建入口 SHALL 使用同一品牌图源与一致的生成规则；缺少或损坏图源、必要资源处理失败时 SHALL 明确终止构建，不产出声称成功但缺少图标的 GUI。所有影响可执行主体的图标资源处理 SHALL 在追加 payload、manifest 和最终 Trailer 之前完成，最终文件 SHALL 仍能按现有协议定位并验证 bundle。GUI 主体复用校验 SHALL 覆盖实际图标、内嵌前端及资源生成配方的输入变化，拒绝不匹配输入的旧主体；CLI SHALL 保持现有无桌面依赖的构建和运行方式。

#### Scenario: 仅复制最终 GUI 文件
- **WHEN** 用户只将匹配平台的最终 GUI 文件复制到满足运行前提的另一目录并离线打开
- **THEN** 应用与窗口图标无需同目录 ICO、PNG、源码或构建工具即可使用，原 bundle 可被正确读取和校验

#### Scenario: Windows 两个构建入口产生一致图标
- **WHEN** 分别使用已有 Python 和原生 PowerShell GUI 构建入口构建相同源码与图源
- **THEN** 两个入口生成相同规则的多尺寸 Piwork 图标，并将其作为可供系统和窗口使用的资源嵌入主体，再由现有流程生成最终 GUI 单文件

#### Scenario: 图源缺失或资源生成失败
- **WHEN** GUI 图源缺失、不可解码或必要的资源生成步骤失败
- **THEN** 构建报告具体错误并停止，不静默使用默认图标，不生成有效成功记录来接受旧图标主体

#### Scenario: 图标或前端输入改变后尝试复用旧主体
- **WHEN** GUI 主体构建后修改品牌图源、内嵌前端或图标生成配方，再尝试封装旧主体
- **THEN** 封装拒绝该主体并要求重建，不仅依据 Go 源码、上游输入或主体文件是否存在来接受复用

#### Scenario: 图标处理不破坏单文件格式
- **WHEN** 对已带应用图标资源的 GUI 主体追加资源包并检查最终产物
- **THEN** Piwork 图标仍可提取或加载，manifest 与 Trailer 定位校验通过，版本信息可读取，追加后没有再执行改变主体或文件尾部的资源处理
