from types import SimpleNamespace

import pytest

from backend.app.admin.service import user_password_policy as service_module
from backend.common.exception import errors


@pytest.fixture(autouse=True)
def password_policy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_MIN_LENGTH', 6)
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_MAX_LENGTH', 12)
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_REQUIRE_SPECIAL_CHAR', False)
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_HISTORY_CHECK_COUNT', 2)


def test_user_password_policy_rejects_too_short_password() -> None:
    with pytest.raises(errors.RequestError):
        service_module.user_password_policy._validate_shape('a1')


def test_user_password_policy_rejects_too_long_password() -> None:
    with pytest.raises(errors.RequestError):
        service_module.user_password_policy._validate_shape('abcdef1234567')


def test_user_password_policy_rejects_password_without_number() -> None:
    with pytest.raises(errors.RequestError):
        service_module.user_password_policy._validate_shape('abcdef')


def test_user_password_policy_rejects_password_without_letter() -> None:
    with pytest.raises(errors.RequestError):
        service_module.user_password_policy._validate_shape('123456')


def test_user_password_policy_rejects_missing_special_char_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.settings, 'USER_PASSWORD_REQUIRE_SPECIAL_CHAR', True)

    with pytest.raises(errors.RequestError):
        service_module.user_password_policy._validate_shape('abc123')


@pytest.mark.anyio
async def test_user_password_policy_rejects_recent_password(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_by_user_id(db, user_id: int):  # noqa: ANN001
        return [SimpleNamespace(password='old-hash')]

    monkeypatch.setattr(service_module.user_password_history_dao, 'get_by_user_id', fake_get_by_user_id)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: True)

    with pytest.raises(errors.RequestError):
        await service_module.user_password_policy._validate_history(db=None, user_id=1, new_password='abc123')


@pytest.mark.anyio
async def test_user_password_policy_accepts_new_password(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_user_security_config(db) -> None:  # noqa: ANN001
        return None

    async def fake_get_by_user_id(db, user_id: int):  # noqa: ANN001
        return [SimpleNamespace(password='old-hash')]

    monkeypatch.setattr(service_module, 'load_user_security_config', fake_load_user_security_config)
    monkeypatch.setattr(service_module.user_password_history_dao, 'get_by_user_id', fake_get_by_user_id)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: False)

    await service_module.user_password_policy.validate_new(db=None, user_id=1, new_password='abc123')
