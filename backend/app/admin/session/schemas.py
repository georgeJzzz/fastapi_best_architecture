from __future__ import annotations

import dataclasses

from datetime import datetime
from typing import Any

from backend.common.context import ctx
from backend.common.enums import StatusType


@dataclasses.dataclass(slots=True)
class UserSessionContext:
    """Request facts stored as User session extra info."""

    ip: str | None = None
    os: str | None = None
    browser: str | None = None
    device: str | None = None

    @classmethod
    def from_current_request(cls) -> UserSessionContext:
        return cls(
            ip=ctx.ip,
            os=ctx.os,
            browser=ctx.browser,
            device=ctx.device,
        )


@dataclasses.dataclass(slots=True)
class UserSessionUser:
    """User fields required by the User session module."""

    id: int
    username: str
    nickname: str
    is_multi_login: bool
    last_login_time: datetime | None = None
    status: int | bool = True

    @classmethod
    def from_user(cls, user: Any) -> UserSessionUser:
        return cls(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            is_multi_login=user.is_multi_login,
            last_login_time=user.last_login_time,
            status=user.status,
        )


@dataclasses.dataclass(slots=True)
class UserSessionTokens:
    """Tokens created by the User session module."""

    access_token: str
    access_token_expire_time: datetime
    refresh_token: str
    refresh_token_expire_time: datetime
    session_uuid: str


@dataclasses.dataclass(slots=True)
class UserSessionDetail:
    """Online User session details."""

    id: int
    session_uuid: str
    username: str
    nickname: str
    ip: str
    os: str
    browser: str
    device: str
    status: StatusType
    last_login_time: str
    expire_time: datetime
