from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace

import pytest

from fastapi import Response

from backend.app.admin.service import auth_service as auth_service_module
from backend.app.admin.session import ResponseCookieAdapter, UserSessionContext, UserSessionTokens
from backend.core.conf import settings


@pytest.mark.anyio
async def test_refresh_token_delegates_to_user_session_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_context = UserSessionContext(ip='127.0.0.1', os='Windows', browser='Chrome', device='PC')
    expires_at = datetime(2026, 1, 2, tzinfo=datetime_timezone.utc)
    session_tokens = UserSessionTokens(
        access_token='new-access-token',
        access_token_expire_time=expires_at,
        refresh_token='new-refresh-token',
        refresh_token_expire_time=expires_at,
        session_uuid='session-uuid',
    )
    captured: dict[str, object] = {}

    class FakeUserSessionContext:
        @staticmethod
        def from_current_request() -> UserSessionContext:
            return expected_context

    async def fake_refresh(db, refresh_token: str | None, *, context: UserSessionContext, cookie: ResponseCookieAdapter):
        captured['db'] = db
        captured['refresh_token'] = refresh_token
        captured['context'] = context
        captured['cookie'] = cookie
        return session_tokens

    db = object()
    response = Response()
    request = SimpleNamespace(cookies={settings.COOKIE_REFRESH_TOKEN_KEY: 'old-refresh-token'})

    monkeypatch.setattr(auth_service_module, 'UserSessionContext', FakeUserSessionContext)
    monkeypatch.setattr(auth_service_module.user_session_manager, 'refresh', fake_refresh)

    data = await auth_service_module.auth_service.refresh_token(
        db=db,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        response=response,
    )

    assert data.access_token == 'new-access-token'
    assert data.access_token_expire_time == expires_at
    assert data.session_uuid == 'session-uuid'
    assert captured['db'] is db
    assert captured['refresh_token'] == 'old-refresh-token'
    assert captured['context'] is expected_context
    assert isinstance(captured['cookie'], ResponseCookieAdapter)
    assert captured['cookie'].response is response
