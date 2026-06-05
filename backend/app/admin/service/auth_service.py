from fastapi import Request, Response
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask, BackgroundTasks

from backend.app.admin.crud.crud_menu import menu_dao
from backend.app.admin.model import User
from backend.app.admin.schema.token import GetLoginToken, GetNewToken
from backend.app.admin.schema.user import AuthLoginParam
from backend.app.admin.session import (
    ResponseCookieAdapter,
    UserSessionContext,
    user_session_manager,
)
from backend.app.admin.service.login_log_service import login_log_service
from backend.app.admin.service.user_login_attempt_service import user_login_attempt_service
from backend.common.enums import LoginLogStatusType, StatusType
from backend.common.exception import errors
from backend.common.i18n import t
from backend.common.log import log
from backend.common.security.jwt import get_token
from backend.core.conf import settings
from backend.database.db import uuid4_str
from backend.utils.timezone import timezone


class AuthService:
    """认证服务类"""

    @staticmethod
    async def user_verify(db: AsyncSession, username: str, password: str) -> tuple[User, int | None]:
        """
        验证用户名和密码

        :param db: 数据库会话
        :param username: 用户名
        :param password: 密码
        :return:
        """
        return await user_login_attempt_service.verify_credentials(db, username, password)

    async def swagger_login(self, *, db: AsyncSession, obj: HTTPBasicCredentials) -> tuple[str, User]:
        """
        Swagger 文档登录

        :param db: 数据库会话
        :param obj: 登录凭证
        :return:
        """
        return await user_login_attempt_service.swagger_login(db=db, obj=obj)

    async def login(
        self,
        *,
        db: AsyncSession,
        response: Response,
        obj: AuthLoginParam,
        background_tasks: BackgroundTasks,
    ) -> GetLoginToken:
        """
        用户登录

        :param db: 数据库会话
        :param response: 响应对象
        :param obj: 登录参数
        :param background_tasks: 后台任务
        :return:
        """
        user = None
        try:
            attempt = await user_login_attempt_service.login(db=db, response=response, obj=obj)
            user = attempt.user
        except errors.NotFoundError as e:
            log.error('登陆错误: 用户名不存在')
            raise errors.NotFoundError(msg=e.msg)
        except (errors.RequestError, errors.CustomError) as e:
            if not user:
                log.error(f'登陆错误: {e.msg}')
            task = BackgroundTask(
                login_log_service.create,
                user_uuid=user.uuid if user else uuid4_str(),
                username=obj.username,
                login_time=timezone.now(),
                status=LoginLogStatusType.fail.value,
                msg=e.msg,
            )
            raise errors.RequestError(code=e.code, msg=e.msg, background=task)
        except Exception as e:
            log.error(f'登陆错误: {e}')
            raise
        else:
            background_tasks.add_task(
                login_log_service.create,
                user_uuid=user.uuid,
                username=obj.username,
                login_time=timezone.now(),
                status=LoginLogStatusType.success.value,
                msg=t('success.login.success'),
            )
            data = GetLoginToken(
                access_token=attempt.session_tokens.access_token,
                access_token_expire_time=attempt.session_tokens.access_token_expire_time,
                session_uuid=attempt.session_tokens.session_uuid,
                password_expire_days_remaining=attempt.password_expire_days_remaining,
                user=user,  # type: ignore
            )
            return data

    @staticmethod
    async def get_codes(*, db: AsyncSession, request: Request) -> list[str]:
        """
        获取用户权限码

        :param db: 数据库会话
        :param request: FastAPI 请求对象
        :return:
        """
        codes = set()
        if request.user.is_superuser:
            menus = await menu_dao.get_all(db, None, None)
            for menu in menus:
                if menu.status == StatusType.enable and menu.perms:
                    codes.update(menu.perms.split(','))
        else:
            roles = [role for role in request.user.roles if role.status == StatusType.enable]
            if roles:
                for role in roles:
                    for menu in role.menus:
                        if menu.status == StatusType.enable and menu.perms:
                            codes.update(menu.perms.split(','))

        return list(codes)

    @staticmethod
    async def refresh_token(*, db: AsyncSession, request: Request, response: Response) -> GetNewToken:
        """
        刷新令牌

        :param db: 数据库会话
        :param request: FastAPI 请求对象
        :param response: FastAPI 响应对象
        :return:
        """
        refresh_token = request.cookies.get(settings.COOKIE_REFRESH_TOKEN_KEY)
        session_tokens = await user_session_manager.refresh(
            db,
            refresh_token,
            context=UserSessionContext.from_current_request(),
            cookie=ResponseCookieAdapter(response),
        )
        data = GetNewToken(
            access_token=session_tokens.access_token,
            access_token_expire_time=session_tokens.access_token_expire_time,
            session_uuid=session_tokens.session_uuid,
        )
        return data

    @staticmethod
    async def logout(*, request: Request, response: Response) -> None:
        """
        用户登出

        :param request: FastAPI 请求对象
        :param response: FastAPI 响应对象
        :return:
        """
        access_token = None
        try:
            access_token = get_token(request)
        except errors.TokenError:
            pass

        await user_session_manager.end(
            access_token,
            request.cookies.get(settings.COOKIE_REFRESH_TOKEN_KEY),
            cookie=ResponseCookieAdapter(response),
        )


auth_service: AuthService = AuthService()
