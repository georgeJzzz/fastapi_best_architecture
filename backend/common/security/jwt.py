from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from jose import jwt
from starlette.authentication import UnauthenticatedUser

from backend.app.admin.session import NoopCookieAdapter, UserSessionContext, UserSessionUser, user_session_manager
from backend.common.dataclasses import AccessToken, NewToken, RefreshToken, TokenPayload
from backend.common.exception import errors
from backend.core.conf import settings

# JWT dependency injection
DependsJwtAuth = Depends(HTTPBearer())


def jwt_encode(payload: dict[str, Any]) -> str:
    """Compatibility wrapper for User session JWT encoding."""
    return jwt.encode(payload, settings.TOKEN_SECRET_KEY, settings.TOKEN_ALGORITHM)


def jwt_decode(token: str) -> TokenPayload:
    """Compatibility wrapper for User session JWT decoding."""
    return user_session_manager.decode(token)


async def create_access_token(user_id: int, *, multi_login: bool, **kwargs) -> AccessToken:
    """Compatibility wrapper for legacy callers; new code should use User session."""
    tokens = await user_session_manager.create(
        UserSessionUser(
            id=user_id,
            username=kwargs.get('username') or '',
            nickname=kwargs.get('nickname') or '',
            is_multi_login=multi_login,
        ),
        context=UserSessionContext(
            ip=kwargs.get('ip'),
            os=kwargs.get('os'),
            browser=kwargs.get('browser'),
            device=kwargs.get('device'),
        ),
        cookie=NoopCookieAdapter(),
        swagger=kwargs.get('swagger') is not None,
    )
    return AccessToken(
        access_token=tokens.access_token,
        access_token_expire_time=tokens.access_token_expire_time,
        session_uuid=tokens.session_uuid,
    )


async def create_refresh_token(session_uuid: str, user_id: int, *, multi_login: bool) -> RefreshToken:
    """Compatibility wrapper retained for imports; User session now issues refresh tokens with access tokens."""
    refresh_token = await user_session_manager.store.get_refresh_token(user_id, session_uuid)
    if not refresh_token:
        raise errors.TokenError(msg='Refresh Token 已过期，请重新登录')
    token_payload = user_session_manager.decode(refresh_token)
    return RefreshToken(refresh_token=refresh_token, refresh_token_expire_time=token_payload.expire_time)


async def create_new_token(
    refresh_token: str,
    session_uuid: str,
    user_id: int,
    *,
    multi_login: bool,
    **kwargs,
) -> NewToken:
    """Compatibility wrapper retained for imports; new code should call user_session_manager.refresh."""
    redis_refresh_token = await user_session_manager.store.get_refresh_token(user_id, session_uuid)
    if not redis_refresh_token or redis_refresh_token != refresh_token:
        raise errors.TokenError(msg='Refresh Token 已过期，请重新登录')

    await user_session_manager.revoke_session(user_id, session_uuid)
    new_access_token = await create_access_token(user_id, multi_login=multi_login, **kwargs)
    new_refresh_token = await create_refresh_token(new_access_token.session_uuid, user_id, multi_login=multi_login)
    return NewToken(
        new_access_token=new_access_token.access_token,
        new_access_token_expire_time=new_access_token.access_token_expire_time,
        new_refresh_token=new_refresh_token.refresh_token,
        new_refresh_token_expire_time=new_refresh_token.refresh_token_expire_time,
        session_uuid=new_access_token.session_uuid,
    )


async def revoke_token(user_id: int, session_uuid: str) -> None:
    """Compatibility wrapper for revoking one User session."""
    await user_session_manager.revoke_session(user_id, session_uuid)


def get_token(request: Request) -> str:
    """
    获取请求头中的 token

    :param request: FastAPI 请求对象
    :return:
    """
    authorization = request.headers.get('Authorization')
    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != 'bearer':
        raise errors.TokenError(msg='Token 无效')
    return token


async def get_jwt_user(user_id: int):  # noqa: ANN201
    """Compatibility wrapper for authenticated User detail loading."""
    return await user_session_manager.get_user_detail(user_id)


async def jwt_authentication(token: str):  # noqa: ANN201
    """Compatibility wrapper for User session authentication."""
    return await user_session_manager.authenticate_user(token)


def superuser_verify(request: Request, _token: str = DependsJwtAuth) -> bool:
    """
    验证当前用户超级管理员权限

    :param request: FastAPI 请求对象
    :param _token: JWT 令牌
    :return:
    """
    if isinstance(request.user, UnauthenticatedUser):
        raise errors.TokenError

    superuser = request.user.is_superuser
    if not superuser or not request.user.is_staff:
        raise errors.AuthorizationError
    return superuser


# 超级管理员鉴权依赖注入
DependsSuperUser = Depends(superuser_verify)
