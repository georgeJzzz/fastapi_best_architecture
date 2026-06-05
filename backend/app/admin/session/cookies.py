from datetime import datetime
from typing import Protocol

from fastapi import Response

from backend.core.conf import settings
from backend.utils.timezone import timezone


class CookieAdapter(Protocol):
    """Adapter for refresh-token cookie mutation."""

    def set_refresh_token(self, value: str, expires: datetime) -> None: ...

    def delete_refresh_token(self) -> None: ...


class ResponseCookieAdapter:
    """FastAPI response cookie adapter."""

    def __init__(self, response: Response) -> None:
        self.response = response

    def set_refresh_token(self, value: str, expires: datetime) -> None:
        self.response.set_cookie(
            key=settings.COOKIE_REFRESH_TOKEN_KEY,
            value=value,
            max_age=settings.COOKIE_REFRESH_TOKEN_EXPIRE_SECONDS,
            expires=timezone.to_utc(expires),
            httponly=True,
        )

    def delete_refresh_token(self) -> None:
        self.response.delete_cookie(settings.COOKIE_REFRESH_TOKEN_KEY)


class NoopCookieAdapter:
    """Cookie adapter for User session flows that intentionally skip cookies."""

    def set_refresh_token(self, value: str, expires: datetime) -> None:
        pass

    def delete_refresh_token(self) -> None:
        pass


class FakeCookieAdapter:
    """Inspectable cookie adapter for User session tests."""

    def __init__(self) -> None:
        self.refresh_token: str | None = None
        self.refresh_token_expires: datetime | None = None
        self.deleted_refresh_token = False

    def set_refresh_token(self, value: str, expires: datetime) -> None:
        self.refresh_token = value
        self.refresh_token_expires = expires
        self.deleted_refresh_token = False

    def delete_refresh_token(self) -> None:
        self.refresh_token = None
        self.refresh_token_expires = None
        self.deleted_refresh_token = True
