from datetime import datetime, timedelta, timezone as datetime_timezone

import pytest

from backend.app.admin.service import user_password_expiry as service_module
from backend.common.exception import errors


class FakeTimezone:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, tzinfo=datetime_timezone.utc)

    def now(self) -> datetime:
        return self.current


@pytest.fixture(autouse=True)
def password_expiry_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_user_security_config(db) -> None:  # noqa: ANN001
        return None

    monkeypatch.setattr(service_module, 'load_user_security_config', fake_load_user_security_config)
    monkeypatch.setattr(service_module, 'timezone', FakeTimezone())
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_EXPIRY_DAYS', 30)
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_REMINDER_DAYS', 7)


@pytest.mark.anyio
async def test_user_password_expiry_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_EXPIRY_DAYS', 0)

    result = await service_module.user_password_expiry.check(db=None, password_changed_time=None)

    assert result is None


@pytest.mark.anyio
async def test_user_password_expiry_rejects_missing_changed_time() -> None:
    with pytest.raises(errors.AuthorizationError):
        await service_module.user_password_expiry.check(db=None, password_changed_time=None)


@pytest.mark.anyio
async def test_user_password_expiry_rejects_expired_password() -> None:
    changed_time = service_module.timezone.now() - timedelta(days=31)

    with pytest.raises(errors.AuthorizationError):
        await service_module.user_password_expiry.check(db=None, password_changed_time=changed_time)


@pytest.mark.anyio
async def test_user_password_expiry_returns_remaining_days_in_reminder_window() -> None:
    changed_time = service_module.timezone.now() - timedelta(days=25)

    result = await service_module.user_password_expiry.check(db=None, password_changed_time=changed_time)

    assert result == 5


@pytest.mark.anyio
async def test_user_password_expiry_returns_none_before_reminder_window() -> None:
    changed_time = service_module.timezone.now() - timedelta(days=10)

    result = await service_module.user_password_expiry.check(db=None, password_changed_time=changed_time)

    assert result is None
