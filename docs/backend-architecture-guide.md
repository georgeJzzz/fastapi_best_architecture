# FastAPI 后端框架架构速查

本文按当前 `backend/` 工作树整理，目标是让新功能开发者能快速知道代码放哪里、请求怎么流转、常用包做什么，以及如何快速开发一个 CRUD。

## 1. 后端总览

这个后端是一个企业后台风格的 FastAPI 应用，核心结构是：

```text
HTTP 请求
  -> FastAPI app
  -> middleware / context / auth
  -> app router
  -> api endpoint
  -> service
  -> crud dao
  -> SQLAlchemy AsyncSession
  -> database
```

运行时还会接入 Redis、Celery、Socket.IO、插件系统、Prometheus 和 OpenTelemetry。

启动入口分两类：

- `backend.main:app`：轻启动入口，默认 `create_app(prepare=False, plugin_runtime=False)`，适合导入、测试、基础 app 构造。
- `backend.prepared_main:app`：运行入口，`create_app(prepare=True, plugin_runtime=True)`，会检查插件并安装插件依赖，然后加载插件路由和 hooks。

## 2. 目录 Tree

```text
backend/
├── main.py                 # 轻启动入口，构造 FastAPI app
├── prepared_main.py        # 生产/运行入口，启用插件准备和插件运行时
├── run.py                  # granian 本地运行入口
├── cli.py                  # fba 命令行工具
├── core/
│   ├── conf.py             # 配置读取，pydantic-settings
│   ├── path_conf.py        # 路径常量
│   └── registrar.py        # app 注册：日志、静态文件、中间件、路由、分页、异常、指标
├── database/
│   ├── db.py               # SQLAlchemy async engine/session 和 FastAPI session 依赖
│   └── redis.py            # Redis 客户端
├── common/
│   ├── model.py            # SQLAlchemy 基类、通用字段、逻辑删除、时间字段
│   ├── schema.py           # Pydantic schema 基类和通用类型
│   ├── response/           # 统一响应结构
│   ├── exception/          # 项目异常和异常处理器
│   ├── security/           # JWT、RBAC、权限、数据权限
│   ├── pagination.py       # fastapi-pagination 封装
│   ├── cache/              # 本地缓存、Pub/Sub
│   ├── observability/      # Prometheus 和 OpenTelemetry
│   └── socketio/           # Socket.IO server 和事件
├── middleware/
│   ├── access_middleware.py
│   ├── i18n_middleware.py
│   ├── jwt_auth_middleware.py
│   ├── opera_log_middleware.py
│   └── state_middleware.py
├── app/
│   ├── router.py           # 聚合 admin/task 等业务模块路由
│   ├── admin/              # 后台管理模块
│   │   ├── api/            # HTTP endpoint 层
│   │   ├── service/        # 业务规则层
│   │   ├── crud/           # 数据访问层
│   │   ├── model/          # SQLAlchemy ORM 模型
│   │   ├── schema/         # Pydantic 入参/出参
│   │   ├── session/        # User session
│   │   └── tests/          # admin 模块测试
│   └── task/               # 定时任务/Celery 模块
│       ├── api/
│       ├── service/
│       ├── crud/
│       ├── model/
│       ├── schema/
│       └── tasks/
├── plugin/
│   ├── lifecycle.py        # 插件生命周期兼容 Interface
│   ├── registry.py         # 插件发现、配置解析、依赖排序
│   ├── runtime_status.py   # Redis-backed 插件状态
│   ├── api_mounting.py     # 插件路由挂载
│   ├── package_manager.py  # 插件安装、卸载、打包、依赖处理
│   ├── hooks_runtime.py    # 插件 hooks
│   ├── config/ dict/ notice/ email/ oauth2/ code_generator/
│   └── tests/
├── alembic/                # 数据库迁移
├── sql/                    # 初始化 SQL
├── static/                 # 静态资源
├── locale/                 # i18n 文案
└── utils/                  # 时间、序列化、动态导入、限流、树构建等通用工具
```

## 3. 启动和请求调用流程

### 3.1 app 构造

`backend.main.create_app()` 调用 `backend.core.registrar.register_app()`：

```text
create_app()
  -> register_app(plugin_runtime=...)
     -> FastAPI(...)
     -> register_logger()
     -> register_socket_app()
     -> register_static_file()
     -> register_middleware()
     -> register_router()
     -> register_page()
     -> register_exception()
     -> register_metrics()      # 仅当配置启用
```

`register_app()` 通过 lifespan 在启动时做这些事：

- 创建数据库表：`create_tables()`
- 初始化 Redis：`redis_client.init()`
- 初始化 Snowflake 节点
- 启动操作日志消费任务
- 启动缓存 Pub/Sub listener
- 退出时关闭 Pub/Sub、Snowflake、Redis

### 3.2 路由聚合

普通业务路由：

```text
backend.app.router.router
  -> backend.app.admin.api.router.v1
     -> backend.app.admin.api.v1.auth
     -> backend.app.admin.api.v1.sys
     -> backend.app.admin.api.v1.log
     -> backend.app.admin.api.v1.monitor
  -> backend.app.task.api.router.v1
```

插件运行时启用后：

```text
plugin_lifecycle.build_router()
  -> plugin_registry.parse_config()
  -> plugin_registry.order()
  -> plugin_api_mounting.build_router()
     -> inject_extend_router()
     -> inject_app_router()
```

扩展级插件通过 `plugin.toml` 的 `[api.<file>]` 配置把插件 `api/v1/*.py` 挂到目标模块。例如 `backend/plugin/config/plugin.toml`：

```toml
[app]
extend = "admin"

[api.config]
prefix = "/sys/configs"
tags = "系统参数配置"
```

这表示插件文件 `backend/plugin/config/api/v1/config.py` 会注入到 `backend.app.admin.api.v1` 对应位置，并保留 `/sys/configs` 路径前缀。

### 3.3 单个 CRUD 请求流程

以部门查询为例：

```text
GET /api/v1/sys/depts/{pk}
  -> backend/app/admin/api/v1/sys/dept.py:get_dept()
     -> DependsJwtAuth 验证登录
     -> CurrentSession 注入 AsyncSession
     -> dept_service.get(db, pk)
        -> dept_dao.get(db, pk)
           -> CRUDPlus.select_model_by_column(...)
        -> errors.require_found(...)
     -> response_base.success(data=dept)
```

写请求使用 `CurrentSessionTransaction`，由依赖提供事务会话：

```text
POST /api/v1/sys/depts
  -> RequestPermission("sys:dept:add")
  -> DependsRBAC
  -> CurrentSessionTransaction
  -> dept_service.create()
  -> dept_dao.create()
  -> response_base.success()
```

## 4. 每个板块的作用

| 板块 | 作用 | 开发时主要关注 |
| --- | --- | --- |
| `api/` | FastAPI endpoint，声明路由、参数、权限依赖、响应包装 | 不放复杂业务规则 |
| `service/` | 业务规则、资源存在性、冲突校验、跨 DAO 协作、缓存/session 副作用 | 新业务逻辑优先放这里 |
| `crud/` | 数据访问，封装 SQLAlchemy/CRUDPlus 查询、创建、更新、逻辑删除 | 不放 HTTP、权限和响应 |
| `model/` | SQLAlchemy ORM 表结构 | 表名、字段、索引、关联 |
| `schema/` | Pydantic 入参/出参 | 字段校验、OpenAPI 描述 |
| `common/` | 跨模块基础设施 | 响应、异常、分页、安全、缓存、观测 |
| `core/` | app 和配置装配 | 启动流程、中间件、路由注册 |
| `database/` | DB/Redis 连接与依赖 | session、事务、连接池 |
| `middleware/` | 请求前后处理 | 日志、JWT、i18n、上下文 |
| `plugin/` | 插件发现、状态、路由挂载、hooks、包管理 | 新插件或插件接口变更 |
| `app/task/` | Celery 定时任务 | scheduler/result/control API 和任务执行 |

### 4.1 架构连续性术语

本仓库用 `CONTEXT.md` 里的 canonical terms 描述跨模块业务边界。写 issue、测试名、PRD 或架构说明时优先使用这些词，避免漂移到局部实现名。

| Term | 在后端中的边界 |
| --- | --- |
| `User session` | access token、refresh token、Redis-backed session state、用户缓存和 refresh-cookie 的认证连续性 |
| `Login captcha challenge` | 登录验证码生成、存储、过期、比较和一次性消费 |
| `Email captcha challenge` | 邮件验证码生成、邮件发送、Redis-backed 验证码状态和一次性消费 |
| `OAuth2 state challenge` | OAuth2 login/binding state 生成、payload 存储、校验和一次性消费 |
| `User security gate` | 用户状态、登录失败次数、锁定窗口和锁定错误提示 |
| `User password policy` | 密码长度、复杂度、哈希验证和历史密码拒绝 |
| `User password expiry` | 密码变更时间、过期天数、提醒窗口和过期授权错误 |
| `User password change` | 密码历史写入、密码变更时间更新和 User session 吊销 |
| `Resource presence` | service 层 required resource 的统一 not-found 判断 |
| `Reference integrity` | service 层关联 ID 集合完整性校验 |
| `Plugin lifecycle` | 插件发现、配置解析、运行状态、依赖排序、路由、hooks、安装和依赖处理 |
| `Plugin API mounting` | 插件 API 文件发现、目标 router 匹配、prefix 应用、状态依赖注入和公开 URL 兼容 |
| `Plugin feature gateway` | 核心业务代码访问 email/config/oauth2/casbin 等可选插件能力的统一入口 |

## 5. 使用的主要包

### Web 和服务运行

- `fastapi`：HTTP 框架和依赖注入。
- `starlette-context`：请求上下文，配合 trace id、IP、UA 等信息。
- `granian`：ASGI 服务运行器。
- `python-socketio`：Socket.IO 支持。
- `msgspec`：高性能 JSON 响应。

### 数据库和缓存

- `sqlalchemy[asyncio]`：异步 ORM 和查询。
- `sqlalchemy-crud-plus`：CRUDPlus 基础查询/写入封装。
- `asyncpg`：PostgreSQL async driver。
- `asyncmy` / `pymysql`：MySQL driver。
- `psycopg[binary]`：PostgreSQL 辅助 driver。
- `alembic`：数据库迁移。
- `redis[hiredis]`：Redis 客户端。
- `cachebox`：本地缓存。

### 数据校验和配置

- `pydantic`：schema、字段校验、响应模型。
- `pydantic-settings`：配置读取。
- `rtoml`：插件 `plugin.toml` 解析。

### 认证、安全、权限

- `python-jose`：JWT 编解码。
- `pwdlib` / `bcrypt`：密码哈希和校验。
- `cryptography` / `itsdangerous`：加密和安全 token 工具。
- `pyrate-limiter`：限流。
- `py-ip2region` / `user-agents`：IP 和 UA 解析。

### 任务和插件

- `celery` / `celery-aio-pool`：异步任务。
- `flower`：Celery 监控。
- `dulwich`：Git 插件安装。
- `jinja2`：代码生成模板。
- `fast-captcha`：验证码生成。

### 可观测性

- `prometheus-client`：Prometheus 指标。
- `opentelemetry-sdk` 和各类 `opentelemetry-instrumentation-*`：链路追踪和自动埋点。
- `loguru`：日志。

### 开发工具

- `pytest` / `pytest-sugar`：测试。
- `ruff`：lint 和 format。
- `prek`：pre-commit 风格的检查入口。
- `cappa`：CLI 命令框架。

## 6. 如何快速开发一个 CRUD

推荐按 `model -> schema -> crud -> service -> api -> router` 的顺序做。

### 6.1 手写 CRUD

假设新增 `book` 资源，放在 `backend/app/admin/`：

```text
backend/app/admin/
├── model/book.py
├── schema/book.py
├── crud/crud_book.py
├── service/book_service.py
└── api/v1/sys/book.py
```

#### 1. 写 model

继承 `Base` 可获得通用 `created_time`、`updated_time`、`deleted`、`deleted_time`：

```python
import sqlalchemy as sa

from sqlalchemy.orm import Mapped, mapped_column

from backend.common.model import Base, id_key


class Book(Base):
    """图书表"""

    __tablename__ = 'sys_book'

    id: Mapped[id_key] = mapped_column(init=False)
    name: Mapped[str] = mapped_column(sa.String(64), comment='图书名称')
    status: Mapped[int] = mapped_column(default=1, comment='状态')
```

同时在 `backend/app/admin/model/__init__.py` 导出该模型，确保 `create_tables()`、Alembic 和动态模型发现能看到它。

#### 2. 写 schema

```python
from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase


class BookSchemaBase(SchemaBase):
    """图书基础模型"""

    name: str = Field(description='图书名称')
    status: int = Field(description='状态')


class CreateBookParam(BookSchemaBase):
    """创建图书参数"""


class UpdateBookParam(BookSchemaBase):
    """更新图书参数"""


class DeleteBookParam(SchemaBase):
    """删除图书参数"""

    pks: list[int] = Field(description='图书 ID 列表')


class GetBookDetail(BookSchemaBase):
    """图书详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_time: datetime
    updated_time: datetime | None = None
```

#### 3. 写 crud

```python
from typing import Sequence

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.app.admin.model import Book
from backend.app.admin.schema.book import CreateBookParam, UpdateBookParam
from backend.utils.timezone import timezone


class CRUDBook(CRUDPlus[Book]):
    async def get(self, db: AsyncSession, pk: int) -> Book | None:
        return await self.select_model(db, pk, deleted=0)

    async def get_select(self) -> Select:
        return await self.select_order('id', 'desc', deleted=0)

    async def get_all(self, db: AsyncSession) -> Sequence[Book]:
        return await self.select_models(db, deleted=0)

    async def create(self, db: AsyncSession, obj: CreateBookParam) -> None:
        await self.create_model(db, obj)

    async def update(self, db: AsyncSession, pk: int, obj: UpdateBookParam) -> int:
        return await self.update_model_by_column(db, obj, id=pk, deleted=0)

    async def delete(self, db: AsyncSession, pks: list[int]) -> int:
        return await self.delete_model_by_column(
            db,
            allow_multiple=True,
            logical_deletion=True,
            deleted_flag_column='deleted',
            deleted_flag_value=self.model.id,
            deleted_at_column='deleted_time',
            deleted_at_factory=timezone.now(),
            id__in=pks,
            deleted=0,
        )


book_dao: CRUDBook = CRUDBook(Book)
```

#### 4. 写 service

```python
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.crud.crud_book import book_dao
from backend.app.admin.model import Book
from backend.app.admin.schema.book import CreateBookParam, DeleteBookParam, UpdateBookParam
from backend.common.exception import errors
from backend.common.pagination import paging_data


class BookService:
    async def get(self, *, db: AsyncSession, pk: int) -> Book:
        return errors.require_found(await book_dao.get(db, pk), msg='图书不存在')

    async def get_list(self, db: AsyncSession) -> dict[str, Any]:
        book_select = await book_dao.get_select()
        return await paging_data(db, book_select)

    async def get_all(self, *, db: AsyncSession) -> Sequence[Book]:
        return await book_dao.get_all(db)

    async def create(self, *, db: AsyncSession, obj: CreateBookParam) -> None:
        await book_dao.create(db, obj)

    async def update(self, *, db: AsyncSession, pk: int, obj: UpdateBookParam) -> int:
        return await book_dao.update(db, pk, obj)

    async def delete(self, *, db: AsyncSession, obj: DeleteBookParam) -> int:
        return await book_dao.delete(db, obj.pks)


book_service: BookService = BookService()
```

业务校验放 `service`，例如名称唯一、关联资源存在、状态限制、删除前检查子资源等。不要把这些规则散到 `api` 或 `crud`。

#### 5. 写 api

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from backend.app.admin.schema.book import CreateBookParam, DeleteBookParam, GetBookDetail, UpdateBookParam
from backend.app.admin.service.book_service import book_service
from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter()


@router.get('/{pk}', summary='获取图书详情', dependencies=[DependsJwtAuth])
async def get_book(db: CurrentSession, pk: Annotated[int, Path(description='图书 ID')]) -> ResponseSchemaModel[GetBookDetail]:
    book = await book_service.get(db=db, pk=pk)
    return response_base.success(data=book)


@router.get('', summary='分页获取所有图书', dependencies=[DependsJwtAuth, DependsPagination])
async def get_books_paginated(db: CurrentSession) -> ResponseSchemaModel[PageData[GetBookDetail]]:
    page_data = await book_service.get_list(db=db)
    return response_base.success(data=page_data)


@router.post('', summary='创建图书', dependencies=[Depends(RequestPermission('sys:book:add')), DependsRBAC])
async def create_book(db: CurrentSessionTransaction, obj: CreateBookParam) -> ResponseModel:
    await book_service.create(db=db, obj=obj)
    return response_base.success()


@router.put('/{pk}', summary='更新图书', dependencies=[Depends(RequestPermission('sys:book:edit')), DependsRBAC])
async def update_book(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='图书 ID')],
    obj: UpdateBookParam,
) -> ResponseModel:
    count = await book_service.update(db=db, pk=pk, obj=obj)
    return response_base.success_by_count(count)


@router.delete('', summary='批量删除图书', dependencies=[Depends(RequestPermission('sys:book:del')), DependsRBAC])
async def delete_books(db: CurrentSessionTransaction, obj: DeleteBookParam) -> ResponseModel:
    count = await book_service.delete(db=db, obj=obj)
    return response_base.success_by_count(count)
```

#### 6. 注册 router

在 `backend/app/admin/api/v1/sys/__init__.py` 导入并 include：

```python
from backend.app.admin.api.v1.sys.book import router as book_router

router.include_router(book_router, prefix='/books', tags=['图书'])
```

也要在菜单/权限数据里补 `sys:book:add`、`sys:book:edit`、`sys:book:del`，否则 RBAC 会拦截请求。

### 6.2 使用代码生成插件

项目内置 `backend/plugin/code_generator/`，模板已经覆盖：

- `model.jinja`
- `schema.jinja`
- `crud.jinja`
- `service.jinja`
- `api.jinja`
- SQL 初始化模板

适合从已有数据库表生成标准 CRUD 切片。生成后仍建议人工检查：

- `model` 字段类型是否符合业务语义
- `schema` 是否需要更严格校验
- `service` 是否需要资源存在性、唯一性、引用完整性等规则
- `api` 权限码和路由前缀是否符合菜单体系
- 是否需要 Alembic migration 或初始化 SQL

## 7. CRUD 开发检查清单

- `model`：表名、字段、索引、唯一约束、逻辑删除是否正确。
- `schema`：创建/更新/详情/删除参数是否分开，字段描述是否清晰。
- `crud`：只处理数据库访问，默认过滤 `deleted=0`。
- `service`：`Resource presence` 用 `errors.require_found()`，`Reference integrity` 用 `require_complete_ids()`，冲突用 `ConflictError`，禁止操作用 `ForbiddenError`。
- `api`：读接口用 `CurrentSession`，写接口用 `CurrentSessionTransaction`。
- `api`：登录保护用 `DependsJwtAuth`，业务权限用 `RequestPermission(...)` + `DependsRBAC`。
- `response`：统一用 `response_base.success()` 或 `success_by_count()`。
- `router`：在模块 `__init__.py` 或上层 router 注册前缀和 tags。
- `tests`：优先测最高可用 seam 的外部行为，不测私有实现细节；需要数据库/Redis 的集成测试单独隔离。
- `docs/menu`：补菜单、权限码、前端路由或初始化 SQL。

## 8. 常见调用链

### 登录

```text
api/v1/auth/auth.py
  -> auth_service.login()
     -> user_login_attempt_service.login()
        -> login_captcha_service.verify_if_enabled()
        -> user_security_gate.check_login_allowed()
        -> user_password_policy.verify()
        -> user_password_expiry.check()
        -> user_session_manager.create()
     -> login_log_service.create()
```

### 刷新 Token

```text
auth_service.refresh_token()
  -> request.cookies[COOKIE_REFRESH_TOKEN_KEY]
  -> UserSessionContext.from_current_request()
  -> user_session_manager.refresh()
  -> ResponseCookieAdapter(response)
  -> GetNewToken
```

### 登录安全

```text
user_login_attempt_service.login()
  -> Login captcha challenge
  -> User security gate
  -> User password policy
  -> User password expiry
  -> User session
```

### 密码变更

```text
user_password_change_service.update_own() / reset_by_admin()
  -> User password policy
  -> User password change
     -> password history
     -> password_changed_time
     -> User session revoke_user()
```

### 插件验证码与 OAuth2 state

```text
email_captcha_service.send() / verify()
  -> Email captcha challenge

oauth2_state_service.create_login() / create_binding() / consume()
  -> OAuth2 state challenge
```

### 数据权限过滤

```text
api endpoint
  -> Depends(DataPermissionFilter(Model))
  -> filter_data_permission()
     -> request.user.roles/scopes/rules
     -> SQLAlchemy ColumnElement[bool]
  -> service
  -> crud 查询时带入 data_filter
```

### 插件路由挂载

```text
prepared_main:app
  -> create_app(prepare=True, plugin_runtime=True)
  -> prepare_plugins()
  -> register_router(plugin_runtime=True)
  -> plugin_lifecycle.build_router()
  -> plugin_registry.parse_config()
  -> plugin_api_mounting.inject_extend_router()
  -> PluginStatusChecker(plugin_name)
```

## 9. 插件系统收口规则

插件系统对外只暴露一个包级公开 Interface：

```python
from backend.plugin import plugin_features, plugin_lifecycle
```

业务外部代码不要直接导入 `backend.plugin.lifecycle`，也不要直接依赖 `registry/runtime_status/api_mounting/package_manager/hooks_runtime` 这些 Implementation Module。业务外部代码也不要直接导入 `backend.plugin.email.*`、`backend.plugin.oauth2.*`、`backend.plugin.config.*`、`backend.plugin.casbin_rbac.*` 这类可选插件内部路径；需要使用可选插件能力时走 `plugin_features`。这样可以把插件系统变化集中在 `backend/plugin/` 内部，外部只知道 `Plugin lifecycle` 和 `Plugin feature gateway` 两个 Seam。

插件系统内部职责如下：

| Module | 作用 |
| --- | --- |
| `PluginLifecycle` | 兼容 facade，承接外部调用 |
| `PluginFeatureGateway` | 集中 email/config/oauth2/casbin 等可选插件能力调用 |
| `PluginRegistry` | 插件发现、必需插件检查、`plugin.toml` 解析、依赖排序、插件模型发现 |
| `PluginRuntimeStatus` | Redis-backed 插件启用状态、变更标记、状态检查 |
| `PluginApiMounting` | 扩展级/应用级插件路由注入，保留公开 URL 兼容 |
| `PluginPackageManager` | 后端插件安装、卸载、打包、依赖安装/卸载 |
| `PluginHooks` | 插件 setup/lifespan/OpenTelemetry hooks |

新增插件时，插件目录内部仍按 `api/model/schema/crud/service/plugin.toml` 组织；插件运行时接入点统一通过 `plugin.toml` 和 `Plugin API mounting`，不要让业务模块手动 import 插件路由。

## 10. 开发建议

- 先找一个相近模块复制结构，`Dept` 适合学习树形/关联校验，`Task Scheduler` 适合学习分页列表，插件模块适合学习扩展级路由。
- `api` 层保持薄：只处理 FastAPI 参数、依赖、响应。
- `service` 层保持深：把业务规则、跨 DAO 协作、副作用集中到这里。
- `crud` 层保持稳定：封装查询表达式和 CRUDPlus 调用，避免直接从 `api` 拼 SQL。
- 不要绕过统一响应和统一异常，否则前端和异常处理器会失去一致性。
- 插件开发优先写 `plugin.toml`，再写 `api/model/schema/crud/service`，最后确认路由被 `Plugin API mounting` 注入。
- 新增测试时优先从 `User session`、captcha/state challenge、密码安全、`Resource presence`、`Reference integrity`、插件运行时这些 seam 入手，断言对调用方可见的结果和错误语义。
