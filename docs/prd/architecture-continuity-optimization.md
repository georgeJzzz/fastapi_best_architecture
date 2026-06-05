# PRD: 架构连续性抽取与测试固化

## Problem Statement

FastAPI Best Architecture 的后台代码已经具备清晰的 `api / service / crud / model / schema` 分层，但部分跨模块流程曾分散在 endpoint、service、插件内部模块和工具函数之间。开发者在修改认证、密码安全、插件、资源存在性判断或引用完整性时，需要同时理解 Redis 状态、cookie、动态配置、插件路由挂载、异常语义和数据库访问细节，容易出现行为漂移、重复判断和测试覆盖不足。

这会让新功能开发者难以判断代码应该放在哪一层，也让后续代理或维护者难以沿着项目语言识别稳定边界，例如 `User session`、`Plugin lifecycle`、`Resource presence`、`Reference integrity` 和各类 captcha/state challenge。

## Solution

将关键跨模块流程收口为可命名、可测试、可复用的架构连续性，并用领域文档和后端架构速查文档固化这些边界。开发者从文档中可以直接理解请求如何流转、CRUD 如何开发、插件如何挂载、认证会话如何刷新、密码安全如何检查，以及测试应该落在哪些外部行为边界。

本 PRD 覆盖当前工作树中的架构优化方向：认证与安全流程服务化、插件生命周期模块化、资源存在性与引用完整性统一、插件 API 挂载兼容、启动入口区分、后端开发指南补全。

## User Stories

1. As a backend developer, I want authentication token refresh to go through `User session`, so that access token、refresh token、cookie 和 Redis session 状态保持一致。
2. As a backend developer, I want logout and session revocation to share the same `User session` rules, so that 用户退出、密码变更和单点登录限制不会产生不同清理路径。
3. As a backend developer, I want login captcha verification to be represented as `Login captcha challenge`, so that 动态配置、图片生成、Redis 存储、过期和一次性消费有同一个业务边界。
4. As a backend developer, I want email verification to be represented as `Email captcha challenge`, so that 邮件验证码生成、模板数据、发送、校验和消费保持一致。
5. As a backend developer, I want OAuth2 callback state to be represented as `OAuth2 state challenge`, so that 登录意图、绑定意图、用户绑定元数据和 state 一次性消费不会混杂在 callback endpoint 中。
6. As a backend developer, I want login lockout rules to be represented as `User security gate`, so that 用户状态、失败次数、锁定窗口和错误提示有统一语义。
7. As a backend developer, I want password validation to be represented as `User password policy`, so that 长度、复杂度、哈希校验和历史密码拒绝不会散落在工具函数中。
8. As a backend developer, I want password age checks to be represented as `User password expiry`, so that 缺失变更时间、到期天数、提醒窗口和授权错误保持一致。
9. As a backend developer, I want password update side effects to be represented as `User password change`, so that 历史密码写入、更新时间戳和会话吊销总是一起发生。
10. As a backend developer, I want missing-resource checks to use `Resource presence`, so that service 层不会反复手写 not-found 分支并产生不一致错误文案。
11. As a backend developer, I want related-ID checks to use `Reference integrity`, so that 重复 ID 归一化、已查询记录对比和缺失目标错误保持一致。
12. As a plugin developer, I want plugin discovery, status, dependency ordering, hooks and route injection to be represented as `Plugin lifecycle`, so that 插件运行时行为可以被逐段理解和测试。
13. As a plugin developer, I want plugin routes to be mounted through `Plugin API mounting`, so that 旧公开 URL 兼容性和插件状态依赖注入不会依赖手动 include。
14. As a backend developer, I want optional plugin capabilities to go through `Plugin feature gateway`, so that 核心业务代码不直接依赖可选插件内部目录。
15. As a maintainer, I want a backend architecture guide, so that 新贡献者可以快速了解启动入口、目录职责、请求流转、CRUD 开发步骤和插件系统收口规则。
16. As a maintainer, I want test seams documented at the highest useful boundary, so that 后续代理优先验证外部行为而不是内部调用细节。
17. As a reviewer, I want glossary terms to match code boundaries, so that PRD、issue、测试名和架构讨论不会漂移到被项目明确避免的同义词。
18. As an operator, I want prepared startup to be distinct from lightweight app construction, so that 测试、导入和生产运行不会意外执行插件准备流程。

## Implementation Decisions

- 保持项目现有三层架构：endpoint 负责 FastAPI 参数、依赖和响应包装；service 负责业务规则、跨 DAO 协作和副作用；crud 负责数据库访问。
- 将认证会话连续性命名为 `User session`，并把 token 生成、refresh-cookie、Redis session 状态、用户快照缓存和会话吊销视为一个业务边界。
- 将登录安全拆分为 `Login captcha challenge`、`User security gate`、`User password policy`、`User password expiry` 和 `User password change`，避免把验证码、锁定、密码校验和密码更新副作用混在认证主流程中。
- 将 OAuth2 state 处理命名为 `OAuth2 state challenge`，覆盖 state 生成、payload 存储、登录/绑定意图和一次性消费。
- 将 service 层的单资源查询缺失处理收口为 `Resource presence`，将关联资源 ID 集合校验收口为 `Reference integrity`。
- 将插件系统对外维持为 `Plugin lifecycle` 和 `Plugin feature gateway` 两个主要交互边界，内部拆分为发现、运行状态、API 挂载、包管理、hooks 和能力网关。
- 插件路由注入使用 `Plugin API mounting`，让插件 `plugin.toml` 配置、目标 router 匹配、前缀应用、状态依赖和公开 URL 兼容成为一个可测试流程。
- 启动入口区分轻启动和准备后启动：轻启动适合导入、测试和基础 app 构造；准备后启动负责插件检查、依赖准备、插件路由和 hooks。
- 后端架构速查文档作为开发入口文档，覆盖目录职责、请求调用链、CRUD 开发模板、插件系统规则和常见流程。
- 不创建 ADR：本次优化主要是现有结构的命名、收口和测试固化，虽然重要，但当前没有需要记录为难以逆转且存在明确替代方案取舍的单一架构决策。

## Testing Decisions

- 测试应验证外部行为和业务边界，不验证私有实现细节；测试名称和断言应使用 `CONTEXT.md` 中的 canonical terms。
- `User session` 测试覆盖创建 session、refresh token rotation、cookie 写入、单点登录吊销、用户缓存失效、无效 token 拒绝和会话删除。
- 认证 service 测试覆盖 refresh token 是否委托给 `User session`，并验证请求上下文和 cookie adapter 传递。
- `Login captcha challenge`、`Email captcha challenge` 和 `OAuth2 state challenge` 测试覆盖动态配置、Redis-backed 存储、过期、比较和一次性消费。
- `User security gate`、`User password policy`、`User password expiry` 和 `User password change` 测试覆盖锁定窗口、密码复杂度、历史密码、过期提醒、密码历史写入和会话吊销。
- `Plugin lifecycle` 测试覆盖 registry ordering、运行状态解析、router 构建、hook 注册、插件安装、依赖安装和依赖卸载。
- `Plugin API mounting` 测试覆盖 app router 注入、extend router 注入、缺失目标 router 报错、插件状态依赖注入和公开路径兼容。
- `Resource presence` 和 `Reference integrity` 测试优先落在 service 层，通过缺失资源、重复 ID 和部分缺失关联目标验证统一异常语义。
- 后端架构速查文档通过人工 review 与关键测试文件交叉验证，确保文档中的流程图和模块职责不偏离当前工作树。

## Out of Scope

- 不改变数据库 schema、迁移脚本或初始化 SQL。
- 不改变 API URL、响应结构、权限码或前端菜单协议。
- 不重写插件打包、安装或依赖解析机制，只固化现有运行时边界。
- 不引入新的认证协议、OAuth2 provider 或密码算法。
- 不把所有 service 都强制改造为同一种抽象；只对已识别的高频跨模块连续性做收口。
- 不在 PRD 中锁定具体文件路径或代码片段，避免实现过程中路径变化导致文档过期。

## Further Notes

本 PRD 使用 `CONTEXT.md` 的项目语言，适合作为 GitHub issue 发布并标记 `ready-for-agent`。后续实现或 review 时，应优先检查新增/修改测试是否覆盖这些业务边界，而不是只检查模块是否被拆分。
