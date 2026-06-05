import uuid

from datetime import timedelta
from typing import Any

from jose import ExpiredSignatureError, JWTError, jwt
from pydantic_core import from_json
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.session.cookies import CookieAdapter
from backend.app.admin.session.schemas import UserSessionContext, UserSessionDetail, UserSessionTokens, UserSessionUser
from backend.app.admin.session.store import SessionStore
from backend.app.admin.session.users import UserSnapshotAdapter
from backend.common.context import ctx
from backend.common.dataclasses import TokenPayload
from backend.common.enums import StatusType
from backend.common.exception import errors
from backend.core.conf import settings
from backend.database.db import async_db_session
from backend.utils.timezone import timezone


class UserSessionManager:
    """Deep module for User session token, cookie, and cache lifecycle."""

    def __init__(self, store: SessionStore, user_snapshot: UserSnapshotAdapter | None = None) -> None:
        self.store = store
        self.user_snapshot = user_snapshot

    async def create(
        self,
        user: UserSessionUser,
        *,
        context: UserSessionContext,
        cookie: CookieAdapter,
        swagger: bool = False,
    ) -> UserSessionTokens:
        """Create a User session and write the refresh cookie."""
        return await self._issue_tokens(user, context=context, cookie=cookie, swagger=swagger, revoke_existing=True)

    async def refresh(
        self,
        db: AsyncSession,
        refresh_token: str | None,
        *,
        context: UserSessionContext,
        cookie: CookieAdapter,
    ) -> UserSessionTokens:
        """Refresh a User session and rotate access and refresh tokens."""
        if not refresh_token:
            raise errors.RequestError(msg='Refresh Token 已过期，请重新登录')
        if self.user_snapshot is None:
            raise RuntimeError('User session refresh requires a User snapshot adapter')

        token_payload = self.decode(refresh_token)
        user = errors.require_found(await self.user_snapshot.get(db, token_payload.user_id), msg='用户不存在')
        if not user.status:
            raise errors.AuthorizationError(msg='用户已被锁定, 请联系统管理员')

        redis_refresh_token = await self.store.get_refresh_token(token_payload.user_id, token_payload.session_uuid)
        if not redis_refresh_token or redis_refresh_token != refresh_token:
            raise errors.TokenError(msg='Refresh Token 已过期，请重新登录')

        if not user.is_multi_login and await self.store.has_other_access_sessions(user.id, token_payload.session_uuid):
            raise errors.ForbiddenError(msg='此用户已在异地登录，请重新登录并及时修改密码')

        await self.store.delete_session(token_payload.user_id, token_payload.session_uuid)
        return await self._issue_tokens(user, context=context, cookie=cookie, swagger=False, revoke_existing=False)

    async def authenticate_access_token(self, token: str) -> TokenPayload:
        """Validate an access token against the active User session store."""
        token_payload = self.decode(token)
        redis_token = await self.store.get_access_token(token_payload.user_id, token_payload.session_uuid)
        if not redis_token:
            raise errors.TokenError(msg='Token 已过期')
        if token != redis_token:
            raise errors.TokenError(msg='Token 已失效')
        return token_payload

    async def authenticate_user(self, token: str):  # noqa: ANN201
        """Validate an access token and load the cached authenticated User details."""
        token_payload = await self.authenticate_access_token(token)
        ctx.user_id = token_payload.user_id
        return await self.get_user_detail(token_payload.user_id)

    async def get_user_detail(self, user_id: int):  # noqa: ANN201
        """Load authenticated User details through the User session cache."""
        from backend.app.admin.schema.user import GetUserInfoWithRelationDetail

        cache_user = await self.store.get_user_cache(user_id)
        if not cache_user:
            async with async_db_session() as db:
                current_user = await self._get_current_user(db, user_id)
                user = GetUserInfoWithRelationDetail.model_validate(current_user)
                await self.store.set_user_cache(
                    user_id,
                    user.model_dump_json(),
                    expires_in=settings.TOKEN_EXPIRE_SECONDS,
                )
        else:
            # TODO: Replace with model_validate_json when partial JSON parsing is no longer needed.
            # https://docs.pydantic.dev/latest/concepts/json/#partial-json-parsing
            user = GetUserInfoWithRelationDetail.model_validate(from_json(cache_user, allow_partial=True))
        return user

    async def list_online(self, *, username: str | None = None) -> list[UserSessionDetail]:
        """List active non-Swagger User sessions."""
        online_sessions = await self.store.online_session_uuids()
        sessions: list[UserSessionDetail] = []
        for token in await self.store.list_access_tokens():
            try:
                token_payload = self.decode(token)
            except errors.TokenError:
                continue
            extra_info = await self.store.get_extra_info(token_payload.user_id, token_payload.session_uuid) or {}
            if extra_info.get('swagger') is not None:
                continue
            session_username = extra_info.get('username') or '未知'
            if username is not None and username != session_username:
                continue
            sessions.append(
                UserSessionDetail(
                    id=token_payload.user_id,
                    session_uuid=token_payload.session_uuid,
                    username=session_username,
                    nickname=extra_info.get('nickname') or '未知',
                    ip=extra_info.get('ip') or '未知',
                    os=extra_info.get('os') or '未知',
                    browser=extra_info.get('browser') or '未知',
                    device=extra_info.get('device') or '未知',
                    status=(
                        StatusType.enable
                        if token_payload.session_uuid in online_sessions
                        else StatusType.disable
                    ),
                    last_login_time=extra_info.get('last_login_time') or '未知',
                    expire_time=token_payload.expire_time,
                ),
            )
        return sessions

    async def revoke_session(self, user_id: int, session_uuid: str) -> None:
        """Revoke one User session."""
        await self.store.delete_session(user_id, session_uuid)

    async def revoke_user(self, user_id: int, *, keep_session_uuid: str | None = None) -> None:
        """Revoke a User's sessions and cached User snapshot."""
        await self.store.revoke_user(user_id, keep_session_uuid=keep_session_uuid)

    async def invalidate_user_cache(self, user_id: int) -> None:
        """Invalidate the cached User snapshot without revoking active sessions."""
        await self.store.invalidate_user_cache(user_id)

    @staticmethod
    def decode(token: str) -> TokenPayload:
        """Decode and validate a User session JWT payload."""
        try:
            payload = jwt.decode(
                token,
                settings.TOKEN_SECRET_KEY,
                algorithms=[settings.TOKEN_ALGORITHM],
                options={'verify_exp': True},
            )
            session_uuid = payload.get('session_uuid')
            user_id = payload.get('sub')
            expire = payload.get('exp')
            if not session_uuid or not user_id or not expire:
                raise errors.TokenError(msg='Token 无效')
        except ExpiredSignatureError:
            raise errors.TokenError(msg='Token 已过期')
        except JWTError:
            raise errors.TokenError(msg='Token 无效')
        except Exception:
            raise errors.TokenError(msg='Token 无效')
        return TokenPayload(
            user_id=int(user_id),
            session_uuid=session_uuid,
            expire_time=timezone.from_datetime(timezone.to_utc(expire)),
        )

    async def _get_current_user(self, db: AsyncSession, pk: int):  # noqa: ANN202
        from backend.app.admin.crud.crud_user import user_dao

        user = await user_dao.get_join(db, user_id=pk)
        if not user:
            raise errors.TokenError(msg='Token 无效')
        if not user.status:
            raise errors.AuthorizationError(msg='用户已被锁定，请联系系统管理员')
        if user.dept_id and not user.dept:
            raise errors.AuthorizationError(msg='用户所属部门不存在或已被删除，请联系系统管理员')
        if user.dept and not user.dept.status:
            raise errors.AuthorizationError(msg='用户所属部门已被锁定，请联系系统管理员')
        if user.roles:
            role_status = [role.status for role in user.roles]
            if all(status == 0 for status in role_status):
                raise errors.AuthorizationError(msg='用户所属角色已被锁定，请联系系统管理员')
        return user

    async def _issue_tokens(
        self,
        user: UserSessionUser,
        *,
        context: UserSessionContext,
        cookie: CookieAdapter,
        swagger: bool,
        revoke_existing: bool,
    ) -> UserSessionTokens:
        if revoke_existing and not user.is_multi_login:
            await self.store.revoke_user(user.id)

        session_uuid = str(uuid.uuid4())
        access_expire = timezone.now() + timedelta(seconds=settings.TOKEN_EXPIRE_SECONDS)
        refresh_expire = timezone.now() + timedelta(seconds=settings.TOKEN_REFRESH_EXPIRE_SECONDS)

        access_token = self._encode(user.id, session_uuid, access_expire)
        refresh_token = self._encode(user.id, session_uuid, refresh_expire)

        await self.store.store_access_token(
            user.id,
            session_uuid,
            access_token,
            extra_info=self._build_extra_info(user, context, swagger=swagger),
            expires_in=settings.TOKEN_EXPIRE_SECONDS,
        )
        await self.store.store_refresh_token(
            user.id,
            session_uuid,
            refresh_token,
            expires_in=settings.TOKEN_REFRESH_EXPIRE_SECONDS,
        )

        if not swagger:
            cookie.set_refresh_token(refresh_token, refresh_expire)

        return UserSessionTokens(
            access_token=access_token,
            access_token_expire_time=access_expire,
            refresh_token=refresh_token,
            refresh_token_expire_time=refresh_expire,
            session_uuid=session_uuid,
        )

    async def end(
        self,
        access_token: str | None,
        refresh_token: str | None,
        *,
        cookie: CookieAdapter,
    ) -> None:
        """End a User session. Invalid or missing tokens are ignored."""
        for token in {access_token, refresh_token}:
            if not token:
                continue
            try:
                payload = self.decode(token)
            except errors.TokenError:
                continue
            await self.store.delete_session(payload.user_id, payload.session_uuid)

        cookie.delete_refresh_token()

    @staticmethod
    def _encode(user_id: int, session_uuid: str, expire_time) -> str:  # noqa: ANN001
        return jwt.encode(
            {
                'session_uuid': session_uuid,
                'exp': timezone.to_utc(expire_time).timestamp(),
                'sub': str(user_id),
            },
            settings.TOKEN_SECRET_KEY,
            settings.TOKEN_ALGORITHM,
        )

    @staticmethod
    def _build_extra_info(user: UserSessionUser, context: UserSessionContext, *, swagger: bool) -> dict[str, Any]:
        if swagger:
            return {'swagger': True}

        return {
            'username': user.username,
            'nickname': user.nickname,
            'last_login_time': timezone.to_str(user.last_login_time) if user.last_login_time else None,
            'ip': context.ip,
            'os': context.os,
            'browser': context.browser,
            'device': context.device,
        }
