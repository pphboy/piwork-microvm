# MicroVM Single Binary Delivery Spec Delta

## MODIFIED Requirements

### Requirement: 提供可复现输入和真实来源身份

构建 SHALL 锁定实际 Piwork commit、工具链、Guest 依赖、QEMU 和运行库/固件来源及校验，记录原版源码状态、UI 输入 hash、生产镜像身份、产物 hash 和必要许可证。构建流程 SHALL 不推送容器镜像、远程仓库，也不自行发布 Release；容器镜像 MUST NOT 被推送到任何远程 registry。公开 Release SHALL 由独立于构建流程的发布步骤执行，其资产与对应源码义务由该步骤负责。

#### Scenario: 审核并重建两个产物
- **WHEN** 开发者按仓库构建入口和锁定清单重建
- **THEN** 可以取得同一依赖组合，验证源码没有 Piwork 补丁、Server/镜像身份一致，并分别核对 ELF 与 PE 的资源清单

#### Scenario: 区分构建流程与发布步骤
- **WHEN** 只执行构建流程，未执行独立发布步骤
- **THEN** 不产生任何远程推送、容器镜像发布或 GitHub Release，产物仅存在于本地
