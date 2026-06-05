from dataclasses import dataclass

from fastapi import Response
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.crud.crud_user import user_dao
from backend.app.admin.model import User
from backend.app.admin.schema.user import AuthLoginParam
from backend.app.admin.session import (
    NoopCookieAdapter,
    ResponseCookieAdapter,
    UserSessionContext,
    UserSessionTokens,
    UserSessionUser,
    user_session_manager,
)
from backend.app.admin.service.login_captcha_service import login_captcha_service
from backend.app.admin.service.user_password_expiry import user_password_expiry
from backend.app.admin.service.user_password_policy import user_password_policy
from backend.app.admin.service.user_security_gate import user_security_gate
from backend.common.exception import errors


@dataclass(slots=True)
class UserLoginAttemptResult:
    """用户登录尝试结果。"""

    user: User
    session_tokens: UserSessionTokens
    password_expire_days_remaining: int | None


class UserLoginAttemptService:
    """用户登录尝试 Module，集中验证码、凭证安全和 User session 创建顺序。"""

    async def verify_credentials(self, db: AsyncSession, username: str, password: str) -> tuple[User, int | None]:
        """验证用户名和密码，并返回密码到期提醒天数。"""
        user = errors.require_found(await user_dao.get_by_username(db, username), msg='用户名或密码有误')

        await user_security_gate.check_login_allowed(user_id=user.id, user_status=user.status)

        if user.password is None or not user_password_policy.verify(password, user.password):
            await user_security_gate.record_login_failure(db=db, user_id=user.id)
            raise errors.AuthorizationError(msg='用户名或密码有误')

        days_remaining = await user_password_expiry.check(db=db, password_changed_time=user.last_password_changed_time)

        await user_security_gate.clear(user.id)

        return user, days_remaining

    async def login(
        self,
        *,
        db: AsyncSession,
        response: Response,
        obj: AuthLoginParam,
    ) -> UserLoginAttemptResult:
        """执行后台用户登录尝试。"""
        await login_captcha_service.verify_if_enabled(db, uuid=obj.uuid, captcha=obj.captcha)

        user, days_remaining = await self.verify_credentials(db, obj.username, obj.password)
        await user_dao.update_login_time(db, obj.username)
        await db.refresh(user)
        session_tokens = await user_session_manager.create(
            UserSessionUser.from_user(user),
            context=UserSessionContext.from_current_request(),
            cookie=ResponseCookieAdapter(response),
        )
        return UserLoginAttemptResult(
            user=user,
            session_tokens=session_tokens,
            password_expire_days_remaining=days_remaining,
        )

    async def swagger_login(self, *, db: AsyncSession, obj: HTTPBasicCredentials) -> tuple[str, User]:
        """执行 Swagger 文档登录尝试。"""
        user, _ = await self.verify_credentials(db, obj.username, obj.password)
        await user_dao.update_login_time(db, obj.username)
        await db.refresh(user)
        session_tokens = await user_session_manager.create(
            UserSessionUser.from_user(user),
            context=UserSessionContext(),
            cookie=NoopCookieAdapter(),
            swagger=True,
        )
        return session_tokens.access_token, user


user_login_attempt_service = UserLoginAttemptService()
