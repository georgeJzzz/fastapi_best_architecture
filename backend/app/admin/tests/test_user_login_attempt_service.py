from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace

import pytest

from backend.app.admin.session.schemas import UserSessionTokens
from backend.app.admin.session.schemas import UserSessionContext
from backend.app.admin.service import user_login_attempt_service as service_module
from backend.common.exception import errors


class FakeDb:
    def __init__(self) -> None:
        self.refreshed = []

    async def refresh(self, obj) -> None:  # noqa: ANN001
        self.refreshed.append(obj)


def make_user(password: str | None = 'hashed-password') -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        uuid='user-uuid',
        username='admin',
        nickname='Admin',
        password=password,
        status=1,
        is_multi_login=True,
        last_login_time=None,
        last_password_changed_time=datetime(2026, 1, 1, tzinfo=datetime_timezone.utc),
    )


@pytest.mark.anyio
async def test_user_login_attempt_verifies_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    user = make_user()

    async def fake_get_by_username(db, username: str):  # noqa: ANN001
        events.append(f'lookup:{username}')
        return user

    async def fake_check_login_allowed(*, user_id: int, user_status: int) -> None:
        events.append(f'allowed:{user_id}:{user_status}')

    async def fake_check_password_expiry(*, db, password_changed_time):  # noqa: ANN001
        events.append('expiry')
        return 3

    async def fake_clear(user_id: int) -> None:
        events.append(f'clear:{user_id}')

    monkeypatch.setattr(service_module.user_dao, 'get_by_username', fake_get_by_username)
    monkeypatch.setattr(service_module.user_security_gate, 'check_login_allowed', fake_check_login_allowed)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: True)
    monkeypatch.setattr(service_module.user_password_expiry, 'check', fake_check_password_expiry)
    monkeypatch.setattr(service_module.user_security_gate, 'clear', fake_clear)

    verified_user, days_remaining = await service_module.user_login_attempt_service.verify_credentials(
        db=None,
        username='admin',
        password='plain-password',
    )

    assert verified_user is user
    assert days_remaining == 3
    assert events == ['lookup:admin', 'allowed:7:1', 'expiry', 'clear:7']


@pytest.mark.anyio
async def test_user_login_attempt_records_failure_for_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    failures: list[int] = []
    user = make_user()

    async def fake_get_by_username(db, username: str):  # noqa: ANN001
        return user

    async def fake_check_login_allowed(*, user_id: int, user_status: int) -> None:
        return None

    async def fake_record_login_failure(*, db, user_id: int) -> None:  # noqa: ANN001
        failures.append(user_id)

    monkeypatch.setattr(service_module.user_dao, 'get_by_username', fake_get_by_username)
    monkeypatch.setattr(service_module.user_security_gate, 'check_login_allowed', fake_check_login_allowed)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: False)
    monkeypatch.setattr(service_module.user_security_gate, 'record_login_failure', fake_record_login_failure)

    with pytest.raises(errors.AuthorizationError):
        await service_module.user_login_attempt_service.verify_credentials(
            db=None,
            username='admin',
            password='wrong-password',
        )

    assert failures == [7]


@pytest.mark.anyio
async def test_user_login_attempt_login_creates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    user = make_user()
    tokens = UserSessionTokens(
        access_token='access-token',
        access_token_expire_time=datetime(2026, 1, 1, tzinfo=datetime_timezone.utc),
        refresh_token='refresh-token',
        refresh_token_expire_time=datetime(2026, 1, 2, tzinfo=datetime_timezone.utc),
        session_uuid='session-id',
    )

    async def fake_verify_if_enabled(db, *, uuid: str | None, captcha: str | None) -> None:  # noqa: ANN001
        events.append(f'captcha:{uuid}:{captcha}')

    async def fake_verify_credentials(db, username: str, password: str):  # noqa: ANN001
        events.append(f'credentials:{username}:{password}')
        return user, 5

    async def fake_update_login_time(db, username: str) -> None:  # noqa: ANN001
        events.append(f'login-time:{username}')

    async def fake_create(session_user, *, context, cookie, swagger: bool = False):  # noqa: ANN001
        events.append(f'session:{session_user.id}:{swagger}')
        return tokens

    service = service_module.UserLoginAttemptService()
    monkeypatch.setattr(service_module.login_captcha_service, 'verify_if_enabled', fake_verify_if_enabled)
    monkeypatch.setattr(service, 'verify_credentials', fake_verify_credentials)
    monkeypatch.setattr(service_module.user_dao, 'update_login_time', fake_update_login_time)
    monkeypatch.setattr(service_module.user_session_manager, 'create', fake_create)
    monkeypatch.setattr(
        service_module.UserSessionContext,
        'from_current_request',
        staticmethod(lambda: UserSessionContext(ip='127.0.0.1')),
    )

    result = await service.login(
        db=FakeDb(),
        response=SimpleNamespace(),
        obj=SimpleNamespace(username='admin', password='plain-password', uuid='captcha-id', captcha='abc1'),
    )

    assert result.user is user
    assert result.session_tokens is tokens
    assert result.password_expire_days_remaining == 5
    assert events == [
        'captcha:captcha-id:abc1',
        'credentials:admin:plain-password',
        'login-time:admin',
        'session:7:False',
    ]
